import asyncio
from typing import Dict, List, Optional, Any
from fastapi import WebSocket
from pydantic import BaseModel
import time
import uuid

class SessionInfo(BaseModel):
    session_id: str
    start_time: float
    last_message_time: float
    mode: str = "AI"  # "AI" or "MANUAL"
    source: str = "text_widget"  # "text_widget", "voice_widget", or "phone"
    last_message_preview: str = ""
    messages: List[Dict] = []
    intent_group: Optional[str] = None
    intent_color: Optional[str] = None
    team_agent_id: Optional[int] = None
    team_agent_name: Optional[str] = None
    channel_type: Optional[str] = None  # "web_widget", "line", "facebook", "phone"
    channel_user_id: Optional[str] = None
    api_key_id: Optional[int] = None

class SessionManager:
    def __init__(self):
        # Map session_id -> SessionInfo
        self.sessions: Dict[str, SessionInfo] = {}
        # Map session_id -> User WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        # Map session_id -> WebsocketHelper
        self.active_helpers: Dict[str, Any] = {}
        # Map session_id -> List[Admin WebSocket]
        self.admin_connections: Dict[str, List[WebSocket]] = {}
        # Dashboard admin websockets (viewing all sessions, no specific session_id)
        self.dashboard_admins: List[WebSocket] = []
        # Map admin websocket -> team_agent_id filter context
        self.admin_team_context: Dict[int, Optional[int]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        session_id: str,
        source: str = "text_widget",
        team_agent_id: Optional[int] = None,
        team_agent_name: Optional[str] = None,
        channel_type: Optional[str] = None,
        channel_user_id: Optional[str] = None,
        api_key_id: Optional[int] = None,
    ):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionInfo(
                session_id=session_id,
                start_time=time.time(),
                last_message_time=time.time(),
                source=source,
                team_agent_id=team_agent_id,
                team_agent_name=team_agent_name,
                channel_type=channel_type,
                channel_user_id=channel_user_id,
                api_key_id=api_key_id,
            )
        # Notify admins of new session
        await self.broadcast_sessions_list()

    def register_helper(self, session_id: str, helper: Any):
        self.active_helpers[session_id] = helper

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        if session_id in self.active_helpers:
            del self.active_helpers[session_id]
        if session_id in self.sessions:
            del self.sessions[session_id]
        # Notify admins of session removal
        asyncio.create_task(self.broadcast_sessions_list())

    async def connect_admin(
        self,
        websocket: WebSocket,
        session_id: Optional[str] = None,
        team_agent_id: Optional[int] = None,
    ):
        await websocket.accept()
        self.admin_team_context[id(websocket)] = team_agent_id
        if session_id:
            # Admin monitoring specific session
            if session_id not in self.admin_connections:
                self.admin_connections[session_id] = []

            # Force single connection per session to prevent duplicates
            self.admin_connections[session_id] = [websocket]
            # Send initial history if available
            if session_id in self.sessions:
                await websocket.send_json({
                    "type": "history",
                    "messages": self.sessions[session_id].messages
                })
        else:
            # Admin viewing dashboard (all sessions)
            if websocket not in self.dashboard_admins:
                self.dashboard_admins.append(websocket)
            # Send initial session list
            await self.broadcast_sessions_list()

    def disconnect_admin(self, websocket: WebSocket, session_id: Optional[str] = None):
        if session_id and session_id in self.admin_connections:
            if websocket in self.admin_connections[session_id]:
                self.admin_connections[session_id].remove(websocket)
        if websocket in self.dashboard_admins:
            self.dashboard_admins.remove(websocket)
        self.admin_team_context.pop(id(websocket), None)

    async def update_session(self, session_id: str, message: Dict, is_user: bool = True):
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.last_message_time = time.time()
            content = message.get("content", "")
            if isinstance(content, str):
                session.last_message_preview = content[:50]
            
            # Append to history
            msg_entry = {
                "role": "user" if is_user else "assistant",
                "content": content,
                "timestamp": time.time()
            }
            session.messages.append(msg_entry)
            
            # Broadcast to monitoring admins
            if session_id in self.admin_connections:
                for admin_ws in self.admin_connections[session_id]:
                    try:
                        await admin_ws.send_json({
                            "type": "new_message",
                            "message": msg_entry
                        })
                    except:
                        pass # Handle disconnects

            # Update dashboard
            await self.broadcast_sessions_list()

    async def broadcast_sessions_list(self):
        """Send session list summary to all dashboard admin websockets."""
        stale = []
        for admin_ws in self.dashboard_admins:
            try:
                team_agent_id = self.admin_team_context.get(id(admin_ws))
                # Send all sessions as a summary list (without full message history)
                session_list = []
                for s in self.sessions.values():
                    if team_agent_id is not None and s.team_agent_id != team_agent_id:
                        continue
                    session_list.append({
                        "session_id": s.session_id,
                        "start_time": s.start_time,
                        "last_message_time": s.last_message_time,
                        "mode": s.mode,
                        "source": s.source,
                        "last_message_preview": s.last_message_preview,
                        "intent_group": s.intent_group,
                        "intent_color": s.intent_color,
                        "team_agent_id": s.team_agent_id,
                        "team_agent_name": s.team_agent_name,
                        "channel_type": s.channel_type,
                    })
                await admin_ws.send_json({
                    "type": "sessions_list",
                    "sessions": session_list,
                })
            except Exception:
                stale.append(admin_ws)
        for ws in stale:
            if ws in self.dashboard_admins:
                self.dashboard_admins.remove(ws)
            self.admin_team_context.pop(id(ws), None)

    def get_all_sessions(self, team_agent_id: Optional[int] = None) -> List[SessionInfo]:
        sessions = list(self.sessions.values())
        if team_agent_id is not None:
            sessions = [session for session in sessions if session.team_agent_id == team_agent_id]
        return sessions

    def set_mode(self, session_id: str, mode: str):
        if session_id in self.sessions:
            self.sessions[session_id].mode = mode
            # Notify admins
            asyncio.create_task(self.broadcast_mode_update(session_id, mode))

    async def broadcast_mode_update(self, session_id: str, mode: str):
        if session_id in self.admin_connections:
            for admin_ws in self.admin_connections[session_id]:
                try:
                    await admin_ws.send_json({
                        "type": "mode_update",
                        "mode": mode
                    })
                except:
                    pass

    async def update_session_intent(self, session_id: str, group: str, color: str):
        if session_id in self.sessions:
            self.sessions[session_id].intent_group = group
            self.sessions[session_id].intent_color = color
            # Broadcast update to dashboard (which uses sessions list)
            await self.broadcast_sessions_list()

    async def send_to_user(self, session_id: str, message: str):
        if session_id in self.active_helpers:
            helper = self.active_helpers[session_id]
            await helper.send_admin_message(message)
            # Also update our local history tracking
            await self.update_session(session_id, {"content": message}, is_user=False)

    def get_intent_statistics(self, team_agent_id: Optional[int] = None) -> dict:
        """Get real-time intent distribution statistics from active sessions"""
        sessions = self.get_all_sessions(team_agent_id=team_agent_id)
        stats = {
            "total_active_sessions": len(sessions),
            "by_intent": {},
            "unclassified": 0,
            "timestamp": time.time()
        }

        # Count sessions by intent group
        for session_info in sessions:
            intent = session_info.intent_group
            if intent:
                stats["by_intent"][intent] = stats["by_intent"].get(intent, 0) + 1
            else:
                stats["unclassified"] += 1

        return stats

session_manager = SessionManager()
