"""
Analytics Service for Servio
Handles conversation recording and data enrichment
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
import asyncio

from app import database


class AnalyticsService:
    """Service for managing conversation analytics"""

    def __init__(self):
        self.session_id = None
        self.conversation_id = None
        self.started_at = None
        self.messages = []
        self.agents_used = set()
        self.tools_called = []

    def start_conversation(self, session_id: str) -> int:
        """Start tracking a new conversation"""
        self.session_id = session_id
        self.started_at = datetime.now().isoformat()
        self.messages = []
        self.agents_used = set()
        self.tools_called = []

        # Create conversation record in database
        self.conversation_id = database.create_conversation(
            session_id=session_id,
            started_at=self.started_at
        )

        return self.conversation_id

    def track_message(
        self,
        role: str,
        content: str,
        agent_name: Optional[str] = None,
        tool_calls: Optional[List[Dict]] = None
    ):
        """Track a message in the conversation"""
        if not self.conversation_id:
            return

        timestamp = datetime.now().isoformat()

        # Add to in-memory list
        message = {
            'role': role,
            'content': content,
            'agent_name': agent_name,
            'timestamp': timestamp,
            'tool_calls': tool_calls
        }
        self.messages.append(message)

        # Track agent usage
        if agent_name:
            self.agents_used.add(agent_name)

        # Save to database
        database.add_conversation_message(
            conversation_id=self.conversation_id,
            role=role,
            content=content,
            timestamp=timestamp,
            agent_name=agent_name,
            tool_calls=json.dumps(tool_calls) if tool_calls else None
        )

    def track_tool_call(self, tool_name: str, arguments: Dict[str, Any]):
        """Track a tool call"""
        self.tools_called.append({
            'tool': tool_name,
            'args': arguments,
            'timestamp': datetime.now().isoformat()
        })

    async def end_conversation(self, outcome: str = 'completed'):
        """End conversation and save final metadata"""
        if not self.conversation_id:
            return

        ended_at = datetime.now().isoformat()
        started = datetime.fromisoformat(self.started_at)
        ended = datetime.fromisoformat(ended_at)
        duration_seconds = int((ended - started).total_seconds())

        # Count messages
        total_messages = len(self.messages)
        user_messages = len([m for m in self.messages if m['role'] == 'user'])
        agent_messages = len([m for m in self.messages if m['role'] in ['assistant', 'agent']])

        # Update conversation record
        database.update_conversation(
            conversation_id=self.conversation_id,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            total_messages=total_messages,
            user_messages=user_messages,
            agent_messages=agent_messages,
            agents_involved=json.dumps(list(self.agents_used)),
            tools_used=json.dumps(self.tools_called),
            outcome=outcome
        )

        # Trigger enrichment in background (Phase 2)
        await self.enqueue_enrichment()

        # Reset state
        self.session_id = None
        self.conversation_id = None
        self.started_at = None
        self.messages = []
        self.agents_used = set()
        self.tools_called = []

    def get_conversation_data(self) -> Dict[str, Any]:
        """Get current conversation data"""
        if not self.conversation_id:
            return {}

        return {
            'session_id': self.session_id,
            'conversation_id': self.conversation_id,
            'started_at': self.started_at,
            'messages': self.messages,
            'agents_used': list(self.agents_used),
            'tools_called': self.tools_called
        }

    @staticmethod
    def get_summary(period: str = 'today') -> Dict[str, Any]:
        """Get analytics summary"""
        return database.get_analytics_summary(period)

    @staticmethod
    def prepare_conversation_for_analysis(conversation_id: int) -> Dict[str, Any]:
        """Prepare conversation data for LLM analysis (Phase 2)"""
        messages = database.get_conversation_messages(conversation_id)
        conversation = database.get_conversation_by_session(
            messages[0]['session_id'] if messages else ''
        )

        if not conversation:
            return {}

        return {
            'messages': [
                {
                    'role': m['role'],
                    'content': m['content'],
                    'agent': m.get('agent_name')
                }
                for m in messages
            ],
            'metadata': {
                'duration_seconds': conversation.get('duration_seconds'),
                'agents': json.loads(conversation.get('agents_involved', '[]')),
                'tools_used': json.loads(conversation.get('tools_used', '[]')),
                'outcome': conversation.get('outcome')
            }
        }

    # Enrichment methods (Phase 2)
    async def enqueue_enrichment(self):
        """Queue conversation for LLM enrichment"""
        if not self.conversation_id:
            return

        # Run enrichment in background without blocking
        asyncio.create_task(self.enrich_conversation(self.conversation_id))

    async def enrich_conversation(self, conversation_id: int):
        """Enrich conversation with LLM analysis"""
        try:
            from app.enrichment_service import get_enrichment_service

            enrichment_service = get_enrichment_service()
            await enrichment_service.enrich_conversation(conversation_id)

        except Exception as e:
            print(f"❌ Enrichment failed for conversation {conversation_id}: {e}")


# Singleton instance for easy import
_analytics_service = AnalyticsService()


def get_analytics_service() -> AnalyticsService:
    """Get the analytics service instance"""
    return _analytics_service
