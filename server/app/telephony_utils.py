import base64
import json
import audioop
import numpy as np
from fastapi import WebSocket
from typing import Dict, Any, Optional

# Constants for Twilio Stream
TWILIO_SAMPLE_RATE = 8000
TWILIO_CHANNELS = 1
# OpenAI/Agent usually expects 24000
AGENT_SAMPLE_RATE = 24000

class TelephonyUtils:
    @staticmethod
    def ulaw_to_pcm16(ulaw_data: bytes) -> bytes:
        """Convert mu-law (8kHz) to PCM 16-bit (8kHz)."""
        return audioop.ulaw2lin(ulaw_data, 2)

    @staticmethod
    def pcm16_to_ulaw(pcm_data: bytes) -> bytes:
        """Convert PCM 16-bit (8kHz) to mu-law (8kHz)."""
        return audioop.lin2ulaw(pcm_data, 2)

    @staticmethod
    def resample_audio(audio_bytes: bytes, from_rate: int, to_rate: int) -> bytes:
        """
        Resample audio using audioop.ratecv.
        Note: ratecv returns (new_fragments, state). We ignore state for simple chunks but 
        for streaming we should ideally maintain state. For simplicity here we reset state.
        """
        # None state means start from scratch
        new_fragments, _ = audioop.ratecv(audio_bytes, 2, 1, from_rate, to_rate, None)
        return new_fragments

    @staticmethod
    def decode_twilio_payload(payload: str) -> np.ndarray:
        """
        Decode Twilio Base64 payload (µ-law 8kHz) -> Float32 24kHz (for Agent).
        """
        # 1. Decode Base64
        ulaw_data = base64.b64decode(payload)
        
        # 2. µ-law -> PCM16 (8kHz)
        pcm_8k = TelephonyUtils.ulaw_to_pcm16(ulaw_data)
        
        # 3. Resample 8kHz -> 24kHz
        pcm_24k = TelephonyUtils.resample_audio(pcm_8k, TWILIO_SAMPLE_RATE, AGENT_SAMPLE_RATE)
        
        # 4. Bytes -> Numpy Float32
        audio_int16 = np.frombuffer(pcm_24k, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        
        return audio_float32

    @staticmethod
    def encode_response_payload(audio_data: np.ndarray) -> str:
        """
        Encode Agent Audio (Float32 or Int16) -> Twilio Base64 (µ-law 8kHz).
        """
        # 1. Check if Float32 or Int16
        if audio_data.dtype == np.float32:
            # Float32 -> Int16
            audio_int16 = (audio_data * 32767).astype(np.int16)
        else:
            # Assume already Int16
            audio_int16 = audio_data.astype(np.int16)
            
        pcm_24k = audio_int16.tobytes()
        
        # 2. Resample 24kHz -> 8kHz
        pcm_8k = TelephonyUtils.resample_audio(pcm_24k, AGENT_SAMPLE_RATE, TWILIO_SAMPLE_RATE)
        
        # 3. PCM16 -> µ-law
        ulaw_data = TelephonyUtils.pcm16_to_ulaw(pcm_8k)
        
        # 4. Encode Base64
        return base64.b64encode(ulaw_data).decode("utf-8")

    @staticmethod
    def create_twilio_message(event_type: str, stream_sid: str, payload: Optional[str] = None, mark_name: Optional[str] = None) -> str:
        """Create a JSON string for Twilio WebSocket message."""
        msg = {
            "event": event_type,
            "streamSid": stream_sid,
        }
        if payload:
            msg["media"] = {"payload": payload}
        if mark_name:
            msg["mark"] = {"name": mark_name}
        return json.dumps(msg)

    @staticmethod
    def is_speech(audio_chunk: bytes, threshold: int = 500) -> bool:
        """
        Simple energy-based VAD (Voice Activity Detection).
        Returns True if RMS energy is above threshold.
        """
        try:
            rms = audioop.rms(audio_chunk, 2)
            return rms > threshold
        except Exception:
            return False

from agents.voice import VoiceStreamEvent, VoiceStreamEventAudio
from app.utils import WebsocketHelper

class TwilioHelper(WebsocketHelper):
    def __init__(
        self,
        websocket: WebSocket,
        history: list,
        initial_agent: Any,
        session_id: str,
        stream_sid: str,
        team_agent_id: Optional[int] = None,
        channel_type: str = "phone",
    ):
        super().__init__(
            websocket,
            history,
            initial_agent,
            session_id,
            team_agent_id=team_agent_id,
            channel_type=channel_type,
        )
        self.stream_sid = stream_sid

    async def show_user_input(self, user_input: str):
        # Debug: See what STT actually heard
        print(f"DEBUG TRANSCRIPT: '{user_input}'")
        
        # Twilio doesn't have a UI to show user input, so we just track history
        self.history.append({
            "type": "message",
            "role": "user",
            "content": user_input,
        })
        
        # Broadcast to Session Manager ONLY if content is not empty
        if user_input.strip():
            from app.session_manager import session_manager
            await session_manager.update_session(self.session_id, {"content": user_input}, is_user=True)
            
            # We could log this or track analytics
            self.analytics.track_message(role="user", content=user_input, agent_name=None)
            
        return (self.history, self.latest_agent)

    async def stream_response(self, new_tokens: str, is_text: bool = False):
        # Phone calls don't show streaming text
        if is_text:
            return 
        # Logic for non-text streaming (if any)
        pass

    async def handle_new_item(self, event):
        # For phone, we ignore visual updates but still preserve audit history.
        if hasattr(event, "new_agent"):
            previous_agent_name = getattr(self.latest_agent, "name", None)
            self.latest_agent = event.new_agent
            self.analytics.track_handoff(previous_agent_name, getattr(self.latest_agent, "name", None))
        elif hasattr(event, "item"):
            item = event.item.to_input_item()
            self.history.append(item)
            if item.get("type") == "function_call":
                tool_name = item.get("name", "unknown")
                try:
                    arguments = json.loads(item.get("arguments", "{}"))
                except Exception:
                    arguments = {}
                self.analytics.track_tool_call(
                    tool_name,
                    arguments,
                    agent_name=getattr(self.latest_agent, "name", None),
                )

    async def text_output_complete(self, output, is_done=False):
        if is_done:
            self.latest_agent = output.last_agent
            self.history = output.to_input_list()
            
            # Broadcast final Agent response to Session Manager
            # The agent's response is usually in output.messages[-1] or similar, 
            # but usually 'output' is a complex object.
            # Ideally we extract the last message text.
            # Assuming the pipeline generated audio, it also generated text.
            # We can try to extract it from the last message in history.
            last_msg = self.history[-1]
            if last_msg.get("role") == "assistant" and last_msg.get("content"):
                 from app.session_manager import session_manager
                 assistant_content = last_msg["content"]
                 if isinstance(assistant_content, list):
                     assistant_content = "".join(
                         part.get("text", "") if isinstance(part, dict) else str(part)
                         for part in assistant_content
                     )
                 await session_manager.update_session(self.session_id, {"content": assistant_content}, is_user=False)
                 self.analytics.track_message(
                     role="assistant",
                     content=str(assistant_content),
                     agent_name=getattr(self.latest_agent, "name", None),
                 )
            
            self.partial_response = ""

    async def send_audio_chunk(self, event: VoiceStreamEvent):
        if isinstance(event, VoiceStreamEventAudio):
            # 1. Decode -> Resample -> Encode mu-law -> Base64
            # We assume event.data is float32 or int16 numpy array
            b64_payload = TelephonyUtils.encode_response_payload(event.data)
            
            # 2. Send Media event
            msg = TelephonyUtils.create_twilio_message("media", self.stream_sid, payload=b64_payload)
            await self.websocket.send_text(msg)

    async def send_audio_done(self):
        # Optional: Send a Mark event to know when playback finishes
        msg = TelephonyUtils.create_twilio_message("mark", self.stream_sid, mark_name="response_end")
        await self.websocket.send_text(msg)

