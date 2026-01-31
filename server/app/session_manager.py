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

    async def connect(self, websocket: WebSocket, session_id: str, source: str = "text_widget"):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionInfo(
                session_id=session_id,
                start_time=time.time(),
                last_message_time=time.time(),
                source=source
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

    async def connect_admin(self, websocket: WebSocket, session_id: Optional[str] = None):
        await websocket.accept()
        if session_id:
            # Admin monitoring specific session
            if session_id not in self.admin_connections:
                self.admin_connections[session_id] = []
            
            # Force single connection per session to prevent duplicates
            # This handles React Strict Mode (double connect) and zombie connections
            self.admin_connections[session_id] = [websocket]
            # Send initial history if available
            if session_id in self.sessions:
                await websocket.send_json({
                    "type": "history",
                    "messages": self.sessions[session_id].messages
                })
        else:
            # Admin viewing dashboard (all sessions)
            # We might want a separate list for dashboard admins
            pass

    def disconnect_admin(self, websocket: WebSocket, session_id: str):
        if session_id in self.admin_connections:
            if websocket in self.admin_connections[session_id]:
                self.admin_connections[session_id].remove(websocket)

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
        # This is a bit simplified. In a real app, we'd have a separate list of admins subscribed to the dashboard.
        # For now, we'll assume we handle dashboard updates via a separate mechanism or just polling.
        pass

    def get_all_sessions(self) -> List[SessionInfo]:
        return list(self.sessions.values())

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

    def get_intent_statistics(self) -> dict:
        """Get real-time intent distribution statistics from active sessions"""
        stats = {
            "total_active_sessions": len(self.sessions),
            "by_intent": {},
            "unclassified": 0,
            "timestamp": time.time()
        }

        # Count sessions by intent group
        for session_info in self.sessions.values():
            intent = session_info.intent_group
            if intent:
                stats["by_intent"][intent] = stats["by_intent"].get(intent, 0) + 1
            else:
                stats["unclassified"] += 1

        return stats

session_manager = SessionManager()
