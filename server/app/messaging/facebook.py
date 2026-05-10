"""Facebook Messenger Platform API client for processing incoming messages and sending replies."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

FACEBOOK_API_VERSION = "v18.0"
FACEBOOK_API_BASE = f"https://graph.facebook.com/{FACEBOOK_API_VERSION}"


class FacebookClient:
    def __init__(self, page_access_token: str, app_secret: Optional[str] = None):
        self.page_access_token = page_access_token
        self.app_secret = app_secret

    def verify_webhook(
        self, mode: str, verify_token: str, challenge: str, expected_token: str
    ) -> Optional[str]:
        if mode == "subscribe" and verify_token == expected_token:
            return challenge
        return None

    def parse_events(self, payload: dict) -> list[dict]:
        events: list[dict] = []
        for entry in payload.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender = messaging.get("sender", {})
                recipient = messaging.get("recipient", {})

                event_data = {
                    "sender_id": sender.get("id"),
                    "recipient_id": recipient.get("id"),
                    "timestamp": messaging.get("timestamp"),
                }

                if "message" in messaging:
                    message = messaging["message"]
                    mid = message.get("mid")
                    text = message.get("text")
                    attachments = message.get("attachments")

                    if attachments:
                        event_data["message_type"] = "attachments"
                        event_data["attachments"] = []
                        for att in attachments:
                            event_data["attachments"].append({
                                "type": att.get("type"),
                                "url": att.get("payload", {}).get("url"),
                            })
                    elif text:
                        event_data["message_type"] = "text"
                        event_data["text"] = text
                    else:
                        event_data["message_type"] = "unknown"

                    event_data["message_id"] = mid

                elif "postback" in messaging:
                    event_data["event_type"] = "postback"
                    event_data["payload"] = messaging["postback"].get("payload")
                    event_data["message_type"] = "postback"

                events.append(event_data)

        return events

    def send_text(self, recipient_id: str, text: str) -> dict:
        return self._call_send_api(recipient_id, {"message": {"text": text}})

    def send_image(self, recipient_id: str, image_url: str) -> dict:
        return self._call_send_api(
            recipient_id,
            {
                "message": {
                    "attachment": {
                        "type": "image",
                        "payload": {"url": image_url, "is_reusable": True},
                    }
                }
            },
        )

    def send_audio(self, recipient_id: str, audio_url: str) -> dict:
        return self._call_send_api(
            recipient_id,
            {
                "message": {
                    "attachment": {
                        "type": "audio",
                        "payload": {"url": audio_url, "is_reusable": True},
                    }
                }
            },
        )

    def send_sender_action(self, recipient_id: str, action: str) -> dict:
        """Send sender action: typing_on, typing_off, mark_seen."""
        return self._call_send_api(recipient_id, {"sender_action": action})

    def get_user_profile(self, user_id: str) -> Optional[dict]:
        try:
            resp = httpx.get(
                f"{FACEBOOK_API_BASE}/{user_id}",
                params={
                    "fields": "first_name,last_name,profile_pic",
                    "access_token": self.page_access_token,
                },
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.exception("Failed to get Facebook user profile")
            return None

    def _call_send_api(self, recipient_id: str, payload: dict) -> dict:
        body = {"recipient": {"id": recipient_id}, **payload}
        try:
            resp = httpx.post(
                f"{FACEBOOK_API_BASE}/me/messages",
                params={"access_token": self.page_access_token},
                json=body,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.exception("Failed to call Facebook Send API")
            raise


def get_facebook_client_from_db(db_getter, team_agent_id=None) -> Optional[FacebookClient]:
    config = db_getter("facebook", team_agent_id=team_agent_id)
    if not config or not config.get("is_active"):
        return None
    cfg = config.get("config", {})
    access_token = cfg.get("page_access_token", "").strip()
    if not access_token:
        return None
    return FacebookClient(
        page_access_token=access_token,
        app_secret=cfg.get("app_secret", "").strip() or None,
    )
