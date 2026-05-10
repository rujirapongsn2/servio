"""Agent handler for messaging channels (LINE, Facebook Messenger).

Takes incoming text messages, runs them through the OpenAI agent pipeline,
and returns the agent's text response.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from agents import Runner
from app.agent_config import get_runtime_starting_agent
from app.utils import is_text_output

logger = logging.getLogger(__name__)

# In-memory conversation store. Keys are composite: "{team_agent_id}:{channel_type}:{user_id}".
# Each entry holds full conversation history (list of input/output items).
_conversations: Dict[str, Dict[str, Any]] = {}


def _conversation_key(channel_type: str, user_id: str, team_agent_id: Optional[int] = None) -> str:
    return f"{team_agent_id}:{channel_type}:{user_id}"


def get_or_create_conversation(
    channel_type: str, user_id: str, team_agent_id: Optional[int] = None
) -> list:
    """Return the full conversation history for a channel user."""
    key = _conversation_key(channel_type, user_id, team_agent_id)
    if key not in _conversations:
        _conversations[key] = {
            "history": [],
            "agent": get_runtime_starting_agent(team_agent_id),
            "team_agent_id": team_agent_id,
        }
    return _conversations[key]["history"]


def reset_conversation(
    channel_type: str, user_id: str, team_agent_id: Optional[int] = None
) -> None:
    key = _conversation_key(channel_type, user_id, team_agent_id)
    _conversations.pop(key, None)


async def handle_message(
    channel_type: str,
    user_id: str,
    text: str,
    team_agent_id: Optional[int] = None,
) -> str:
    """Process an incoming text message through the agent pipeline.

    Returns the agent's text response.
    """
    conversation = get_or_create_conversation(channel_type, user_id, team_agent_id)

    # Add user message to history
    conversation.append({"role": "user", "content": text})

    # Get the latest agent (may have been reassigned via handoffs)
    key = _conversation_key(channel_type, user_id, team_agent_id)
    agent = _conversations[key].get("agent", get_runtime_starting_agent(team_agent_id))

    # Run agent
    try:
        output = Runner.run_streamed(agent, conversation)

        response_parts: list[str] = []
        async for event in output.stream_events():
            if is_text_output(event):
                response_parts.append(event.data.delta)

        full_response = "".join(response_parts)

        # Track the latest agent in case of handoffs
        if output.last_agent:
            _conversations[key]["agent"] = output.last_agent

        # Add assistant response to history
        if full_response.strip():
            conversation.append({"role": "assistant", "content": full_response})

        return full_response.strip()

    except Exception:
        logger.exception("Agent run failed for %s user %s", channel_type, user_id)
        return "ขออภัย ระบบขัดข้องชั่วคราว กรุณาลองใหม่อีกครั้ง"
