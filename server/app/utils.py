import asyncio
import base64
import json
import threading
from typing import Optional

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

from app.analytics_service import AnalyticsService
from app.product_presentations import parse_product_carousel, product_inquiry
from app.knowledge_image_presentations import hydrate_knowledge_images
from app.knowledge_image_search import ImageSearchSession, ImageSearchRequest, InvalidSearchImage, search_image
from app.knowledge_audio_presentations import hydrate_knowledge_media


_IMAGE_SEARCH_WORKERS = threading.BoundedSemaphore(2)


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


def is_agent_updated(event):
    return isinstance(event, AgentUpdatedStreamEvent)


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
    def __init__(
        self,
        websocket: WebSocket,
        history: list,
        initial_agent: Agent,
        session_id: str,
        voice_response_enabled: bool = True,
        team_agent_id: Optional[int] = None,
        channel_type: Optional[str] = None,
        channel_user_id: Optional[str] = None,
        api_key_id: Optional[int] = None,
    ):
        self.websocket = websocket
        self.history = history or []
        self.latest_agent = initial_agent
        self.partial_response = ""
        self.presentations = {}
        self._knowledge_calls = {}
        self.image_search_session = ImageSearchSession()
        self.team_agent_id = team_agent_id
        self.session_id = session_id
        self.voice_response_enabled = voice_response_enabled

        # Initialize analytics tracking
        self.analytics = AnalyticsService()
        self.conversation_id = self.analytics.start_conversation(
            session_id,
            team_agent_id=team_agent_id,
            channel_type=channel_type,
            channel_user_id=channel_user_id,
            api_key_id=api_key_id,
        )

    def reset_presentations(self):
        self.presentations.clear()
        self._knowledge_calls.clear()
        self.image_search_session.reset()

    async def _image_search_manual(self, request: ImageSearchRequest) -> bool:
        from app.session_manager import session_manager

        session = session_manager.sessions.get(self.session_id)
        if session is None or session.mode != "MANUAL":
            return False
        user_input = "ค้นหาสินค้าจากรูปภาพ" + (f"\n{request.query}" if request.query else "")
        await self.show_user_input(user_input)
        await session_manager.update_session(self.session_id, {"content": user_input}, is_user=True)
        await self.websocket.send_json({"type": "knowledge.image.error", "request_id": request.request_id,
            "code": "manual_mode", "message": "เจ้าหน้าที่กำลังดูแลการสนทนานี้", "retryable": False})
        return True

    async def search_knowledge_image(self, request: ImageSearchRequest, generation: int):
        user_input = "ค้นหาสินค้าจากรูปภาพ" + (f"\n{request.query}" if request.query else "")

        def bounded_search():
            if not _IMAGE_SEARCH_WORKERS.acquire(blocking=False):
                return None
            try:
                return search_image(self.team_agent_id, request)
            finally:
                _IMAGE_SEARCH_WORKERS.release()

        try:
            if await self._image_search_manual(request):
                return
            result = await asyncio.to_thread(bounded_search)
            if generation != self.image_search_session.generation:
                return
            if await self._image_search_manual(request):
                return
            if result is None:
                await self.websocket.send_json({"type": "knowledge.image.error", "request_id": request.request_id,
                    "code": "busy", "message": "กำลังค้นหารูปภาพ กรุณารอสักครู่", "retryable": True})
                return
            message_id = None
            if result.status == "matched":
                message_id, presentation = self.image_search_session.presentation(result, self.team_agent_id)
                self.presentations[message_id] = presentation.model_dump()
                while len(self.presentations) > 50:
                    del self.presentations[next(iter(self.presentations))]
                self.history.extend([
                    {"type": "message", "role": "user", "content": user_input},
                    {"type": "message", "role": "assistant", "id": message_id, "content": [{"type": "output_text", "text": presentation.summary, "annotations": []}]},
                ])
            else:
                content = "ไม่พบสินค้าที่ใกล้เคียง ลองรูปอื่น" if result.status == "no_match" else "การค้นหาด้วยรูปภาพยังไม่พร้อมใช้งาน"
                self.history.extend([
                    {"type": "message", "role": "user", "content": user_input},
                    {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": content, "annotations": []}]},
                ])
            from app.session_manager import session_manager

            summary = presentation.summary if result.status == "matched" else content
            self.analytics.track_message(role="user", content=user_input, agent_name=self.latest_agent.name)
            self.analytics.track_message(role="assistant", content=summary, agent_name=self.latest_agent.name)
            await session_manager.update_session(self.session_id, {"content": user_input}, is_user=True)
            await session_manager.update_session(self.session_id, {"content": summary}, is_user=False)
            if generation != self.image_search_session.generation:
                return
            await self.websocket.send_json({"type": "history.updated", "reason": "knowledge.image.result", "request_id": request.request_id, "inputs": self.history,
                "presentations": self.presentations, "agent_name": self.latest_agent.name})
            await self.websocket.send_json({"type": "knowledge.image.result", "request_id": request.request_id,
                "status": result.status, "message_id": message_id})
        except InvalidSearchImage as exc:
            if generation == self.image_search_session.generation:
                await self.websocket.send_json({"type": "knowledge.image.error", "request_id": request.request_id,
                    "code": "invalid_image", "message": str(exc), "retryable": False})
        except Exception:
            if generation == self.image_search_session.generation:
                await self.websocket.send_json({"type": "knowledge.image.error", "request_id": request.request_id,
                    "code": "unavailable", "message": "การค้นหาด้วยรูปภาพขัดข้องชั่วคราว กรุณาลองใหม่", "retryable": True})

    def resolve_product_inquiry(self, message: dict) -> str | None:
        call_id = message.get("call_id")
        product_id = message.get("product_id")
        if not isinstance(call_id, str) or not isinstance(product_id, str):
            return None
        carousel = parse_product_carousel(self.presentations.get(call_id))
        if carousel is None:
            return None
        for product in carousel.products:
            if product.id == product_id:
                return product_inquiry(product)
        return None

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
                    "presentations": self.presentations,
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
                    "presentations": self.presentations,
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
        if is_agent_updated(event):
            previous_agent_name = getattr(self.latest_agent, "name", None)
            self.latest_agent = event.new_agent
            self.analytics.track_handoff(previous_agent_name, getattr(self.latest_agent, "name", None))
            await self.websocket.send_text(
                json.dumps(
                    {
                        "type": "history.updated",
                        "presentations": self.presentations,
                        "reason": "agent.updated",
                        "inputs": self.history,
                        "agent_name": self.latest_agent.name,
                    }
                )
            )
        elif is_new_output_item(event):
            item = event.item.to_input_item()  # type: ignore
            self.history.append(item)
            if item.get("type") == "function_call":
                for tool in event.item.agent.tools:
                    bundle_id = getattr(tool, "_servio_knowledge_bundle_id", None)
                    if getattr(tool, "name", None) == item.get("name") and bundle_id:
                        self._knowledge_calls[item["call_id"]] = bundle_id
                        break
            if item.get("type") == "function_call_output":
                call_id = item.get("call_id")
                bundle_id = self._knowledge_calls.pop(call_id, None)
                carousel = parse_product_carousel(item.get("output"))
                if carousel is None and bundle_id is not None:
                    carousel = hydrate_knowledge_images(item.get("output"), self.team_agent_id, bundle_id) or hydrate_knowledge_media(item.get("output"), self.team_agent_id, bundle_id)
                if carousel is not None and isinstance(call_id, str) and call_id not in self.presentations:
                    if len(self.presentations) < 50:
                        self.presentations[call_id] = carousel.model_dump(exclude_none=True)

            # Track tool calls in analytics
            if item.get("type") == "function_call":
                tool_name = item.get("name", "unknown")
                try:
                    arguments = json.loads(item.get("arguments", "{}"))
                except:
                    arguments = {}

                self.analytics.track_tool_call(tool_name, arguments, agent_name=self.latest_agent.name)

            await self.websocket.send_text(
                json.dumps(
                    {
                        "type": "history.updated",
                        "presentations": self.presentations,
                        "reason": "response.input_item",
                        "inputs": self.history,
                        "agent_name": self.latest_agent.name,
                    }
                )
            )
        elif is_text_output(event):
            await self.stream_response(event.data.delta)  # type: ignore

    async def text_output_complete(self, output, is_done=False, knowledge_context=None):
        if not is_done:
            await self.websocket.send_text(
                json.dumps(
                    {
                        "type": "history.updated",
                        "presentations": self.presentations,
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
            self.history = [item for item in output.to_input_list() if knowledge_context is None or item != knowledge_context]
            await self.websocket.send_text(
                json.dumps(
                    {
                        "type": "history.updated",
                        "presentations": self.presentations,
                        "inputs": self.history,
                        "reason": "response.done",
                        "agent_name": self.latest_agent.name,
                    }
                )
            )

    async def send_assistant_message(self, content: str, agent_name: Optional[str] = None):
        self.history.append(
            {
                "type": "message",
                "role": "assistant",
                "content": content,
            }
        )

        self.analytics.track_message(
            role="assistant",
            content=content,
            agent_name=agent_name or self.latest_agent.name
        )

        await self.websocket.send_text(
            json.dumps(
                {
                    "type": "history.updated",
                    "presentations": self.presentations,
                    "reason": "assistant.message",
                    "inputs": self.history,
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
                    "presentations": self.presentations,
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
