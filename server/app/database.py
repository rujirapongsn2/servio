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
    FileStore, FileStoreFile, VoIPProvider, ChannelConfig, ApiKey,
    Conversation, ConversationMessage, ConversationAnalytics, AnalyticsDailySummary,
    IntentRule, TeamAgent, TeamAgentMember, TeamToolAssignment, TeamUserMembership
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
# Intent Rule Operations
# ============================================================================

def get_all_intent_rules() -> List[Dict[str, Any]]:
    """Get all intent rules"""
    with get_db() as db:
        rules = db.query(IntentRule).all()
        return [
            {
                "id": r.id,
                "group": r.group,
                "keywords": r.keywords or [],
                "color": r.color,
                "description": r.description
            }
            for r in rules
        ]

def get_intent_rule(rule_id: int) -> Optional[Dict[str, Any]]:
    """Get specific intent rule"""
    with get_db() as db:
        rule = db.query(IntentRule).filter(IntentRule.id == rule_id).first()
        if not rule:
            return None
        return {
            "id": rule.id,
            "group": rule.group,
            "keywords": rule.keywords or [],
            "color": rule.color,
            "description": rule.description
        }

def create_intent_rule(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new intent rule"""
    with get_db() as db:
        rule = IntentRule(
            group=data["group"],
            keywords=data.get("keywords", []),
            color=data.get("color", "#999999"),
            description=data.get("description")
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return {
            "id": rule.id,
            "group": rule.group,
            "keywords": rule.keywords or [],
            "color": rule.color,
            "description": rule.description
        }

def update_intent_rule(rule_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update an intent rule"""
    with get_db() as db:
        rule = db.query(IntentRule).filter(IntentRule.id == rule_id).first()
        if not rule:
            return None
        
        if "keywords" in updates:
            rule.keywords = updates["keywords"]
        if "color" in updates:
            rule.color = updates["color"]
        if "description" in updates:
            rule.description = updates["description"]
            
        db.commit()
        db.refresh(rule)
        return {
            "id": rule.id,
            "group": rule.group,
            "keywords": rule.keywords or [],
            "color": rule.color,
            "description": rule.description
        }


def delete_intent_rule(rule_id: int) -> bool:
    """Delete an intent rule"""
    with get_db() as db:
        rule = db.query(IntentRule).filter(IntentRule.id == rule_id).first()
        if not rule:
            return False
        db.delete(rule)
        db.commit()
        return True

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
            "is_super_admin": admin.is_super_admin,
            "created_at": admin.created_at.isoformat() if admin.created_at else None,
        }


def update_admin_password(username: str, new_password: str) -> bool:
    """Update admin password"""
    with get_db() as db:
        admin = db.query(Admin).filter_by(username=username).first()
        if not admin:
            return False
        admin.password_hash = hash_password(new_password)
        return True


ROLE_RANK = {
    "viewer": 1,
    "operator": 2,
    "admin": 3,
    "owner": 4,
}


def is_operator_only_user(username: str) -> bool:
    """Return True when user is limited to operator role across all memberships."""
    with get_db() as db:
        admin = db.query(Admin).filter_by(username=username).first()
        if not admin or admin.is_super_admin:
            return False
        memberships = db.query(TeamUserMembership).filter_by(admin_id=admin.id).all()
        if not memberships:
            return False
        return all(m.role == "operator" for m in memberships)


def has_any_team_role(username: str, min_role: str = "viewer") -> bool:
    """Return True when user has at least one membership at min_role or higher."""
    with get_db() as db:
        admin = db.query(Admin).filter_by(username=username).first()
        if not admin:
            return False
        if admin.is_super_admin:
            return True
        min_rank = ROLE_RANK.get(min_role, 1)
        memberships = db.query(TeamUserMembership).filter_by(admin_id=admin.id).all()
        return any(ROLE_RANK.get(m.role, 0) >= min_rank for m in memberships)


def can_manage_users(username: str) -> bool:
    """User management permission: super admin or explicit team admin role."""
    with get_db() as db:
        admin = db.query(Admin).filter_by(username=username).first()
        if not admin:
            return False
        if admin.is_super_admin:
            return True
        memberships = db.query(TeamUserMembership).filter_by(admin_id=admin.id).all()
        return any(m.role == "admin" for m in memberships)


def get_team_access_role(username: str, team_id: int) -> Optional[str]:
    """Return the user's role for a team.

    If no memberships exist yet, allow legacy single-admin installs to keep
    working as owner until memberships are configured.
    """
    with get_db() as db:
        membership_count = db.query(TeamUserMembership).count()
        if membership_count == 0:
            return "owner" if db.query(Admin).filter_by(username=username).first() else None

        admin = db.query(Admin).filter_by(username=username).first()
        if not admin:
            return None

        membership = db.query(TeamUserMembership).filter_by(
            admin_id=admin.id,
            team_agent_id=team_id,
        ).first()
        return membership.role if membership else None


def has_team_access(username: str, team_id: Optional[int], min_role: str = "viewer") -> bool:
    """Check team access for admin APIs. Super admins always have full access."""
    if team_id is None:
        return True
    # Super admin bypass
    admin = get_admin_by_username(username)
    if admin and admin.get("is_super_admin"):
        return True
    role = get_team_access_role(username, team_id)
    return ROLE_RANK.get(role or "", 0) >= ROLE_RANK.get(min_role, 1)


def has_exact_team_role(username: str, team_id: int, required_role: str) -> bool:
    """Check whether a user has exactly the specified team role.

    Super admins are treated as allowed for operational safety.
    """
    admin = get_admin_by_username(username)
    if admin and admin.get("is_super_admin"):
        return True
    role = get_team_access_role(username, team_id)
    return role == required_role


def get_accessible_team_ids(username: str, min_role: str = "viewer") -> Optional[List[int]]:
    """Return accessible team IDs, or None when legacy fallback grants all."""
    with get_db() as db:
        membership_count = db.query(TeamUserMembership).count()
        if membership_count == 0:
            return None

        admin = db.query(Admin).filter_by(username=username).first()
        if not admin:
            return []

        # Super admin sees all teams
        if admin.is_super_admin:
            return None

        min_rank = ROLE_RANK.get(min_role, 1)
        memberships = db.query(TeamUserMembership).filter_by(admin_id=admin.id).all()
        return [
            membership.team_agent_id
            for membership in memberships
            if ROLE_RANK.get(membership.role, 0) >= min_rank
        ]


def get_agent_team_ids(agent_id: int) -> List[int]:
    """Return IDs of teams that include the agent."""
    with get_db() as db:
        return [
            row.team_agent_id
            for row in db.query(TeamAgentMember.team_agent_id).filter_by(agent_id=agent_id).all()
        ]


def user_can_access_agent(
    username: str,
    agent_id: int,
    min_role: str = "viewer",
    team_agent_id: Optional[int] = None,
) -> bool:
    """Check whether a user can access an agent through team membership.

    If team_agent_id is provided, the agent must be a member of that team and
    the user must have the requested role on that team. Without team_agent_id,
    the user must have the requested role on at least one team containing the
    agent. Legacy installs with no memberships keep existing all-access behavior.
    """
    accessible_team_ids = get_accessible_team_ids(username, min_role=min_role)
    if accessible_team_ids is None:
        return True

    with get_db() as db:
        query = db.query(TeamAgentMember).filter_by(agent_id=agent_id)
        if team_agent_id is not None:
            query = query.filter_by(team_agent_id=team_agent_id)
        agent_team_ids = [row.team_agent_id for row in query.all()]

    if team_agent_id is not None and team_agent_id not in agent_team_ids:
        return False
    return any(team_id in accessible_team_ids for team_id in agent_team_ids)


# ============================================================================
# Agent Operations
# ============================================================================

def _team_member_agent_ids(db, team_agent_id: int) -> List[int]:
    return [
        row.agent_id
        for row in db.query(TeamAgentMember.agent_id).filter_by(team_agent_id=team_agent_id).all()
    ]


def _tool_available_to_team(db, tool_id: int, team_agent_id: int) -> bool:
    tool = db.query(Tool).filter_by(id=tool_id).first()
    if not tool:
        return False
    if tool.owner_team_agent_id == team_agent_id or tool.visibility == "global":
        return True
    return db.query(TeamToolAssignment).filter_by(
        team_agent_id=team_agent_id,
        tool_id=tool_id,
        relationship="shared_in",
    ).first() is not None


def get_all_agents(
    team_agent_id: Optional[int] = None,
    accessible_team_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """Get agents with their tools and handoffs.

    When team_agent_id is provided, only returns agents that are members of
    that team. This keeps handoff selection scoped to the active Team Agent.
    When accessible_team_ids is provided, returns agents from those teams only.
    """
    with get_db() as db:
        query = db.query(Agent).options(
            selectinload(Agent.tools),
            selectinload(Agent.handoff_to),
            selectinload(Agent.llm_provider)  # Added
        )
        if team_agent_id is not None:
            member_ids = _team_member_agent_ids(db, team_agent_id)
            if not member_ids:
                return []
            query = query.filter(Agent.id.in_(member_ids))
        elif accessible_team_ids is not None:
            if not accessible_team_ids:
                return []
            member_ids = [
                row.agent_id
                for row in db.query(TeamAgentMember.agent_id)
                .filter(TeamAgentMember.team_agent_id.in_(accessible_team_ids))
                .distinct()
                .all()
            ]
            if not member_ids:
                return []
            query = query.filter(Agent.id.in_(member_ids))
        agents = query.order_by(Agent.created_at.desc()).all()

        return [
            {
                "id": agent.id,
                "name": agent.name,
                "instructions": agent.instructions,
                "model": agent.model,
                "is_starting_agent": agent.is_starting_agent,
                "llm_provider": {  # Added
                    "id": agent.llm_provider.id,
                    "name": agent.llm_provider.name,
                    "base_url": agent.llm_provider.base_url,
                    "api_key": agent.llm_provider.api_key
                } if agent.llm_provider else None,
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
            selectinload(Agent.handoff_to),
            selectinload(Agent.llm_provider)  # Added
        ).filter_by(id=agent_id).first()

        if not agent:
            return None

        return {
            "id": agent.id,
            "name": agent.name,
            "instructions": agent.instructions,
            "model": agent.model,
            "is_starting_agent": agent.is_starting_agent,
            "llm_provider": {  # Added
                "id": agent.llm_provider.id,
                "name": agent.llm_provider.name,
                "base_url": agent.llm_provider.base_url,
                "api_key": agent.llm_provider.api_key
            } if agent.llm_provider else None,
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
    is_starting_agent: bool = False,
    llm_provider_id: Optional[int] = None,
    team_agent_id: Optional[int] = None,
) -> int:
    """Create a new agent"""
    with get_db() as db:
        datetime_tool = db.query(Tool).filter_by(name="DateTimeTool").first()
        effective_tool_ids = list(dict.fromkeys(tool_ids))
        if datetime_tool and datetime_tool.id not in effective_tool_ids:
            effective_tool_ids.append(datetime_tool.id)

        if team_agent_id is not None:
            if not db.query(TeamAgent).filter_by(id=team_agent_id).first():
                raise ValueError("Team Agent not found")
            invalid_tools = [
                tool_id for tool_id in effective_tool_ids
                if not _tool_available_to_team(db, tool_id, team_agent_id)
            ]
            if invalid_tools:
                raise ValueError("One or more tools are not available to this Team Agent")
            member_ids = set(_team_member_agent_ids(db, team_agent_id))
            invalid_handoffs = [agent_id for agent_id in handoff_agent_ids if agent_id not in member_ids]
            if invalid_handoffs:
                raise ValueError("Handoff agents must be members of the same Team Agent")

        # If this is a starting agent, unset other starting agents
        if is_starting_agent:
            db.query(Agent).update({"is_starting_agent": False})

        # Create agent
        agent = Agent(
            name=name,
            instructions=instructions,
            model=model,
            is_starting_agent=is_starting_agent,
            llm_provider_id=llm_provider_id,  # Added
            updated_at=datetime.utcnow()
        )
        db.add(agent)
        db.flush()  # Get ID without committing

        # Add tools
        for tool_id in effective_tool_ids:
            agent_tool = AgentTool(agent_id=agent.id, tool_id=tool_id)
            db.add(agent_tool)

        # Add handoffs
        for handoff_id in handoff_agent_ids:
            handoff = AgentHandoff(from_agent_id=agent.id, to_agent_id=handoff_id)
            db.add(handoff)

        if team_agent_id is not None:
            if is_starting_agent:
                db.query(TeamAgentMember).filter_by(
                    team_agent_id=team_agent_id,
                    role="starting",
                ).update({"role": "member"})
            db.add(TeamAgentMember(
                team_agent_id=team_agent_id,
                agent_id=agent.id,
                role="starting" if is_starting_agent else "member",
                sort_order=db.query(TeamAgentMember).filter_by(team_agent_id=team_agent_id).count(),
            ))

        return agent.id


def update_agent(
    agent_id: int,
    name: str,
    instructions: str,
    model: str,
    tool_ids: List[int],
    handoff_agent_ids: List[int],
    is_starting_agent: bool,
    llm_provider_id: Optional[int] = None,
    team_agent_id: Optional[int] = None,
) -> bool:
    """Update an existing agent"""
    with get_db() as db:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return False
        datetime_tool = db.query(Tool).filter_by(name="DateTimeTool").first()
        effective_tool_ids = list(dict.fromkeys(tool_ids))
        if datetime_tool and datetime_tool.id not in effective_tool_ids:
            effective_tool_ids.append(datetime_tool.id)
        if team_agent_id is not None:
            membership = db.query(TeamAgentMember).filter_by(
                team_agent_id=team_agent_id,
                agent_id=agent_id,
            ).first()
            if not membership:
                return False
            invalid_tools = [
                tool_id for tool_id in effective_tool_ids
                if not _tool_available_to_team(db, tool_id, team_agent_id)
            ]
            if invalid_tools:
                raise ValueError("One or more tools are not available to this Team Agent")
            member_ids = set(_team_member_agent_ids(db, team_agent_id))
            invalid_handoffs = [handoff_id for handoff_id in handoff_agent_ids if handoff_id not in member_ids]
            if invalid_handoffs:
                raise ValueError("Handoff agents must be members of the same Team Agent")

        # If setting as starting agent, unset others
        if is_starting_agent and not agent.is_starting_agent:
            db.query(Agent).update({"is_starting_agent": False})
        if team_agent_id is not None and is_starting_agent:
            db.query(TeamAgentMember).filter_by(
                team_agent_id=team_agent_id,
                role="starting",
            ).update({"role": "member"})
            membership.role = "starting"

        agent.name = name
        agent.instructions = instructions
        agent.model = model
        agent.is_starting_agent = is_starting_agent
        agent.llm_provider_id = llm_provider_id  # Added
        agent.updated_at = datetime.utcnow()

        # Remove old tools and handoffs
        db.query(AgentTool).filter_by(agent_id=agent_id).delete()
        db.query(AgentHandoff).filter_by(from_agent_id=agent_id).delete()

        # Add new tools
        for tool_id in effective_tool_ids:
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


def assign_tool_to_agent(
    agent_id: int,
    tool_id: int,
    team_agent_id: Optional[int] = None,
) -> bool:
    """Assign a tool to an agent if not already assigned."""
    with get_db() as db:
        agent = db.query(Agent).filter_by(id=agent_id).first()
        tool = db.query(Tool).filter_by(id=tool_id).first()
        if not agent or not tool:
            return False

        if team_agent_id is not None:
            membership = db.query(TeamAgentMember).filter_by(
                team_agent_id=team_agent_id,
                agent_id=agent_id,
            ).first()
            if not membership:
                return False
            if not _tool_available_to_team(db, tool_id, team_agent_id):
                return False

        existing = db.query(AgentTool).filter_by(agent_id=agent_id, tool_id=tool_id).first()
        if existing:
            return True

        db.add(AgentTool(agent_id=agent_id, tool_id=tool_id))
        return True


# ============================================================================
# Tool Operations
# ============================================================================

def get_all_tools(team_agent_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get tools, optionally filtered by team.

    When team_agent_id is provided, returns:
    - Tools owned by that team
    - Tools with visibility='global'
    - Tools shared into the team via team_tool_assignments

    When team_agent_id is None, returns Default Team tools rather than leaking
    private tools owned by every team.
    """
    with get_db() as db:
        if team_agent_id is None:
            default_team = db.query(TeamAgent).filter_by(slug="default").first()
            team_agent_id = default_team.id if default_team else None
        if team_agent_id is not None:
            # Owned by team
            owned = db.query(Tool).filter_by(owner_team_agent_id=team_agent_id).all()
            # Global tools
            global_tools = db.query(Tool).filter_by(visibility="global").all()
            # Shared into team
            shared_ids = [
                row.tool_id for row in
                db.query(TeamToolAssignment.tool_id).filter_by(
                    team_agent_id=team_agent_id, relationship="shared_in"
                ).all()
            ]
            shared = db.query(Tool).filter(Tool.id.in_(shared_ids)).all() if shared_ids else []
            tools = list({t.id: t for t in owned + global_tools + shared}.values())
        else:
            tools = db.query(Tool).filter_by(visibility="global").order_by(Tool.type, Tool.name).all()

        result = []
        for tool in tools:
            owner_team_name = None
            created_by_username = None
            if tool.owner_team_agent_id is not None:
                owner_team = db.query(TeamAgent).filter_by(id=tool.owner_team_agent_id).first()
                owner_team_name = owner_team.name if owner_team else None
            if tool.created_by_admin_id is not None:
                creator = db.query(Admin).filter_by(id=tool.created_by_admin_id).first()
                created_by_username = creator.username if creator else None
            usage_count = db.query(AgentTool).filter_by(tool_id=tool.id).count()
            result.append({
                "id": tool.id,
                "name": tool.name,
                "type": tool.type,
                "config": json.dumps(tool.config) if tool.config else None,
                "visibility": tool.visibility,
                "owner_team_agent_id": tool.owner_team_agent_id,
                "owner_team_name": owner_team_name,
                "created_by_admin_id": tool.created_by_admin_id,
                "created_by_username": created_by_username,
                "agent_usage_count": usage_count,
                "created_at": tool.created_at.isoformat() if tool.created_at else None,
                "updated_at": tool.updated_at.isoformat() if tool.updated_at else None,
            })
        return result


def get_tool_by_id(tool_id: int, team_agent_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Get a single tool by ID"""
    with get_db() as db:
        if team_agent_id is None:
            default_team = db.query(TeamAgent).filter_by(slug="default").first()
            team_agent_id = default_team.id if default_team else None
        tool = db.query(Tool).filter_by(id=tool_id).first()
        if not tool:
            return None
        if team_agent_id is not None and not _tool_available_to_team(db, tool_id, team_agent_id):
            return None
        owner_team_name = None
        created_by_username = None
        if tool.owner_team_agent_id is not None:
            owner_team = db.query(TeamAgent).filter_by(id=tool.owner_team_agent_id).first()
            owner_team_name = owner_team.name if owner_team else None
        if tool.created_by_admin_id is not None:
            creator = db.query(Admin).filter_by(id=tool.created_by_admin_id).first()
            created_by_username = creator.username if creator else None
        usage_count = db.query(AgentTool).filter_by(tool_id=tool.id).count()
        return {
            "id": tool.id,
            "name": tool.name,
            "type": tool.type,
            "config": json.dumps(tool.config) if tool.config else None,
            "visibility": tool.visibility,
            "owner_team_agent_id": tool.owner_team_agent_id,
            "owner_team_name": owner_team_name,
            "created_by_admin_id": tool.created_by_admin_id,
            "created_by_username": created_by_username,
            "agent_usage_count": usage_count,
            "created_at": tool.created_at.isoformat() if tool.created_at else None,
            "updated_at": tool.updated_at.isoformat() if tool.updated_at else None,
        }


def create_custom_tool(
    name: str, config: Dict[str, Any], icon: str = "Wrench",
    team_agent_id: Optional[int] = None,
    visibility: Optional[str] = None,
    created_by_username: Optional[str] = None,
) -> int:
    """Create a custom API tool or MCP tool, optionally owned by a team"""
    with get_db() as db:
        # Determine tool type from config
        tool_type = config.get("type", "custom_api")
        # Determine visibility: explicit > team-ownership > global fallback
        effective_visibility = visibility or ("team" if team_agent_id else "global")
        creator = db.query(Admin).filter_by(username=created_by_username).first() if created_by_username else None

        tool = Tool(
            name=name,
            type=tool_type,
            config=config,
            owner_team_agent_id=team_agent_id,
            visibility=effective_visibility,
            created_by_admin_id=creator.id if creator else None,
        )
        db.add(tool)
        db.flush()

        # Create team_tool_assignments row for ownership tracking
        if team_agent_id:
            assignment = TeamToolAssignment(
                team_agent_id=team_agent_id,
                tool_id=tool.id,
                relationship="owned",
            )
            db.add(assignment)

        return tool.id


def update_custom_tool(
    tool_id: int, name: str, config: Dict[str, Any], icon: str = "Wrench",
    team_agent_id: Optional[int] = None,
    visibility: Optional[str] = None,
) -> bool:
    """Update a custom API tool, MCP tool, or Gemini File Search tool.
    When team_agent_id is provided, only allows update if the team owns the tool.
    """
    with get_db() as db:
        query = db.query(Tool).filter(
            Tool.id == tool_id,
            Tool.type.in_(["custom_api", "mcp_streamable_http", "gemini_file_search"])
        )
        tool = query.first()

        if not tool:
            return False

        # Ownership check: only the owning team (or global/super admin) can edit
        if team_agent_id is None:
            default_team = db.query(TeamAgent).filter_by(slug="default").first()
            team_agent_id = default_team.id if default_team else None
        if tool.owner_team_agent_id is not None and tool.owner_team_agent_id != team_agent_id:
            return False

        # Determine tool type from config
        tool_type = config.get("type", "custom_api")

        tool.name = name
        tool.type = tool_type
        tool.config = config
        if visibility is not None:
            tool.visibility = visibility
        tool.updated_at = datetime.utcnow()

        return True


def delete_custom_tool(tool_id: int, team_agent_id: Optional[int] = None) -> bool:
    """Delete a custom API tool, MCP tool, or Gemini File Search tool.
    When team_agent_id is provided, only allows delete if the team owns the tool.
    """
    with get_db() as db:
        tool = db.query(Tool).filter(
            Tool.id == tool_id,
            Tool.type.in_(["custom_api", "mcp_streamable_http", "gemini_file_search"])
        ).first()

        if not tool:
            return False

        # Ownership check
        if team_agent_id is None:
            default_team = db.query(TeamAgent).filter_by(slug="default").first()
            team_agent_id = default_team.id if default_team else None
        if tool.owner_team_agent_id is not None and tool.owner_team_agent_id != team_agent_id:
            return False

        db.delete(tool)
        return True


def set_tool_visibility(tool_id: int, visibility: str, team_agent_id: Optional[int] = None) -> bool:
    """Update a tool's visibility.

    When a team is provided, only that team's owned tools can be changed.
    """
    with get_db() as db:
        tool = db.query(Tool).filter_by(id=tool_id).first()
        if not tool:
            return False
        if team_agent_id is None:
            default_team = db.query(TeamAgent).filter_by(slug="default").first()
            team_agent_id = default_team.id if default_team else None
        if tool.owner_team_agent_id != team_agent_id:
            return False
        tool.visibility = visibility
        tool.updated_at = datetime.utcnow()
        return True


def share_tool_to_team(tool_id: int, team_id: int) -> bool:
    """Share a tool into a team (adds shared_in assignment)"""
    with get_db() as db:
        existing = db.query(TeamToolAssignment).filter_by(
            team_agent_id=team_id, tool_id=tool_id
        ).first()
        if existing:
            existing.relationship = "shared_in"
        else:
            assignment = TeamToolAssignment(
                team_agent_id=team_id,
                tool_id=tool_id,
                relationship="shared_in",
            )
            db.add(assignment)
        return True


def unshare_tool_from_team(tool_id: int, team_id: int) -> bool:
    """Remove a shared tool from a team"""
    with get_db() as db:
        db.query(TeamToolAssignment).filter_by(
            team_agent_id=team_id, tool_id=tool_id, relationship="shared_in"
        ).delete()
        return True


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
# Channel Config Operations
# ============================================================================

def _channel_to_dict(channel: ChannelConfig) -> Dict[str, Any]:
    return {
        "id": channel.id,
        "type": channel.type,
        "name": channel.name,
        "config": channel.config or {},
        "is_active": channel.is_active,
        "team_agent_id": channel.team_agent_id,
        "created_at": channel.created_at.isoformat() if channel.created_at else None,
        "updated_at": channel.updated_at.isoformat() if channel.updated_at else None,
    }


def get_all_channel_configs(team_agent_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with get_db() as db:
        query = db.query(ChannelConfig)
        if team_agent_id is not None:
            query = query.filter(ChannelConfig.team_agent_id == team_agent_id)
        channels = query.order_by(ChannelConfig.created_at.desc()).all()
        return [_channel_to_dict(channel) for channel in channels]


def get_channel_config(channel_type: str, team_agent_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    with get_db() as db:
        if team_agent_id is not None:
            channel = db.query(ChannelConfig).filter_by(
                type=channel_type,
                team_agent_id=team_agent_id,
            ).first()
            if channel:
                return _channel_to_dict(channel)

        channel = db.query(ChannelConfig).filter_by(
            type=channel_type,
            team_agent_id=None,
        ).first()
        if not channel:
            default_team = db.query(TeamAgent).filter_by(slug="default").first()
            if default_team:
                channel = db.query(ChannelConfig).filter_by(
                    type=channel_type,
                    team_agent_id=default_team.id,
                ).first()
        if not channel:
            return None
        return _channel_to_dict(channel)


def upsert_channel_config(
    channel_type: str,
    name: str,
    config: Dict[str, Any],
    is_active: bool,
    team_agent_id: Optional[int] = None,
) -> Dict[str, Any]:
    with get_db() as db:
        channel = db.query(ChannelConfig).filter_by(
            type=channel_type, team_agent_id=team_agent_id
        ).first()
        if not channel:
            channel = ChannelConfig(
                type=channel_type,
                name=name,
                config=config,
                is_active=is_active,
                team_agent_id=team_agent_id,
                updated_at=datetime.utcnow(),
            )
            db.add(channel)
            db.flush()
        else:
            channel.name = name
            channel.config = config
            channel.is_active = is_active
            channel.updated_at = datetime.utcnow()
        return _channel_to_dict(channel)


# ============================================================================
# API Key Operations
# ============================================================================

def get_all_api_keys(team_agent_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get API keys, optionally filtered by team"""
    with get_db() as db:
        query = db.query(ApiKey)
        if team_agent_id is not None:
            query = query.filter(ApiKey.team_agent_id == team_agent_id)
        keys = query.order_by(ApiKey.created_at.desc()).all()
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
                "voice_response_enabled": key.voice_response_enabled,
                "slug": key.slug,
                "team_agent_id": key.team_agent_id,
                "channel_type": key.channel_type,
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
            "voice_response_enabled": key.voice_response_enabled,
            "slug": key.slug,
            "team_agent_id": key.team_agent_id,
            "channel_type": key.channel_type,
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
            "allowed_domains": key.allowed_domains,
            "voice_response_enabled": key.voice_response_enabled,
            "slug": key.slug,
            "team_agent_id": key.team_agent_id,
            "channel_type": key.channel_type,
            "created_at": key.created_at.isoformat() if key.created_at else None,
            "updated_at": key.updated_at.isoformat() if key.updated_at else None
        }


def get_api_key_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Get an API key by its slug"""
    with get_db() as db:
        key = db.query(ApiKey).filter_by(slug=slug).first()
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
            "voice_response_enabled": key.voice_response_enabled,
            "slug": key.slug,
            "team_agent_id": key.team_agent_id,
            "channel_type": key.channel_type,
            "created_at": key.created_at.isoformat() if key.created_at else None,
            "updated_at": key.updated_at.isoformat() if key.updated_at else None
        }


def create_api_key(
    name: str,
    key: str,
    expires_at: Optional[datetime] = None,
    created_by: Optional[str] = None,
    allowed_domains: Optional[List[str]] = None,
    voice_response_enabled: bool = True,
    slug: Optional[str] = None,
    team_agent_id: Optional[int] = None,
    channel_type: Optional[str] = "web_widget",
) -> int:
    """Create a new API key"""
    import secrets
    import string

    # Generate a random 10-char slug if not provided
    if not slug:
        alphabet = string.ascii_lowercase + string.digits
        slug = ''.join(secrets.choice(alphabet) for _ in range(10))

    with get_db() as db:
        api_key = ApiKey(
            name=name,
            key=key,
            expires_at=expires_at,
            created_by=created_by,
            allowed_domains=allowed_domains,
            voice_response_enabled=voice_response_enabled,
            slug=slug,
            team_agent_id=team_agent_id,
            channel_type=channel_type,
        )
        db.add(api_key)
        db.flush()
        return api_key.id


def update_api_key(
    key_id: int,
    name: Optional[str] = None,
    is_active: Optional[bool] = None,
    expires_at: Optional[datetime] = None,
    allowed_domains: Optional[List[str]] = None,
    voice_response_enabled: Optional[bool] = None,
    team_agent_id: Optional[int] = None,
    channel_type: Optional[str] = None,
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
        if voice_response_enabled is not None:
            api_key.voice_response_enabled = voice_response_enabled
        if team_agent_id is not None:
            api_key.team_agent_id = team_agent_id
        if channel_type is not None:
            api_key.channel_type = channel_type

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


def validate_api_key(key_value: str, origin: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Validate an API key and return its record if valid, None otherwise"""
    with get_db() as db:
        api_key = db.query(ApiKey).filter_by(key=key_value).first()

        if not api_key:
            return None

        if not api_key.is_active:
            return None

        # Check expiration
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            return None

        # Check origin against allowed domains
        if api_key.allowed_domains:
            # If wildcard is allowed, skip origin check entirely
            if '*' in api_key.allowed_domains:
                pass
            elif origin:
                # Extract domain from origin (e.g., "https://example.com" -> "example.com")
                import re
                origin_domain = re.sub(r'^https?://', '', origin).split(':')[0].split('/')[0]

                # Check if origin matches any allowed domain
                allowed = False
                for allowed_domain in api_key.allowed_domains:
                    if origin_domain == allowed_domain or origin_domain.endswith('.' + allowed_domain):
                        allowed = True
                        break

                if not allowed:
                    return None
            else:
                # Domains are restricted but no origin provided
                return None

        # Return full API key record as dict
        return {
            "id": api_key.id,
            "name": api_key.name,
            "key": api_key.key,
            "slug": api_key.slug,
            "is_active": api_key.is_active,
            "voice_response_enabled": api_key.voice_response_enabled,
            "team_agent_id": api_key.team_agent_id,
            "channel_type": api_key.channel_type,
            "allowed_domains": api_key.allowed_domains,
        }


# ============================================================================
# Analytics Operations
# ============================================================================

def create_conversation(
    session_id: str,
    started_at: str,
    team_agent_id: Optional[int] = None,
    channel_type: Optional[str] = None,
    channel_user_id: Optional[str] = None,
    api_key_id: Optional[int] = None,
) -> int:
    """Create a new conversation record"""
    with get_db() as db:
        conversation = Conversation(
            session_id=session_id,
            started_at=datetime.fromisoformat(started_at) if isinstance(started_at, str) else started_at,
            team_agent_id=team_agent_id,
            channel_type=channel_type,
            channel_user_id=channel_user_id,
            api_key_id=api_key_id,
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


def get_analytics_summary(period: str = 'today', team_agent_id: Optional[int] = None) -> Dict[str, Any]:
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

        def conv_filters(*extra):
            filters = [
                Conversation.started_at >= start_date,
                Conversation.enrichment_status != 'skipped',
            ]
            if team_agent_id is not None:
                filters.append(Conversation.team_agent_id == team_agent_id)
            filters.extend(extra)
            return and_(*filters)

        # Total conversations
        total_conversations = db.query(Conversation).filter(
            conv_filters()
        ).count()

        # Resolution rate
        total_with_outcome = db.query(Conversation).filter(
            conv_filters()
        ).count()
        resolved_count = db.query(Conversation).filter(
            conv_filters(Conversation.outcome == 'resolved')
        ).count()
        resolution_rate = (resolved_count * 100.0 / total_with_outcome) if total_with_outcome > 0 else 0

        # Average messages per conversation
        avg_messages_result = db.query(func.avg(Conversation.total_messages)).filter(
            conv_filters(Conversation.total_messages > 0)
        ).scalar()
        avg_messages = float(avg_messages_result) if avg_messages_result else 0

        # Average sentiment score
        avg_sentiment_result = db.query(func.avg(ConversationAnalytics.sentiment_score)).join(
            Conversation
        ).filter(
            conv_filters(ConversationAnalytics.sentiment_score.isnot(None))
        ).scalar()
        avg_sentiment = float(avg_sentiment_result) if avg_sentiment_result else 0

        # Outcome breakdown
        outcome_results = db.query(
            Conversation.outcome,
            func.count(Conversation.id).label('count')
        ).filter(
            conv_filters()
        ).group_by(Conversation.outcome).all()
        outcome_breakdown = {row.outcome: row.count for row in outcome_results}

        # Sentiment breakdown
        sentiment_results = db.query(
            ConversationAnalytics.overall_sentiment,
            func.count(ConversationAnalytics.id).label('count')
        ).join(Conversation).filter(
            conv_filters(ConversationAnalytics.overall_sentiment.isnot(None))
        ).group_by(ConversationAnalytics.overall_sentiment).all()
        sentiment_breakdown = {row.overall_sentiment: row.count for row in sentiment_results}

        # Topic breakdown
        topic_results = db.query(
            ConversationAnalytics.primary_topic,
            func.count(ConversationAnalytics.id).label('count')
        ).join(Conversation).filter(
            conv_filters(ConversationAnalytics.primary_topic.isnot(None))
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


# ============================================================================
# Admin User Operations
# ============================================================================

def get_all_admins() -> List[Dict[str, Any]]:
    """Get all admin users with their team memberships"""
    with get_db() as db:
        admins = db.query(Admin).order_by(Admin.username).all()
        result = []
        for admin in admins:
            memberships = db.query(TeamUserMembership).filter_by(admin_id=admin.id).all()
            teams = []
            for m in memberships:
                team = db.query(TeamAgent).filter_by(id=m.team_agent_id).first()
                if team:
                    teams.append({
                        "team_id": team.id,
                        "team_name": team.name,
                        "role": m.role,
                    })
            result.append({
                "id": admin.id,
                "username": admin.username,
                "created_at": admin.created_at.isoformat() if admin.created_at else None,
                "teams": teams,
            })
        return result


def get_admin_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Get a single admin by ID"""
    with get_db() as db:
        admin = db.query(Admin).filter_by(id=user_id).first()
        if not admin:
            return None
        memberships = db.query(TeamUserMembership).filter_by(admin_id=admin.id).all()
        teams = []
        for m in memberships:
            team = db.query(TeamAgent).filter_by(id=m.team_agent_id).first()
            if team:
                teams.append({
                    "team_id": team.id,
                    "team_name": team.name,
                    "role": m.role,
                })
        return {
            "id": admin.id,
            "username": admin.username,
            "created_at": admin.created_at.isoformat() if admin.created_at else None,
            "teams": teams,
        }


def create_admin(
    username: str, password: str,
) -> int:
    """Create a new admin user"""
    with get_db() as db:
        admin = Admin(
            username=username,
            password_hash=hash_password(password),
        )
        db.add(admin)
        db.flush()
        return admin.id


def update_admin(
    user_id: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> bool:
    """Update an admin user"""
    with get_db() as db:
        admin = db.query(Admin).filter_by(id=user_id).first()
        if not admin:
            return False
        if username is not None:
            admin.username = username
        if password is not None:
            admin.password_hash = hash_password(password)
        return True


def delete_admin(user_id: int) -> bool:
    """Delete an admin user"""
    with get_db() as db:
        admin = db.query(Admin).filter_by(id=user_id).first()
        if not admin:
            return False
        if admin.username == "admin":
            raise ValueError("Default admin user cannot be deleted")

        owner_memberships = (
            db.query(TeamUserMembership, TeamAgent)
            .join(TeamAgent, TeamAgent.id == TeamUserMembership.team_agent_id)
            .filter(
                TeamUserMembership.admin_id == user_id,
                TeamUserMembership.role == "owner",
            )
            .all()
        )
        if owner_memberships:
            team_names = [team.name for _, team in owner_memberships]
            raise ValueError(
                "Cannot delete user while they are owner of Team Agent(s): "
                + ", ".join(team_names)
                + ". Delete those Team Agents first."
            )

        # Preserve remaining tools by detaching creator ownership from the user.
        db.query(Tool).filter(Tool.created_by_admin_id == user_id).update(
            {"created_by_admin_id": None, "updated_at": datetime.utcnow()},
            synchronize_session=False,
        )
        db.delete(admin)
        return True


def get_team_users(team_id: int) -> List[Dict[str, Any]]:
    """Get users and their roles for a team"""
    with get_db() as db:
        memberships = db.query(TeamUserMembership).filter_by(team_agent_id=team_id).all()
        result = []
        for m in memberships:
            admin = db.query(Admin).filter_by(id=m.admin_id).first()
            if admin:
                result.append({
                    "admin_id": admin.id,
                    "username": admin.username,
                    "role": m.role,
                })
        return result


def set_user_team_role(admin_id: int, team_id: int, role: Optional[str]) -> bool:
    """Add or update a user's role in a team. Set role=None to remove."""
    with get_db() as db:
        if role is None:
            db.query(TeamUserMembership).filter_by(
                admin_id=admin_id, team_agent_id=team_id
            ).delete()
            return True

        existing = db.query(TeamUserMembership).filter_by(
            admin_id=admin_id, team_agent_id=team_id
        ).first()
        if existing:
            existing.role = role
        else:
            membership = TeamUserMembership(
                admin_id=admin_id,
                team_agent_id=team_id,
                role=role,
            )
            db.add(membership)
        return True


def remove_user_from_team(admin_id: int, team_id: int) -> bool:
    """Remove a user from a team"""
    return set_user_team_role(admin_id, team_id, None)


# ============================================================================
# Team Agent Operations
# ============================================================================

def get_all_team_agents(username: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all team agents with member counts"""
    with get_db() as db:
        query = db.query(TeamAgent)
        if username is not None:
            team_ids = get_accessible_team_ids(username)
            if team_ids is not None:
                if not team_ids:
                    return []
                query = query.filter(TeamAgent.id.in_(team_ids))
        teams = query.order_by(TeamAgent.name).all()
        result = []
        for team in teams:
            member_count = db.query(TeamAgentMember).filter_by(team_agent_id=team.id).count()
            starting = db.query(TeamAgentMember).filter_by(
                team_agent_id=team.id, role="starting"
            ).first()
            owner_membership = (
                db.query(TeamUserMembership, Admin)
                .join(Admin, TeamUserMembership.admin_id == Admin.id)
                .filter(
                    TeamUserMembership.team_agent_id == team.id,
                    TeamUserMembership.role == "owner",
                )
                .first()
            )
            starting_name = None
            owner_username = None
            if starting:
                agent = db.query(Agent).filter_by(id=starting.agent_id).first()
                if agent:
                    starting_name = agent.name
            if owner_membership:
                _, owner_admin = owner_membership
                owner_username = owner_admin.username
            result.append({
                "id": team.id,
                "name": team.name,
                "slug": team.slug,
                "description": team.description,
                "status": team.status,
                "member_count": member_count,
                "starting_agent_name": starting_name,
                "owner_username": owner_username,
                "created_at": team.created_at.isoformat() if team.created_at else None,
                "updated_at": team.updated_at.isoformat() if team.updated_at else None,
            })
        return result


def get_team_agent_by_id(team_id: int) -> Optional[Dict[str, Any]]:
    """Get a team agent by ID with members"""
    with get_db() as db:
        team = db.query(TeamAgent).filter_by(id=team_id).first()
        if not team:
            return None
        members = db.query(TeamAgentMember).filter_by(team_agent_id=team_id).order_by(
            TeamAgentMember.sort_order
        ).all()
        member_list = []
        for m in members:
            agent = db.query(Agent).filter_by(id=m.agent_id).first()
            member_list.append({
                "agent_id": m.agent_id,
                "agent_name": agent.name if agent else "Unknown",
                "role": m.role,
                "sort_order": m.sort_order,
            })
        return {
            "id": team.id,
            "name": team.name,
            "slug": team.slug,
            "description": team.description,
            "status": team.status,
            "member_count": len(member_list),
            "members": member_list,
            "created_at": team.created_at.isoformat() if team.created_at else None,
            "updated_at": team.updated_at.isoformat() if team.updated_at else None,
        }


def get_team_agent_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Get a team agent by slug"""
    with get_db() as db:
        team = db.query(TeamAgent).filter_by(slug=slug).first()
        if not team:
            return None
        return get_team_agent_by_id(team.id)


def create_team_agent(
    name: str,
    slug: str,
    description: Optional[str] = None,
    created_by: Optional[str] = None,
) -> int:
    """Create a new team agent"""
    with get_db() as db:
        team = TeamAgent(name=name, slug=slug, description=description)
        db.add(team)
        db.flush()

        if created_by:
            admin = db.query(Admin).filter_by(username=created_by).first()
            if admin:
                db.add(TeamUserMembership(
                    admin_id=admin.id,
                    team_agent_id=team.id,
                    role="owner",
                ))
        return team.id


def update_team_agent(
    team_id: int,
    name: Optional[str] = None,
    slug: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
) -> bool:
    """Update a team agent"""
    with get_db() as db:
        team = db.query(TeamAgent).filter_by(id=team_id).first()
        if not team:
            return False
        if name is not None:
            team.name = name
        if slug is not None:
            team.slug = slug
        if description is not None:
            team.description = description
        if status is not None:
            team.status = status
        team.updated_at = datetime.utcnow()
        return True


def delete_team_agent(team_id: int) -> bool:
    """Delete a team agent"""
    with get_db() as db:
        team = db.query(TeamAgent).filter_by(id=team_id).first()
        if not team:
            return False
        default_team = db.query(TeamAgent).filter_by(slug="default").first()
        fallback_team_id = default_team.id if default_team and default_team.id != team_id else None

        member_agent_ids = [
            row.agent_id
            for row in db.query(TeamAgentMember.agent_id).filter_by(team_agent_id=team_id).all()
        ]
        owned_tools = db.query(Tool).filter_by(owner_team_agent_id=team_id).all()

        for tool in owned_tools:
            external_use_query = db.query(AgentTool).filter(AgentTool.tool_id == tool.id)
            if member_agent_ids:
                external_use_query = external_use_query.filter(~AgentTool.agent_id.in_(member_agent_ids))
            external_use_exists = external_use_query.first() is not None

            if tool.visibility == "global" and external_use_exists:
                tool.owner_team_agent_id = None
                tool.created_by_admin_id = None
                tool.updated_at = datetime.utcnow()
                db.query(TeamToolAssignment).filter_by(
                    team_agent_id=team_id,
                    tool_id=tool.id,
                ).delete(synchronize_session=False)
            else:
                db.delete(tool)

        if member_agent_ids:
            db.query(Agent).filter(Agent.id.in_(member_agent_ids)).delete(synchronize_session=False)

        # Reassign non-cascading references to avoid FK violations while preserving data history.
        db.query(ApiKey).filter_by(team_agent_id=team_id).update(
            {"team_agent_id": fallback_team_id},
            synchronize_session=False,
        )
        team_channels = db.query(ChannelConfig).filter_by(team_agent_id=team_id).all()
        for channel in team_channels:
            if fallback_team_id is None:
                channel.team_agent_id = None
                continue
            existing_fallback = db.query(ChannelConfig).filter_by(
                team_agent_id=fallback_team_id,
                type=channel.type,
            ).first()
            if existing_fallback:
                db.delete(channel)
            else:
                channel.team_agent_id = fallback_team_id
        db.query(Conversation).filter_by(team_agent_id=team_id).update(
            {"team_agent_id": fallback_team_id},
            synchronize_session=False,
        )

        db.delete(team)
        return True


def get_team_agent_members(team_id: int) -> List[Dict[str, Any]]:
    """Get all members of a team agent"""
    with get_db() as db:
        members = db.query(TeamAgentMember).filter_by(team_agent_id=team_id).order_by(
            TeamAgentMember.sort_order
        ).all()
        result = []
        for m in members:
            agent = db.query(Agent).filter_by(id=m.agent_id).first()
            result.append({
                "agent_id": m.agent_id,
                "agent_name": agent.name if agent else "Unknown",
                "role": m.role,
                "sort_order": m.sort_order,
            })
        return result


def set_team_agent_members(
    team_id: int, member_agent_ids: List[int], starting_agent_id: Optional[int] = None
) -> bool:
    """Set the members of a team agent, replacing existing members.

    Ensures the team has exactly one starting agent when it has members and
    removes handoff edges from team members to agents outside the team.
    """
    with get_db() as db:
        team = db.query(TeamAgent).filter_by(id=team_id).first()
        if not team:
            return False

        valid_agent_ids = [
            row.id for row in db.query(Agent.id).filter(Agent.id.in_(member_agent_ids)).all()
        ] if member_agent_ids else []
        member_agent_ids = list(dict.fromkeys(valid_agent_ids))
        if member_agent_ids and starting_agent_id not in member_agent_ids:
            starting_agent_id = member_agent_ids[0]
        if not member_agent_ids:
            starting_agent_id = None

        # Remove existing members
        db.query(TeamAgentMember).filter_by(team_agent_id=team_id).delete()

        # Add new members
        for sort_order, agent_id in enumerate(member_agent_ids):
            role = "starting" if agent_id == starting_agent_id else "member"
            member = TeamAgentMember(
                team_agent_id=team_id,
                agent_id=agent_id,
                role=role,
                sort_order=sort_order,
            )
            db.add(member)

        if member_agent_ids:
            db.query(AgentHandoff).filter(
                AgentHandoff.from_agent_id.in_(member_agent_ids),
                ~AgentHandoff.to_agent_id.in_(member_agent_ids),
            ).delete(synchronize_session=False)

        return True


def set_starting_agent(team_id: int, agent_id: int) -> bool:
    """Set the starting agent for a team"""
    with get_db() as db:
        team = db.query(TeamAgent).filter_by(id=team_id).first()
        if not team:
            return False

        # Verify agent is a member
        member = db.query(TeamAgentMember).filter_by(
            team_agent_id=team_id, agent_id=agent_id
        ).first()
        if not member:
            return False

        # Unset current starting
        db.query(TeamAgentMember).filter_by(
            team_agent_id=team_id, role="starting"
        ).update({"role": "member"})

        # Set new starting
        member.role = "starting"
        return True


def get_team_tools(team_id: int) -> List[Dict[str, Any]]:
    """Get tools available to a team (owned + shared_in + global)"""
    with get_db() as db:
        # Tools owned by this team
        owned = db.query(Tool).filter_by(owner_team_agent_id=team_id).all()
        # Global tools
        global_tools = db.query(Tool).filter_by(visibility="global").all()
        # Tools shared into this team via team_tool_assignments
        shared_ids = [
            row.tool_id for row in
            db.query(TeamToolAssignment.tool_id).filter_by(
                team_agent_id=team_id, relationship="shared_in"
            ).all()
        ]
        shared = db.query(Tool).filter(Tool.id.in_(shared_ids)).all() if shared_ids else []

        all_tools = {t.id: t for t in owned + global_tools + shared}
        return [
            {
                "id": t.id,
                "name": t.name,
                "type": t.type,
                "config": json.dumps(t.config) if t.config else None,
                "visibility": t.visibility,
                "owner_team_agent_id": t.owner_team_agent_id,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in all_tools.values()
        ]


def get_default_team_id() -> Optional[int]:
    """Get the ID of the Default Team"""
    with get_db() as db:
        team = db.query(TeamAgent).filter_by(slug="default").first()
        return team.id if team else None


# Initialize database on module import
init_database()
