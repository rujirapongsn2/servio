import base64
import json

import numpy as np
from agents import (
    Agent,
    RunItemStreamEvent,
    RawResponsesStreamEvent,
    AgentUpdatedStreamEvent,
)
from agents.voice import AudioInput, VoiceStreamEvent, VoiceStreamEventAudio
from fastapi import WebSocket
from openai.types.responses import ResponseTextDeltaEvent

from app.analytics_service import get_analytics_service


def transform_data_to_events(audio_np: np.ndarray) -> dict:
    return {
        "type": "response.audio.delta",
        "delta": base64.b64encode(audio_np.tobytes()).decode("utf-8"),
        "output_index": 0,
        "content_index": 0,
        "item_id": "",
        "response_id": "",
        "event_id": "",
    }


def is_new_output_item(event):
    return isinstance(event, RunItemStreamEvent)


def is_text_output(event):
    return event.type == "raw_response_event" and isinstance(
        event.data, ResponseTextDeltaEvent
    )


def is_sync_message(data):
    return data["type"] == "history.update" and (
        not data["inputs"] or data["inputs"][-1].get("role") != "user"
    )


def is_new_text_message(data):
    return data["type"] == "history.update" and (
        data["inputs"] and data["inputs"][-1].get("role") == "user"
    )


def process_inputs(data, connection) -> str:
    connection.history = data["inputs"][:-1]
    return data["inputs"][-1]["content"]


def is_new_audio_chunk(data):
    return data["type"] == "input_audio_buffer.append"


def is_audio_complete(data):
    return data["type"] == "input_audio_buffer.commit"


def extract_audio_chunk(data):
    decoded_bytes = base64.b64decode(data["delta"])
    audio_int16 = np.frombuffer(decoded_bytes, dtype=np.int16)
    audio_data = audio_int16.astype(np.float32) / 32768.0
    return audio_data


def concat_audio_chunks(chunks) -> AudioInput:
    return AudioInput(np.concatenate(chunks))


class WebsocketHelper:
    def __init__(self, websocket: WebSocket, history: list, initial_agent: Agent, session_id: str, voice_response_enabled: bool = True):
        self.websocket = websocket
        self.history = history or []
        self.latest_agent = initial_agent
        self.partial_response = ""
        self.session_id = session_id
        self.voice_response_enabled = voice_response_enabled

        # Initialize analytics tracking
        self.analytics = get_analytics_service()
        self.conversation_id = self.analytics.start_conversation(session_id)

    async def show_user_input(self, user_input: str):
        self.history.append(
            {
                "type": "message",
                "role": "user",
                "content": user_input,
            }
        )

        # Track user message in analytics
        self.analytics.track_message(
            role="user",
            content=user_input,
            agent_name=None
        )

        await self.websocket.send_text(
            json.dumps(
                {
                    "type": "history.updated",
                    "reason": "user.input",
                    "inputs": self.history,
                    "agent_name": self.latest_agent.name,
                }
            )
        )
        return (self.history, self.latest_agent)

    async def stream_response(self, new_tokens: str, is_text: bool = False):
        if is_text:
            return

        self.partial_response += new_tokens
        await self.websocket.send_text(
            json.dumps(
                {
                    "type": "history.updated",
                    "reason": "response.text.delta",
                    "inputs": self.history
                    + [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": self.partial_response,
                        }
                    ],
                    "agent_name": self.latest_agent.name,
                }
            )
        )

    async def handle_new_item(
        self,
        event: RawResponsesStreamEvent | RunItemStreamEvent | AgentUpdatedStreamEvent,
    ):
        if is_new_output_item(event):
            item = event.item.to_input_item()  # type: ignore
            self.history.append(item)

            # Track tool calls in analytics
            if item.get("type") == "function_call":
                tool_name = item.get("name", "unknown")
                try:
                    arguments = json.loads(item.get("arguments", "{}"))
                except:
                    arguments = {}

                self.analytics.track_tool_call(tool_name, arguments)

            await self.websocket.send_text(
                json.dumps(
                    {
                        "type": "history.updated",
                        "reason": "response.input_item",
                        "inputs": self.history,
                        "agent_name": self.latest_agent.name,
                    }
                )
            )
        elif is_text_output(event):
            await self.stream_response(event.data.delta)  # type: ignore

    async def text_output_complete(self, output, is_done=False):
        if not is_done:
            await self.websocket.send_text(
                json.dumps(
                    {
                        "type": "history.updated",
                        "inputs": self.history,
                        "sync": True,
                        "agent_name": self.latest_agent.name,
                    }
                )
            )
        else:
            # Track agent response in analytics before clearing partial_response
            if self.partial_response:
                self.analytics.track_message(
                    role="assistant",
                    content=self.partial_response,
                    agent_name=self.latest_agent.name
                )

            self.partial_response = ""
            self.latest_agent = output.last_agent
            self.history = output.to_input_list()
            await self.websocket.send_text(
                json.dumps(
                    {
                        "type": "history.updated",
                        "inputs": self.history,
                        "reason": "response.done",
                        "agent_name": self.latest_agent.name,
                    }
                )
            )

    async def send_admin_message(self, content: str):
        self.history.append(
            {
                "type": "message",
                "role": "assistant", # Or "admin"? But "assistant" ensures it shows up on left side.
                "content": content,
            }
        )

        # Track admin message in analytics
        self.analytics.track_message(
            role="assistant",
            content=content,
            agent_name="Admin (Manual Mode)"
        )

        await self.websocket.send_text(
            json.dumps(
                {
                    "type": "history.updated",
                    "reason": "admin.message",
                    "inputs": self.history,
                    "agent_name": self.latest_agent.name,
                }
            )
        )

    async def send_audio_chunk(self, event: VoiceStreamEvent):
        # Skip audio output if voice response is disabled
        if not self.voice_response_enabled:
            return

        if isinstance(event, VoiceStreamEventAudio):
            await self.websocket.send_text(
                json.dumps(transform_data_to_events(event.data))  # type: ignore
            )

    async def send_audio_done(self):
        await self.websocket.send_text(json.dumps({"type": "audio.done"}))

    async def end_conversation(self, outcome: str = "completed"):
        """End conversation tracking and save to database"""
        await self.analytics.end_conversation(outcome=outcome)
