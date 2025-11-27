import time
from collections.abc import AsyncIterator
from logging import getLogger
from typing import Any, Dict
import uuid

from agents import Runner, trace
from agents.voice import (
    TTSModelSettings,
    VoicePipeline,
    VoicePipelineConfig,
    VoiceWorkflowBase,
)
from app.agent_config import get_runtime_starting_agent
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
from app.session_manager import session_manager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
import os


from dotenv import load_dotenv

# When .env file is present, it will override the environment variables
load_dotenv(dotenv_path="../.env", override=True)

app = FastAPI()

# Import and include admin routes
from app.admin_routes import router as admin_router
app.include_router(admin_router)

logger = getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Softnix.png placed at repo root via a simple static endpoint
@app.get("/assets/Softnix.png")
def softnix_logo_png():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    path = os.path.join(root_dir, "Softnix.png")
    if os.path.exists(path):
        return FileResponse(path)
    return HTMLResponse("Softnix.png not found", status_code=404)

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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    session_id = str(uuid.uuid4())
    await session_manager.connect(websocket, session_id)

    try:
        with trace("Voice Agent Chat"):
            # Compose a fresh coordinator agent that includes DB-defined agents as handoffs
            dynamic_starting_agent = get_runtime_starting_agent()
            connection = WebsocketHelper(websocket, [], dynamic_starting_agent, session_id)
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


@app.websocket("/ws/admin/monitor")
async def admin_monitor_endpoint(websocket: WebSocket, session_id: str = Query(None)):
    # In a real app, validate admin token here
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
async def get_active_sessions():
    return session_manager.get_all_sessions()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
