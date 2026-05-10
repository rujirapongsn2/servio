"""LINE Messaging API client for processing incoming messages and sending replies."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
    AudioMessage,
    ImageMessage,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    ImageMessageContent,
    AudioMessageContent,
)

logger = logging.getLogger(__name__)


class LineClient:
    def __init__(self, channel_access_token: str, channel_secret: str):
        self.channel_access_token = channel_access_token
        self.channel_secret = channel_secret
        self._handler = WebhookHandler(channel_secret)
        self._api_client: Optional[ApiClient] = None
        self._messaging_api: Optional[MessagingApi] = None

    @property
    def api(self) -> MessagingApi:
        if self._messaging_api is None:
            configuration = Configuration(access_token=self.channel_access_token)
            self._api_client = ApiClient(configuration)
            self._messaging_api = MessagingApi(self._api_client)
        return self._messaging_api

    def validate_signature(self, body: str, signature: str) -> bool:
        try:
            self._handler.parser.parse(body, signature)
            return True
        except InvalidSignatureError:
            return False

    def parse_events(self, body: str, signature: str) -> list[dict]:
        events: list[dict] = []
        payload = self._handler.parser.parse(body, signature)
        for event in payload.events:
            if not isinstance(event, MessageEvent):
                continue

            source = event.source
            user_id = getattr(source, "user_id", None)
            event_data = {
                "reply_token": getattr(event, "reply_token", None),
                "user_id": user_id,
                "event_type": event.type,
                "timestamp": event.timestamp,
            }

            if isinstance(event.message, TextMessageContent):
                event_data["message_type"] = "text"
                event_data["text"] = event.message.text
            elif isinstance(event.message, ImageMessageContent):
                event_data["message_type"] = "image"
                event_data["message_id"] = event.message.id
            elif isinstance(event.message, AudioMessageContent):
                event_data["message_type"] = "audio"
                event_data["message_id"] = event.message.id
            else:
                event_data["message_type"] = event.message.type

            events.append(event_data)

        return events

    def reply_text(self, reply_token: str, text: str) -> None:
        try:
            self.api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=text)],
                )
            )
        except Exception:
            logger.exception("Failed to send LINE reply")
            raise

    def push_text(self, user_id: str, text: str) -> None:
        try:
            self.api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=text)],
                )
            )
        except Exception:
            logger.exception("Failed to send LINE push message")
            raise

    def push_audio(self, user_id: str, original_content_url: str, duration: int) -> None:
        try:
            self.api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[
                        AudioMessage(
                            original_content_url=original_content_url,
                            duration=duration,
                        )
                    ],
                )
            )
        except Exception:
            logger.exception("Failed to send LINE audio message")
            raise

    def push_image(self, user_id: str, original_content_url: str, preview_image_url: str) -> None:
        try:
            self.api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[
                        ImageMessage(
                            original_content_url=original_content_url,
                            preview_image_url=preview_image_url,
                        )
                    ],
                )
            )
        except Exception:
            logger.exception("Failed to send LINE image message")
            raise

    def get_profile(self, user_id: str) -> Optional[dict]:
        try:
            profile = self.api.get_profile(user_id)
            return {
                "display_name": profile.display_name,
                "user_id": profile.user_id,
                "picture_url": profile.picture_url,
            }
        except Exception:
            logger.exception("Failed to get LINE profile")
            return None


def get_line_client_from_db(db_getter, team_agent_id=None) -> Optional[LineClient]:
    """Create a LineClient from the channel config stored in the database."""
    config = db_getter("line", team_agent_id=team_agent_id)
    if not config or not config.get("is_active"):
        return None
    cfg = config.get("config", {})
    access_token = cfg.get("channel_access_token", "").strip()
    secret = cfg.get("channel_secret", "").strip()
    if not access_token or not secret:
        return None
    return LineClient(channel_access_token=access_token, channel_secret=secret)
