import time
from collections.abc import AsyncIterator
from logging import getLogger
from typing import Any, Dict
import uuid
import json
import base64
import audioop
import secrets


from agents import Runner, trace
from agents.voice import (
    TTSModelSettings,
    VoiceStreamEventAudio,
    VoicePipeline,
    VoicePipelineConfig,
    VoiceWorkflowBase,
)
from openai import AsyncOpenAI
import numpy as np
from app.agent_config import get_runtime_starting_agent
from app.auth import get_current_user, decode_access_token
from app.utils import (
    WebsocketHelper,
    concat_audio_chunks,
    extract_audio_chunk,
    is_audio_complete,
    is_new_audio_chunk,
    is_new_text_message,
    is_sync_message,
    is_text_output,
    process_inputs,
)
from app.telephony_utils import TelephonyUtils, TwilioHelper
from app.session_manager import session_manager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request, Response, status, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
import os


from dotenv import load_dotenv
from pathlib import Path

# Try Docker environment first, then local .env
if not os.getenv("OPENAI_API_KEY"):
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(dotenv_path=env_path, override=True)

app = FastAPI()

# Import and include admin routes
from app.admin_routes import router as admin_router
app.include_router(admin_router)

# Database initialization
from app.database import init_database

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up server...")
    try:
        init_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")


logger = getLogger(__name__)

# Configure CORS with environment variable support for production
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",") if os.getenv("ALLOWED_ORIGINS") else [
    "https://localhost",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
]

# For development: allow all origins ONLY if explicitly in development mode
if os.getenv("ENVIRONMENT") == "development":
    # In development, be more permissive
    ALLOWED_ORIGINS = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Serve Softnix.png placed at repo root via a simple static endpoint
@app.get("/assets/Softnix.png")
def softnix_logo_png():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    path = os.path.join(root_dir, "Softnix.png")
    if os.path.exists(path):
        return FileResponse(path)
    return HTMLResponse("Softnix.png not found", status_code=404)

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

class Workflow(VoiceWorkflowBase):
    def __init__(self, connection: WebsocketHelper, session_id: str):
        self.connection = connection
        self.session_id = session_id

    async def run(self, input_text: str) -> AsyncIterator[str]:
        conversation_history, latest_agent = await self.connection.show_user_input(
            input_text
        )
        
        # Update session manager with user message
        await session_manager.update_session(self.session_id, {"content": input_text}, is_user=True)

        # Check for Manual Mode
        if session_manager.sessions.get(self.session_id) and session_manager.sessions[self.session_id].mode == "MANUAL":
            # In manual mode, we don't run the agent. 
            # The admin will respond via a separate channel (WebSocket).
            # We might want to send a "typing" indicator or just nothing.
            return

        output = Runner.run_streamed(
            latest_agent,
            conversation_history,
        )

        async for event in output.stream_events():
            await self.connection.handle_new_item(event)

            if is_text_output(event):
                yield event.data.delta  # type: ignore

        await self.connection.text_output_complete(output, is_done=True)
        
        # Update session manager with agent response (full response is in connection.partial_response or we can capture it here)
        # Actually connection.text_output_complete clears partial_response.
        # We can get the last message from history.
        if self.connection.history and self.connection.history[-1]["role"] == "assistant":
             await session_manager.update_session(self.session_id, {"content": self.connection.history[-1]["content"]}, is_user=False)


# In-memory store for pending stream tokens
# Format: {token: timestamp}
PENDING_STREAM_TOKENS: Dict[str, float] = {}
STREAM_TOKEN_EXPIRY = 60  # Token valid for 60 seconds



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, api_key: str = Query(None)):
    # Validate API key before accepting connection
    from app import database

    if not api_key:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "API key is required"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Extract Origin header for domain validation
    origin = websocket.headers.get("origin") or websocket.headers.get("Origin")

    if not database.validate_api_key(api_key, origin=origin):
        await websocket.accept()
        error_message = "Invalid or expired API key"
        if origin:
            error_message += f" or unauthorized origin: {origin}"
        await websocket.send_json({"type": "error", "message": error_message})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Increment usage count for this API key
    database.increment_api_key_usage(api_key)

    # Fetch API key settings including voice_response_enabled
    api_key_data = database.get_api_key_by_key(api_key)
    voice_response_enabled = api_key_data.get("voice_response_enabled", True) if api_key_data else True

    session_id = str(uuid.uuid4())
    await session_manager.connect(websocket, session_id, source="text_widget")

    # Send session config to widget
    await websocket.send_json({
        "type": "session.config",
        "voice_response_enabled": voice_response_enabled
    })

    try:
        with trace("Voice Agent Chat"):
            # Compose a fresh coordinator agent that includes DB-defined agents as handoffs
            dynamic_starting_agent = get_runtime_starting_agent()
            connection = WebsocketHelper(websocket, [], dynamic_starting_agent, session_id, voice_response_enabled)
            session_manager.register_helper(session_id, connection)
            audio_buffer = []

            workflow = Workflow(connection, session_id)
            while True:
                try:
                    message = await websocket.receive_json()
                except WebSocketDisconnect:
                    print("Client disconnected")
                    break

                # Handle text based messages
                if is_sync_message(message):
                    connection.history = message["inputs"]
                    if message.get("reset_agent", False):
                        # Recompose to pick up latest DB changes on reset
                        connection.latest_agent = get_runtime_starting_agent()
                elif is_new_text_message(message):
                    user_input = process_inputs(message, connection)
                    async for new_output_tokens in workflow.run(user_input):
                        await connection.stream_response(new_output_tokens, is_text=True)

                # Handle a new audio chunk
                elif is_new_audio_chunk(message):
                    # Update source to voice_widget if it's the first audio chunk
                    if session_manager.sessions.get(session_id) and session_manager.sessions[session_id].source == "text_widget":
                        session_manager.sessions[session_id].source = "voice_widget"
                        await session_manager.broadcast_sessions_list()
                    
                    audio_buffer.append(extract_audio_chunk(message))

                # Send full audio to the agent
                elif is_audio_complete(message):
                    start_time = time.perf_counter()

                    def transform_data(data):
                        nonlocal start_time
                        if start_time:
                            print(
                                f"Time taken to first byte: {time.perf_counter() - start_time}s"
                            )
                            start_time = None
                        return data

                    audio_input = concat_audio_chunks(audio_buffer)
                    
                    # Check manual mode for audio too
                    if session_manager.sessions.get(session_id) and session_manager.sessions[session_id].mode == "MANUAL":
                         # Just ignore audio in manual mode for now, or maybe transcribe it but don't respond
                         audio_buffer = []
                         continue

                    output = await VoicePipeline(
                        workflow=workflow,
                        config=VoicePipelineConfig(
                            tts_settings=TTSModelSettings(
                                buffer_size=512, transform_data=transform_data
                            )
                        ),
                    ).run(audio_input)
                    async for event in output.stream():
                        await connection.send_audio_chunk(event)

                    audio_buffer = []  # reset the audio buffer
    finally:
        # End analytics tracking
        if 'connection' in locals():
            await connection.end_conversation(outcome="completed")
        session_manager.disconnect(session_id)


@app.websocket("/ws/twilio-stream")
async def twilio_stream_endpoint(websocket: WebSocket):
    # Remove early query param check
    # We will validate in the 'start' event

    # Clean up old tokens occasionally
    current_time = time.time()
    to_remove = [k for k, v in PENDING_STREAM_TOKENS.items() if current_time - v > STREAM_TOKEN_EXPIRY]
    for k in to_remove:
        if k in PENDING_STREAM_TOKENS:
            del PENDING_STREAM_TOKENS[k]

    # session_manager.connect will handle accept()
    stream_sid = None
    session_id = str(uuid.uuid4())
    
    # Register session with tracking for Admin Dashboard
    # We create a dummy connection object or use the TwilioHelper once initialized
    # But tracking requires 'connect' first.
    await session_manager.connect(websocket, session_id, source="phone")
    # Set mode to AI by default
    session_manager.set_mode(session_id, "AI")
    
    connection = None
    audio_buffer = []
    
    # VAD State
    silence_frames = 0
    has_spoken = False

    try:
        # 1. Wait for 'start' event to get streamSid, token, and init
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)
            if data['event'] == 'start':
                stream_sid = data['start']['streamSid']
                print(f"Twilio Stream started: {stream_sid}")
                
                # Extract and Validate Token from customParameters
                custom_params = data['start'].get('customParameters', {})
                token = custom_params.get('token')
                
                print(f"--- Debug WebSocket Token (Start Event) ---")
                print(f"Received Token: {token}")
                
                if not token or token not in PENDING_STREAM_TOKENS:
                    print("Twilio Stream Rejecting: Invalid or missing token")
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return

                token_time = PENDING_STREAM_TOKENS[token]
                # Check expiry
                if time.time() - token_time > STREAM_TOKEN_EXPIRY:
                     print("Twilio Stream Rejecting: Expired token")
                     del PENDING_STREAM_TOKENS[token]
                     await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                     return
                
                # Consume token
                del PENDING_STREAM_TOKENS[token]
                print("Twilio Stream Authenticated Successfully")
                break
            elif data['event'] == 'connected':
                continue
        
        # 2. Init Agent
        with trace("Voice Agent Phone Call"):
            dynamic_starting_agent = get_runtime_starting_agent()
            # Initialize history list to track context
            history = []
            connection = TwilioHelper(websocket, history, dynamic_starting_agent, session_id, stream_sid)
            # Register helper so session manager can control it (e.g. view transcripts)
            session_manager.register_helper(session_id, connection)
            
            # --- Welcome Message (Server-Side TTS) ---
            from app import database
            twilio_config = database.get_active_voip_config("twilio")
            if twilio_config and twilio_config.get("welcome_message"):
                welcome_text = twilio_config["welcome_message"]
                print(f"Playing Welcome Message: {welcome_text}")
                try:
                    client = AsyncOpenAI()
                    # Generate speech using OpenAI TTS (alloy is a good general purpose voice)
                    # response_format='pcm' returns 16-bit PCM at 24kHz
                    response = await client.audio.speech.create(
                        model="tts-1",
                        voice="alloy",
                        input=welcome_text,
                        response_format="pcm"
                    )
                    
                    # Read binary content
                    audio_bytes = response.content
                    
                    # Convert raw bytes (int16) to float32 numpy array
                    audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
                    audio_float32 = audio_int16.astype(np.float32) / 32768.0
                    
                    # Send to user
                    await connection.send_audio_chunk(VoiceStreamEventAudio(data=audio_float32))
                    
                    # Update Session Manager (for Admin UI)
                    await session_manager.update_session(session_id, {"content": welcome_text}, is_user=False)
                    
                    # Update Agent Context (Critical for Language Consistency)
                    # This tells the Agent that it has already spoken this text.
                    history.append({
                        "role": "assistant",
                        "content": welcome_text
                    })
                    
                except Exception as e:
                    print(f"Failed to play welcome message: {e}")
            # -----------------------------------------
            
            workflow = Workflow(connection, session_id)
            
            # Init state for main loop
            audio_buffer = []
            silence_frames = 0
            has_spoken = False
            ignore_until = 0
            
            # 3. Media Loop
            while True:
                try:
                    data_str = await websocket.receive_text()
                    data = json.loads(data_str)
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    print(f"Error receiving data: {e}")
                    break

                if data['event'] == 'media':
                    # Echo Cancellation Check
                    if time.time() < ignore_until:
                        # Drain/Skip this packet as it is likely echo
                        continue
                        
                    payload = data['media']['payload']
                    # Decode Twilio audio -> Float32
                    # We keep raw ULW/PCM for VAD check before decoding to full float32 for model
                    ulaw_data = base64.b64decode(payload)
                    pcm_8k_chunk = TelephonyUtils.ulaw_to_pcm16(ulaw_data) # 160 samples (20ms)

                    # 1. VAD Check
                    # Debug: Calculate RMS manually to check levels
                    try:
                        rms = audioop.rms(pcm_8k_chunk, 2)
                    except:
                        rms = 0
                    
                    # Tune Threshold: 
                    # Noise/Breathing seems to be hitting 400-500 causing resets. 
                    # Real speech is > 1000.
                    # Set to 600 to filter out louder breathing/noise.
                    is_voice = rms > 600 
                    
                    if is_voice:
                         # Log only if we are transitioning from silence to voice, or just occasionally
                         if silence_frames > 0:
                             print(f"Voice started! RMS: {rms}")
                         silence_frames = 0
                         has_spoken = True
                    else:
                        silence_frames += 1
                        # Debug: If has_spoken is True, we are waiting for silence to fill up
                        if has_spoken and silence_frames % 10 == 0:
                             print(f"Waiting for silence... ({silence_frames}/30) RMS: {rms}")

                    # 2. Add to buffer (Float32 for AI)
                    chunk_float32 = TelephonyUtils.decode_twilio_payload(payload)
                    audio_buffer.append(chunk_float32)

                    # 3. VAD Trigger Check
                    # - We have spoken at least once in this turn
                    # - Silence has persisted for ~600ms (30 frames)
                    # - OR Buffer is getting too long (> 5 seconds), force send for responsiveness
                    
                    BUFFER_LIMIT = 250 # 250 * 20ms = 5 seconds
                    
                    should_process = False
                    reason = ""
                    
                    if has_spoken and silence_frames > 30:
                        should_process = True
                        reason = "silence"
                    elif len(audio_buffer) > BUFFER_LIMIT:
                        should_process = True
                        reason = "buffer_limit"
                        
                    if should_process:
                        print(f"Speech complete ({reason}). Buffer: {len(audio_buffer)} chunks. Processing...")
                        
                        audio_input = concat_audio_chunks(audio_buffer)
                        audio_buffer = []  # reset
                        silence_frames = 0
                        has_spoken = False
                        
                        # Run pipeline
                        print("Running VoicePipeline...")
                        output = await VoicePipeline(
                            workflow=workflow,
                            config=VoicePipelineConfig(
                                tts_settings=TTSModelSettings(
                                    buffer_size=512, transform_data=lambda x: x
                                )
                            ),
                        ).run(audio_input)
                        
                        print("Streaming response...")
                        async for event in output.stream():
                            await connection.send_audio_chunk(event)
                        print("Response stream done.")
                        
                        # 4. Drain/Clear Echo Buffer (Crucial for Barge-in/Echo Cancellation)
                        # After we finish speaking, any audio that arrived *during* our speech 
                        # (or immediately after) is likely our own voice echo or delayed packets.
                        # We must drain the websocket inputs for a short duration to prevent 
                        # the AI from hearing itself and triggering again.
                        
                        IGNORE_DURATION = 1.2 # seconds to ignore new inputs after speaking
                        drain_start = time.time()
                        
                        # Reset our internal buffer state completely
                        audio_buffer = []  
                        silence_frames = 0
                        has_spoken = False
                        
                        print(f"Draining echo for {IGNORE_DURATION}s...")
                        try:
                            # We can't block strictly, but we can consume messages with a timeout
                            # Since we are in the main 'async for msg in websocket', we can't easily 
                            # call 'websocket.receive_json' here without breaking the outer loop iterator?
                            # Actually, we CANNOT call receive_json inside an async for loop on the same iterator safely
                            # in many frameworks, but passing 'websocket' iterator is tricky.
                            #
                            # BETTER APPROACH: Set a timestamp 'ignore_until'.
                            ignore_until = time.time() + IGNORE_DURATION
                            
                        except Exception as e:
                            print(f"Error draining: {e}")

                        # Signal end of turn (optional)
                        # await connection.send_audio_done()

                elif data['event'] == 'stop':
                    print("Twilio Stream stopped")
                    break
                    
    except Exception as e:
        print(f"Twilio Endpoint Error: {e}")
    finally:
        if connection:
            await connection.end_conversation(outcome="completed")
        if session_id:
            session_manager.disconnect(session_id)
        print(f"Twilio Stream Session Cleaned Up: {session_id}")


@app.websocket("/ws/admin/monitor")
async def admin_monitor_endpoint(websocket: WebSocket, session_id: str = Query(None), token: str = Query(None)):
    if not token:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Authentication required"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    try:
        decode_access_token(token)
    except Exception as e:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": f"Invalid token: {str(e)}"})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await session_manager.connect_admin(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_json()
            # Handle admin actions
            if data.get("type") == "set_mode":
                target_session_id = data.get("session_id")
                mode = data.get("mode")
                if target_session_id and mode in ["AI", "MANUAL"]:
                    session_manager.set_mode(target_session_id, mode)
            
            elif data.get("type") == "admin_message":
                target_session_id = data.get("session_id")
                content = data.get("content")
                if target_session_id and content:
                    # Send to user via session manager
                    await session_manager.send_to_user(target_session_id, content)

    except WebSocketDisconnect:
        if session_id:
            session_manager.disconnect_admin(websocket, session_id)
        else:
            # If it was a dashboard connection, we need to handle that too
            pass


@app.get("/api/admin/sessions")
async def get_active_sessions(current_user: str = Depends(get_current_user)):
    return session_manager.get_all_sessions()


@app.post("/incoming-call")
async def incoming_call_endpoint(request: Request):
    """
    Dynamic endpoint for Twilio Webhook with signature validation.
    Returns TwiML that connects to the WebSocket on the same host.
    """
    from app.auth import validate_twilio_signature
    from app import database

    # Get Twilio configuration
    twilio_config = database.get_active_voip_config("twilio")

    # Validate Twilio signature if auth_token is configured
    if twilio_config and twilio_config.get("auth_token"):
        # Get signature from headers
        twilio_signature = request.headers.get("X-Twilio-Signature", "")

        if not twilio_signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Twilio signature"
            )

        # Get full URL
        url = str(request.url)
        
        # FIX: Force https if behind proxy/ngrok (Twilio signs with https)
        # Nginx/ngrok sends http internally, causing mismatch
        if request.headers.get("X-Forwarded-Proto") == "https" and url.startswith("http://"):
            url = url.replace("http://", "https://", 1)

        # Get form data
        form_data = await request.form()
        params = dict(form_data)

        # Validate signature
        print(f"--- Debug Twilio Signature ---")
        print(f"Request URL: {url}")

        print(f"Twilio Signature: {twilio_signature}")
        print(f"Auth Token: {twilio_config['auth_token'][:5]}...") # Hide full token
        
        is_valid = validate_twilio_signature(
            signature=twilio_signature,
            url=url,
            params=params,
            auth_token=twilio_config["auth_token"]
        )
        print(f"Is Valid: {is_valid}")
        print(f"------------------------------")

        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Twilio signature"
            )


    # Generate a short-lived token for the stream
    stream_token = secrets.token_urlsafe(16)
    PENDING_STREAM_TOKENS[stream_token] = time.time()

    host = request.headers.get("host") or "localhost:8000"
    # If behind ngrok, header 'host' is usually the ngrok domain.
    # Protocol: if https is used, web socket should be wss.
    # We can assume wss for ngrok.

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://{host}/ws/twilio-stream">
            <Parameter name="token" value="{stream_token}" />
        </Stream>
    </Connect>
</Response>
"""
    # Debug XML
    print(f"--- TwiML Response ---")
    print(xml_content)
    print(f"----------------------")
    return Response(content=xml_content, media_type="application/xml")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
