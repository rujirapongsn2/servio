"""Agent handler for messaging channels (LINE, Facebook Messenger).

Takes incoming text messages, runs them through the OpenAI agent pipeline,
and returns the agent's text response.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from agents import Runner
from app.agent_execution import execution_scope, run_agent
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
    from app.chat_inputs import ChatInput
    try:
        text = ChatInput(message=text).message
    except ValueError:
        return "ข้อความไม่ถูกต้องหรือยาวเกินขนาดที่ระบบรองรับ"
    conversation = get_or_create_conversation(channel_type, user_id, team_agent_id)

    # Add user message to history
    conversation.append({"role": "user", "content": text})

    # Get the latest agent (may have been reassigned via handoffs)
    key = _conversation_key(channel_type, user_id, team_agent_id)
    agent = _conversations[key]["agent"]

    # Run agent
    try:
        with execution_scope(agent):
            output = await run_agent(agent, conversation)
        _conversations[key]["agent"] = output.last_agent
        # Retain tool calls, outputs and handoffs as well as assistant prose.
        from app.tool_execution import redact
        from app.agent_execution import runtime_secrets
        conversation[:] = redact(output.to_input_list(), runtime_secrets(agent))
        return redact(str(output.final_output or "").strip(), runtime_secrets(agent))

    except Exception:
        logger.warning("Agent run failed for %s", channel_type)
        return "ขออภัย ระบบขัดข้องชั่วคราว กรุณาลองใหม่อีกครั้ง"
