"""
Database Operations Module (SQLAlchemy ORM)

This module provides database CRUD operations using SQLAlchemy ORM
for the Voice Agents SDK application. Refactored from raw SQL to ORM.
"""

import json
import bcrypt
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import select, update as sql_update, delete as sql_delete, func, and_, or_
from sqlalchemy.orm import selectinload

from app.db_config import get_db
from app.orm_models import (
    Admin, Agent, Tool, AgentTool, AgentHandoff,
    FileStore, FileStoreFile, VoIPProvider, ApiKey,
    Conversation, ConversationMessage, ConversationAnalytics, AnalyticsDailySummary
)


# ============================================================================
# Helper Functions
# ============================================================================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def get_db_connection():
    """
    Get a raw database connection (for compatibility with legacy code).
    Returns a connection with dict-like row factory.
    """
    import psycopg2
    import psycopg2.extras
    import os
    from sqlalchemy.engine.url import make_url

    # Prefer DATABASE_URL if provided (handles complex passwords like `/` or `@`)
    db_url = os.getenv("DATABASE_URL")

    if db_url:
        # Parse URL to safely handle special chars in password (/, @, etc.)
        parsed = make_url(db_url)
        connection = psycopg2.connect(
            dbname=parsed.database,
            user=parsed.username,
            password=parsed.password,
            host=parsed.host,
            port=parsed.port or "5432",
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    else:
        # Fallback to discrete vars
        connection = psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB", "voice_agents"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            host=os.getenv("POSTGRES_HOST", "postgres"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            cursor_factory=psycopg2.extras.RealDictCursor
        )
    return connection


def init_database():
    """Initialize the database with schema and default data"""
    from app.db_config import init_database as db_init
    db_init()


# ============================================================================
# Admin Operations
# ============================================================================

def get_admin_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get admin user by username"""
    with get_db() as db:
        admin = db.query(Admin).filter_by(username=username).first()
        if not admin:
            return None
        return {
            "id": admin.id,
            "username": admin.username,
            "password_hash": admin.password_hash,
            "created_at": admin.created_at.isoformat() if admin.created_at else None
        }


def update_admin_password(username: str, new_password: str) -> bool:
    """Update admin password"""
    with get_db() as db:
        admin = db.query(Admin).filter_by(username=username).first()
        if not admin:
            return False
        admin.password_hash = hash_password(new_password)
        return True


# ============================================================================
# Agent Operations
# ============================================================================

def get_all_agents() -> List[Dict[str, Any]]:
    """Get all agents with their tools and handoffs"""
    with get_db() as db:
        agents = db.query(Agent).options(
            selectinload(Agent.tools),
            selectinload(Agent.handoff_to)
        ).order_by(Agent.created_at.desc()).all()

        return [
            {
                "id": agent.id,
                "name": agent.name,
                "instructions": agent.instructions,
                "model": agent.model,
                "is_starting_agent": agent.is_starting_agent,
                "created_at": agent.created_at.isoformat() if agent.created_at else None,
                "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
                "tools": [
                    {
                        "id": tool.id,
                        "name": tool.name,
                        "type": tool.type,
                        "config": json.dumps(tool.config) if tool.config else None
                    }
                    for tool in agent.tools
                ],
                "handoffs": [
                    {
                        "id": h.id,
                        "name": h.name
                    }
                    for h in agent.handoff_to
                ]
            }
            for agent in agents
        ]


def get_agent_by_id(agent_id: int) -> Optional[Dict[str, Any]]:
    """Get a single agent by ID with tools and handoffs"""
    with get_db() as db:
        agent = db.query(Agent).options(
            selectinload(Agent.tools),
            selectinload(Agent.handoff_to)
        ).filter_by(id=agent_id).first()

        if not agent:
            return None

        return {
            "id": agent.id,
            "name": agent.name,
            "instructions": agent.instructions,
            "model": agent.model,
            "is_starting_agent": agent.is_starting_agent,
            "created_at": agent.created_at.isoformat() if agent.created_at else None,
            "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
            "tools": [
                {
                    "id": tool.id,
                    "name": tool.name,
                    "type": tool.type,
                    "config": json.dumps(tool.config) if tool.config else None
                }
                for tool in agent.tools
            ],
            "handoffs": [
                {
                    "id": h.id,
                    "name": h.name
                }
                for h in agent.handoff_to
            ]
        }


def create_agent(
    name: str,
    instructions: str,
    model: str,
    tool_ids: List[int],
    handoff_agent_ids: List[int],
    is_starting_agent: bool = False
) -> int:
    """Create a new agent"""
    with get_db() as db:
        # If this is a starting agent, unset other starting agents
        if is_starting_agent:
            db.query(Agent).update({"is_starting_agent": False})

        # Create agent
        agent = Agent(
            name=name,
            instructions=instructions,
            model=model,
            is_starting_agent=is_starting_agent,
            updated_at=datetime.utcnow()
        )
        db.add(agent)
        db.flush()  # Get ID without committing

        # Add tools
        for tool_id in tool_ids:
            agent_tool = AgentTool(agent_id=agent.id, tool_id=tool_id)
            db.add(agent_tool)

        # Add handoffs
        for handoff_id in handoff_agent_ids:
            handoff = AgentHandoff(from_agent_id=agent.id, to_agent_id=handoff_id)
            db.add(handoff)

        return agent.id


def update_agent(
    agent_id: int,
    name: str,
    instructions: str,
    model: str,
    tool_ids: List[int],
    handoff_agent_ids: List[int],
    is_starting_agent: bool = False
) -> bool:
    """Update an existing agent"""
    with get_db() as db:
        agent = db.query(Agent).filter_by(id=agent_id).first()
        if not agent:
            return False

        # If this is a starting agent, unset other starting agents
        if is_starting_agent:
            db.query(Agent).filter(Agent.id != agent_id).update({"is_starting_agent": False})

        # Update agent
        agent.name = name
        agent.instructions = instructions
        agent.model = model
        agent.is_starting_agent = is_starting_agent
        agent.updated_at = datetime.utcnow()

        # Remove old tools and handoffs
        db.query(AgentTool).filter_by(agent_id=agent_id).delete()
        db.query(AgentHandoff).filter_by(from_agent_id=agent_id).delete()

        # Add new tools
        for tool_id in tool_ids:
            agent_tool = AgentTool(agent_id=agent.id, tool_id=tool_id)
            db.add(agent_tool)

        # Add new handoffs
        for handoff_id in handoff_agent_ids:
            handoff = AgentHandoff(from_agent_id=agent.id, to_agent_id=handoff_id)
            db.add(handoff)

        return True


def delete_agent(agent_id: int) -> bool:
    """Delete an agent"""
    with get_db() as db:
        agent = db.query(Agent).filter_by(id=agent_id).first()
        if not agent:
            return False
        db.delete(agent)
        return True


# ============================================================================
# Tool Operations
# ============================================================================

def get_all_tools() -> List[Dict[str, Any]]:
    """Get all tools"""
    with get_db() as db:
        tools = db.query(Tool).order_by(Tool.type, Tool.name).all()
        return [
            {
                "id": tool.id,
                "name": tool.name,
                "type": tool.type,
                "config": json.dumps(tool.config) if tool.config else None,
                "created_at": tool.created_at.isoformat() if tool.created_at else None
            }
            for tool in tools
        ]


def get_tool_by_id(tool_id: int) -> Optional[Dict[str, Any]]:
    """Get a single tool by ID"""
    with get_db() as db:
        tool = db.query(Tool).filter_by(id=tool_id).first()
        if not tool:
            return None
        return {
            "id": tool.id,
            "name": tool.name,
            "type": tool.type,
            "config": json.dumps(tool.config) if tool.config else None,
            "created_at": tool.created_at.isoformat() if tool.created_at else None
        }


def create_custom_tool(name: str, config: Dict[str, Any], icon: str = "Wrench") -> int:
    """Create a custom API tool or MCP tool"""
    with get_db() as db:
        # Determine tool type from config
        tool_type = config.get("type", "custom_api")

        tool = Tool(
            name=name,
            type=tool_type,
            config=config
        )
        db.add(tool)
        db.flush()
        return tool.id


def update_custom_tool(tool_id: int, name: str, config: Dict[str, Any], icon: str = "Wrench") -> bool:
    """Update a custom API tool, MCP tool, or Gemini File Search tool"""
    with get_db() as db:
        tool = db.query(Tool).filter(
            Tool.id == tool_id,
            Tool.type.in_(["custom_api", "mcp_streamable_http", "gemini_file_search"])
        ).first()

        if not tool:
            return False

        # Determine tool type from config
        tool_type = config.get("type", "custom_api")

        tool.name = name
        tool.type = tool_type
        tool.config = config

        return True


def delete_custom_tool(tool_id: int) -> bool:
    """Delete a custom API tool, MCP tool, or Gemini File Search tool"""
    with get_db() as db:
        result = db.query(Tool).filter(
            Tool.id == tool_id,
            Tool.type.in_(["custom_api", "mcp_streamable_http", "gemini_file_search"])
        ).delete()
        return result > 0


# ============================================================================
# File Store Operations
# ============================================================================

def get_all_file_stores() -> List[Dict[str, Any]]:
    """Get all file stores"""
    with get_db() as db:
        stores = db.query(FileStore).order_by(FileStore.created_at.desc()).all()
        return [
            {
                "id": store.id,
                "name": store.name,
                "gemini_store_id": store.gemini_store_id,
                "display_name": store.display_name,
                "file_count": store.file_count,
                "created_at": store.created_at.isoformat() if store.created_at else None
            }
            for store in stores
        ]


def get_file_store_by_id(store_id: int) -> Optional[Dict[str, Any]]:
    """Get a single file store by ID"""
    with get_db() as db:
        store = db.query(FileStore).filter_by(id=store_id).first()
        if not store:
            return None
        return {
            "id": store.id,
            "name": store.name,
            "gemini_store_id": store.gemini_store_id,
            "display_name": store.display_name,
            "file_count": store.file_count,
            "created_at": store.created_at.isoformat() if store.created_at else None
        }


def get_file_store_by_gemini_id(gemini_store_id: str) -> Optional[Dict[str, Any]]:
    """Get a file store by Gemini store ID"""
    with get_db() as db:
        store = db.query(FileStore).filter_by(gemini_store_id=gemini_store_id).first()
        if not store:
            return None
        return {
            "id": store.id,
            "name": store.name,
            "gemini_store_id": store.gemini_store_id,
            "display_name": store.display_name,
            "file_count": store.file_count,
            "created_at": store.created_at.isoformat() if store.created_at else None
        }


def create_file_store(name: str, gemini_store_id: str, display_name: str = None) -> int:
    """Create a new file store"""
    with get_db() as db:
        store = FileStore(
            name=name,
            gemini_store_id=gemini_store_id,
            display_name=display_name
        )
        db.add(store)
        db.flush()
        return store.id


def delete_file_store(store_id: int) -> bool:
    """Delete a file store (cascades to files)"""
    with get_db() as db:
        store = db.query(FileStore).filter_by(id=store_id).first()
        if not store:
            return False
        db.delete(store)
        return True


def add_file_to_store(
    file_store_id: int,
    filename: str,
    original_filename: str,
    file_size: int
) -> int:
    """Add a file record to a store"""
    with get_db() as db:
        file_record = FileStoreFile(
            file_store_id=file_store_id,
            filename=filename,
            original_filename=original_filename,
            file_size=file_size
        )
        db.add(file_record)
        db.flush()

        # Update file count
        store = db.query(FileStore).filter_by(id=file_store_id).first()
        if store:
            store.file_count = db.query(FileStoreFile).filter_by(file_store_id=file_store_id).count()

        return file_record.id


def get_files_by_store(file_store_id: int) -> List[Dict[str, Any]]:
    """Get all files in a store"""
    with get_db() as db:
        files = db.query(FileStoreFile).filter_by(file_store_id=file_store_id).order_by(
            FileStoreFile.uploaded_at.desc()
        ).all()

        return [
            {
                "id": file.id,
                "file_store_id": file.file_store_id,
                "filename": file.filename,
                "original_filename": file.original_filename,
                "file_size": file.file_size,
                "uploaded_at": file.uploaded_at.isoformat() if file.uploaded_at else None
            }
            for file in files
        ]


def delete_file(file_id: int) -> bool:
    """Delete a file from a store"""
    with get_db() as db:
        file_record = db.query(FileStoreFile).filter_by(id=file_id).first()
        if not file_record:
            return False

        file_store_id = file_record.file_store_id
        db.delete(file_record)

        # Update file count
        store = db.query(FileStore).filter_by(id=file_store_id).first()
        if store:
            store.file_count = db.query(FileStoreFile).filter_by(file_store_id=file_store_id).count()

        return True


def update_file_count(file_store_id: int) -> bool:
    """Update file count for a store"""
    with get_db() as db:
        store = db.query(FileStore).filter_by(id=file_store_id).first()
        if not store:
            return False
        store.file_count = db.query(FileStoreFile).filter_by(file_store_id=file_store_id).count()
    return True


# ============================================================================
# VoIP Provider Operations
# ============================================================================

def get_all_voip_providers() -> List[Dict[str, Any]]:
    """Get all VoIP providers"""
    with get_db() as db:
        providers = db.query(VoIPProvider).order_by(VoIPProvider.created_at.desc()).all()
        return [
            {
                "id": provider.id,
                "name": provider.name,
                "type": provider.type,
                "config": provider.config,
                "is_active": provider.is_active,
                "created_at": provider.created_at.isoformat() if provider.created_at else None,
                "updated_at": provider.updated_at.isoformat() if provider.updated_at else None
            }
            for provider in providers
        ]


def get_voip_provider_by_id(provider_id: int) -> Optional[Dict[str, Any]]:
    """Get a single VoIP provider by ID"""
    with get_db() as db:
        provider = db.query(VoIPProvider).filter_by(id=provider_id).first()
        if not provider:
            return None
        return {
            "id": provider.id,
            "name": provider.name,
            "type": provider.type,
            "config": provider.config,
            "is_active": provider.is_active,
            "created_at": provider.created_at.isoformat() if provider.created_at else None,
            "updated_at": provider.updated_at.isoformat() if provider.updated_at else None
        }


def create_voip_provider(name: str, type: str, config: Dict[str, Any], is_active: bool = True) -> int:
    """Create a new VoIP provider"""
    with get_db() as db:
        provider = VoIPProvider(
            name=name,
            type=type,
            config=config,
            is_active=is_active,
            updated_at=datetime.utcnow()
        )
        db.add(provider)
        db.flush()
        return provider.id


def update_voip_provider(
    provider_id: int,
    name: str,
    type: str,
    config: Dict[str, Any],
    is_active: bool
) -> bool:
    """Update an existing VoIP provider"""
    with get_db() as db:
        provider = db.query(VoIPProvider).filter_by(id=provider_id).first()
        if not provider:
            return False

        provider.name = name
        provider.type = type
        provider.config = config
        provider.is_active = is_active
        provider.updated_at = datetime.utcnow()

        return True


def delete_voip_provider(provider_id: int) -> bool:
    """Delete a VoIP provider"""
    with get_db() as db:
        provider = db.query(VoIPProvider).filter_by(id=provider_id).first()
        if not provider:
            return False
        db.delete(provider)
        return True


def get_active_voip_config(provider_type: str = "twilio") -> Optional[Dict[str, Any]]:
    """Get the configuration of the active VoIP provider of a certain type"""
    with get_db() as db:
        provider = db.query(VoIPProvider).filter_by(type=provider_type, is_active=True).first()
        if not provider:
            return None
        return provider.config


# ============================================================================
# API Key Operations
# ============================================================================

def get_all_api_keys() -> List[Dict[str, Any]]:
    """Get all API keys"""
    with get_db() as db:
        keys = db.query(ApiKey).order_by(ApiKey.created_at.desc()).all()
        return [
            {
                "id": key.id,
                "name": key.name,
                "key": key.key,
                "is_active": key.is_active,
                "usage_count": key.usage_count,
                "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
                "expires_at": key.expires_at.isoformat() if key.expires_at else None,
                "created_by": key.created_by,
                "allowed_domains": key.allowed_domains,
                "created_at": key.created_at.isoformat() if key.created_at else None,
                "updated_at": key.updated_at.isoformat() if key.updated_at else None
            }
            for key in keys
        ]


def get_api_key_by_id(key_id: int) -> Optional[Dict[str, Any]]:
    """Get a single API key by ID"""
    with get_db() as db:
        key = db.query(ApiKey).filter_by(id=key_id).first()
        if not key:
            return None
        return {
            "id": key.id,
            "name": key.name,
            "key": key.key,
            "is_active": key.is_active,
            "usage_count": key.usage_count,
            "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
            "expires_at": key.expires_at.isoformat() if key.expires_at else None,
            "created_by": key.created_by,
            "allowed_domains": key.allowed_domains,
            "created_at": key.created_at.isoformat() if key.created_at else None,
            "updated_at": key.updated_at.isoformat() if key.updated_at else None
        }


def get_api_key_by_key(key_value: str) -> Optional[Dict[str, Any]]:
    """Get an API key by its key value (for validation)"""
    with get_db() as db:
        key = db.query(ApiKey).filter_by(key=key_value).first()
        if not key:
            return None
        return {
            "id": key.id,
            "name": key.name,
            "key": key.key,
            "is_active": key.is_active,
            "usage_count": key.usage_count,
            "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
            "expires_at": key.expires_at.isoformat() if key.expires_at else None,
            "created_by": key.created_by,
            "created_at": key.created_at.isoformat() if key.created_at else None,
            "updated_at": key.updated_at.isoformat() if key.updated_at else None
        }


def create_api_key(
    name: str,
    key: str,
    expires_at: Optional[datetime] = None,
    created_by: Optional[str] = None,
    allowed_domains: Optional[List[str]] = None
) -> int:
    """Create a new API key"""
    with get_db() as db:
        api_key = ApiKey(
            name=name,
            key=key,
            expires_at=expires_at,
            created_by=created_by,
            allowed_domains=allowed_domains
        )
        db.add(api_key)
        db.flush()
        return api_key.id


def update_api_key(
    key_id: int,
    name: Optional[str] = None,
    is_active: Optional[bool] = None,
    expires_at: Optional[datetime] = None,
    allowed_domains: Optional[List[str]] = None
) -> bool:
    """Update an API key"""
    with get_db() as db:
        api_key = db.query(ApiKey).filter_by(id=key_id).first()
        if not api_key:
            return False

        if name is not None:
            api_key.name = name
        if is_active is not None:
            api_key.is_active = is_active
        if expires_at is not None:
            api_key.expires_at = expires_at
        if allowed_domains is not None:
            api_key.allowed_domains = allowed_domains

        api_key.updated_at = datetime.utcnow()
        return True


def delete_api_key(key_id: int) -> bool:
    """Delete an API key"""
    with get_db() as db:
        api_key = db.query(ApiKey).filter_by(id=key_id).first()
        if not api_key:
            return False
        db.delete(api_key)
        return True


def increment_api_key_usage(key_value: str) -> bool:
    """Increment usage count and update last_used_at for an API key"""
    with get_db() as db:
        api_key = db.query(ApiKey).filter_by(key=key_value).first()
        if not api_key:
            return False
        api_key.usage_count += 1
        api_key.last_used_at = datetime.utcnow()
        return True


def validate_api_key(key_value: str, origin: Optional[str] = None) -> bool:
    """Validate an API key - check if it exists, is active, not expired, and origin is allowed"""
    with get_db() as db:
        api_key = db.query(ApiKey).filter_by(key=key_value).first()

        if not api_key:
            return False

        if not api_key.is_active:
            return False

        # Check expiration
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            return False

        # Check origin against allowed domains
        if api_key.allowed_domains and origin:
            # Extract domain from origin (e.g., "https://example.com" -> "example.com")
            import re
            origin_domain = re.sub(r'^https?://', '', origin).split(':')[0].split('/')[0]
            
            # Check if origin matches any allowed domain
            allowed = False
            for allowed_domain in api_key.allowed_domains:
                # Support wildcards and exact matches
                if allowed_domain == '*' or origin_domain == allowed_domain or origin_domain.endswith('.' + allowed_domain):
                    allowed = True
                    break
            
            if not allowed:
                return False
        elif api_key.allowed_domains and not origin:
            # If domains are restricted but no origin provided, reject
            return False

        return True


# ============================================================================
# Analytics Operations
# ============================================================================

def create_conversation(session_id: str, started_at: str) -> int:
    """Create a new conversation record"""
    with get_db() as db:
        conversation = Conversation(
            session_id=session_id,
            started_at=datetime.fromisoformat(started_at) if isinstance(started_at, str) else started_at
        )
        db.add(conversation)
        db.flush()
        return conversation.id


def get_conversation_by_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get conversation by session ID"""
    with get_db() as db:
        conversation = db.query(Conversation).filter_by(session_id=session_id).first()
        if not conversation:
            return None

        return {
            "id": conversation.id,
            "session_id": conversation.session_id,
            "started_at": conversation.started_at.isoformat() if conversation.started_at else None,
            "ended_at": conversation.ended_at.isoformat() if conversation.ended_at else None,
            "duration_seconds": conversation.duration_seconds,
            "total_messages": conversation.total_messages,
            "user_messages": conversation.user_messages,
            "agent_messages": conversation.agent_messages,
            "agents_involved": json.dumps(conversation.agents_involved) if conversation.agents_involved else None,
            "tools_used": json.dumps(conversation.tools_used) if conversation.tools_used else None,
            "outcome": conversation.outcome,
            "created_at": conversation.created_at.isoformat() if conversation.created_at else None
        }


def update_conversation(
    conversation_id: int,
    ended_at: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    total_messages: Optional[int] = None,
    user_messages: Optional[int] = None,
    agent_messages: Optional[int] = None,
    agents_involved: Optional[str] = None,
    tools_used: Optional[str] = None,
    outcome: Optional[str] = None
) -> bool:
    """Update conversation with metadata"""
    with get_db() as db:
        conversation = db.query(Conversation).filter_by(id=conversation_id).first()
        if not conversation:
            return False

        if ended_at is not None:
            conversation.ended_at = datetime.fromisoformat(ended_at) if isinstance(ended_at, str) else ended_at
        if duration_seconds is not None:
            conversation.duration_seconds = duration_seconds
        if total_messages is not None:
            conversation.total_messages = total_messages
        if user_messages is not None:
            conversation.user_messages = user_messages
        if agent_messages is not None:
            conversation.agent_messages = agent_messages
        if agents_involved is not None:
            conversation.agents_involved = json.loads(agents_involved) if isinstance(agents_involved, str) else agents_involved
        if tools_used is not None:
            conversation.tools_used = json.loads(tools_used) if isinstance(tools_used, str) else tools_used
        if outcome is not None:
            conversation.outcome = outcome

        return True


def update_enrichment_status(conversation_id: int, status: str) -> bool:
    """Update enrichment status for a conversation
    
    Args:
        conversation_id: ID of the conversation
        status: One of 'pending', 'processing', 'completed', 'failed', 'skipped'
    """
    with get_db() as db:
        conversation = db.query(Conversation).filter_by(id=conversation_id).first()
        if not conversation:
            return False
        conversation.enrichment_status = status
        return True


def add_conversation_message(
    conversation_id: int,
    role: str,
    content: str,
    timestamp: str,
    agent_name: Optional[str] = None,
    tool_calls: Optional[str] = None
) -> int:
    """Add a message to a conversation"""
    with get_db() as db:
        message = ConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            timestamp=datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp,
            agent_name=agent_name,
            tool_calls=json.loads(tool_calls) if tool_calls and isinstance(tool_calls, str) else tool_calls
        )
        db.add(message)
        db.flush()
        return message.id


def get_conversation_messages(conversation_id: int) -> List[Dict[str, Any]]:
    """Get all messages for a conversation"""
    with get_db() as db:
        messages = db.query(ConversationMessage).filter_by(conversation_id=conversation_id).order_by(
            ConversationMessage.timestamp.asc()
        ).all()

        return [
            {
                "id": message.id,
                "conversation_id": message.conversation_id,
                "role": message.role,
                "agent_name": message.agent_name,
                "content": message.content,
                "timestamp": message.timestamp.isoformat() if message.timestamp else None,
                "tool_calls": json.dumps(message.tool_calls) if message.tool_calls else None
            }
            for message in messages
        ]


def save_conversation_analytics(conversation_id: int, analytics_data: Dict[str, Any]) -> int:
    """Save LLM-generated analytics for a conversation"""
    with get_db() as db:
        analytics = ConversationAnalytics(
            conversation_id=conversation_id,
            overall_sentiment=analytics_data.get('overall_sentiment'),
            sentiment_score=analytics_data.get('sentiment_score'),
            sentiment_explanation=analytics_data.get('sentiment_explanation'),
            primary_topic=analytics_data.get('primary_topic'),
            topics=analytics_data.get('topics'),
            resolution_quality=analytics_data.get('resolution_quality'),
            agent_performance_score=analytics_data.get('agent_performance_score'),
            response_clarity_score=analytics_data.get('response_clarity_score'),
            empathy_score=analytics_data.get('empathy_score'),
            issues_identified=analytics_data.get('issues_identified'),
            customer_pain_points=analytics_data.get('customer_pain_points'),
            suggestions=analytics_data.get('suggestions'),
            customer_intent=analytics_data.get('customer_intent'),
            urgency_level=analytics_data.get('urgency_level'),
            follow_up_needed=analytics_data.get('follow_up_needed', False),
            follow_up_reason=analytics_data.get('follow_up_reason'),
            llm_model=analytics_data.get('llm_model'),
            analysis_version=analytics_data.get('analysis_version', 'v1.0')
        )
        db.add(analytics)
        db.flush()
        return analytics.id


# ============================================================================
# Maintenance Operations
# ============================================================================

def delete_all_conversations() -> Dict[str, int]:
    """Delete all conversation history (messages, analytics, summaries)."""
    with get_db() as db:
        deleted_messages = db.query(ConversationMessage).delete()
        deleted_analytics = db.query(ConversationAnalytics).delete()
        deleted_summaries = db.query(AnalyticsDailySummary).delete()
        deleted_conversations = db.query(Conversation).delete()

        return {
            "messages": deleted_messages,
            "analytics": deleted_analytics,
            "summaries": deleted_summaries,
            "conversations": deleted_conversations,
        }


def get_analytics_summary(period: str = 'today') -> Dict[str, Any]:
    """Get analytics summary for dashboard"""
    with get_db() as db:
        # Determine date filter based on period
        now = datetime.utcnow()
        if period == 'today':
            start_date = datetime(now.year, now.month, now.day)
        elif period == 'week':
            start_date = now - timedelta(days=7)
        elif period == 'month':
            start_date = now - timedelta(days=30)
        else:
            start_date = datetime(1970, 1, 1)  # All time

        # Total conversations
        total_conversations = db.query(Conversation).filter(
            and_(
                Conversation.started_at >= start_date,
                Conversation.enrichment_status != 'skipped'
            )
        ).count()

        # Resolution rate
        total_with_outcome = db.query(Conversation).filter(
            and_(
                Conversation.started_at >= start_date,
                Conversation.enrichment_status != 'skipped'
            )
        ).count()
        resolved_count = db.query(Conversation).filter(
            and_(
                Conversation.started_at >= start_date,
                Conversation.outcome == 'resolved',
                Conversation.enrichment_status != 'skipped'
            )
        ).count()
        resolution_rate = (resolved_count * 100.0 / total_with_outcome) if total_with_outcome > 0 else 0

        # Average messages per conversation
        avg_messages_result = db.query(func.avg(Conversation.total_messages)).filter(
            and_(
                Conversation.started_at >= start_date,
                Conversation.total_messages > 0,
                Conversation.enrichment_status != 'skipped'
            )
        ).scalar()
        avg_messages = float(avg_messages_result) if avg_messages_result else 0

        # Average sentiment score
        avg_sentiment_result = db.query(func.avg(ConversationAnalytics.sentiment_score)).join(
            Conversation
        ).filter(
            and_(
                Conversation.started_at >= start_date,
                ConversationAnalytics.sentiment_score.isnot(None),
                Conversation.enrichment_status != 'skipped'
            )
        ).scalar()
        avg_sentiment = float(avg_sentiment_result) if avg_sentiment_result else 0

        # Outcome breakdown
        outcome_results = db.query(
            Conversation.outcome,
            func.count(Conversation.id).label('count')
        ).filter(
            and_(
                Conversation.started_at >= start_date,
                Conversation.enrichment_status != 'skipped'
            )
        ).group_by(Conversation.outcome).all()
        outcome_breakdown = {row.outcome: row.count for row in outcome_results}

        # Sentiment breakdown
        sentiment_results = db.query(
            ConversationAnalytics.overall_sentiment,
            func.count(ConversationAnalytics.id).label('count')
        ).join(Conversation).filter(
            and_(
                Conversation.started_at >= start_date,
                ConversationAnalytics.overall_sentiment.isnot(None),
                Conversation.enrichment_status != 'skipped'
            )
        ).group_by(ConversationAnalytics.overall_sentiment).all()
        sentiment_breakdown = {row.overall_sentiment: row.count for row in sentiment_results}

        # Topic breakdown
        topic_results = db.query(
            ConversationAnalytics.primary_topic,
            func.count(ConversationAnalytics.id).label('count')
        ).join(Conversation).filter(
            and_(
                Conversation.started_at >= start_date,
                ConversationAnalytics.primary_topic.isnot(None),
                Conversation.enrichment_status != 'skipped'
            )
        ).group_by(ConversationAnalytics.primary_topic).order_by(
            func.count(ConversationAnalytics.id).desc()
        ).limit(10).all()
        topic_breakdown = {row.primary_topic: row.count for row in topic_results}

        return {
            'total_conversations': total_conversations,
            'resolution_rate': round(resolution_rate, 1),
            'avg_messages': round(avg_messages, 1),
            'avg_sentiment': round(avg_sentiment, 2),
            'outcome_breakdown': outcome_breakdown,
            'sentiment_breakdown': sentiment_breakdown,
            'topic_breakdown': topic_breakdown
        }


# Initialize database on module import
init_database()
