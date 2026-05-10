"""
Database Configuration and Connection Management

This module provides SQLAlchemy database connection and session management
with connection pooling for the Voice Agents SDK application.
"""

import os
import bcrypt
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from contextlib import contextmanager
from typing import Generator
import logging

logger = logging.getLogger(__name__)

# Database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/voice_agents"
)

# Create engine with connection pooling
# For production: use connection pool
# For testing: use NullPool to avoid connection issues
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
    echo=os.getenv("SQL_ECHO", "false").lower() == "true"
)

# Session factory
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Provide a transactional scope for database operations.

    Usage:
        with get_db() as db:
            users = db.query(Admin).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()


def init_database():
    """
    Initialize database schema and default data.

    Creates all tables and inserts default admin user and builtin tools.
    """
    from app.orm_models import (
        Base, Admin, Tool, LLMProvider, TeamAgent, TeamAgentMember,
        TeamToolAssignment, TeamUserMembership, Agent, ApiKey, Conversation, ChannelConfig
    )

    logger.info("Initializing database schema...")

    # Create all tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")

    # [Fix] Explicitly add missing columns that SQLAlchemy create_all doesn't add to existing tables
    with engine.connect() as conn:
        # Check if voice_response_enabled exists in api_keys
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='api_keys' AND column_name='voice_response_enabled'"
        ))
        if not result.fetchone():
            logger.info("Adding missing column 'voice_response_enabled' to 'api_keys' table...")
            try:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN voice_response_enabled BOOLEAN DEFAULT TRUE"))
                conn.commit()
                logger.info("Column 'voice_response_enabled' added successfully")
            except Exception as e:
                logger.error(f"Failed to add column 'voice_response_enabled': {e}")

        # Check if slug exists in api_keys
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='api_keys' AND column_name='slug'"
        ))
        if not result.fetchone():
            logger.info("Adding missing column 'slug' to 'api_keys' table...")
            try:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN slug VARCHAR(50) UNIQUE"))
                conn.commit()
                logger.info("Column 'slug' added successfully")
            except Exception as e:
                logger.error(f"Failed to add column 'slug': {e}")

        # Check if llm_provider_id exists in agents
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='agents' AND column_name='llm_provider_id'"
        ))
        if not result.fetchone():
            logger.info("Adding missing column 'llm_provider_id' to 'agents' table...")
            try:
                conn.execute(text("ALTER TABLE agents ADD COLUMN llm_provider_id INTEGER REFERENCES llm_providers(id) ON DELETE SET NULL"))
                conn.commit()
                logger.info("Column 'llm_provider_id' added successfully")
            except Exception as e:
                logger.error(f"Failed to add column 'llm_provider_id': {e}")

        # Phase 1: Team Agent migration - add missing columns to existing tables
        # team_agent_id and channel_type on api_keys
        for col_name, col_type in [
            ("team_agent_id", "INTEGER REFERENCES team_agents(id)"),
            ("channel_type", "VARCHAR(50) DEFAULT 'web_widget'"),
        ]:
            result = conn.execute(text(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name='api_keys' AND column_name='{col_name}'"
            ))
            if not result.fetchone():
                logger.info(f"Adding missing column '{col_name}' to 'api_keys' table...")
                try:
                    conn.execute(text(f"ALTER TABLE api_keys ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                    logger.info(f"Column '{col_name}' added successfully")
                except Exception as e:
                    logger.error(f"Failed to add column '{col_name}': {e}")

        # New columns on conversations
        for col_name, col_type in [
            ("team_agent_id", "INTEGER REFERENCES team_agents(id)"),
            ("channel_type", "VARCHAR(50)"),
            ("channel_user_id", "VARCHAR(255)"),
            ("api_key_id", "INTEGER REFERENCES api_keys(id)"),
        ]:
            result = conn.execute(text(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name='conversations' AND column_name='{col_name}'"
            ))
            if not result.fetchone():
                logger.info(f"Adding missing column '{col_name}' to 'conversations' table...")
                try:
                    conn.execute(text(f"ALTER TABLE conversations ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                    logger.info(f"Column '{col_name}' added successfully")
                except Exception as e:
                    logger.error(f"Failed to add column '{col_name}': {e}")

        # New columns on tools
        for col_name, col_type in [
            ("owner_team_agent_id", "INTEGER REFERENCES team_agents(id)"),
            ("visibility", "VARCHAR(50) DEFAULT 'team'"),
            ("created_by_admin_id", "INTEGER REFERENCES admins(id)"),
            ("updated_at", "TIMESTAMP"),
        ]:
            result = conn.execute(text(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name='tools' AND column_name='{col_name}'"
            ))
            if not result.fetchone():
                logger.info(f"Adding missing column '{col_name}' to 'tools' table...")
                try:
                    conn.execute(text(f"ALTER TABLE tools ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                    logger.info(f"Column '{col_name}' added successfully")
                except Exception as e:
                    logger.error(f"Failed to add column '{col_name}': {e}")

        # RBAC: add is_super_admin to admins
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='admins' AND column_name='is_super_admin'"
        ))
        if not result.fetchone():
            logger.info("Adding missing column 'is_super_admin' to 'admins' table...")
            try:
                conn.execute(text("ALTER TABLE admins ADD COLUMN is_super_admin BOOLEAN DEFAULT FALSE"))
                conn.commit()
                # Set existing admin user as super admin
                conn.execute(text("UPDATE admins SET is_super_admin = TRUE WHERE username = 'admin'"))
                conn.commit()
                logger.info("Column 'is_super_admin' added; admin set as super_admin")
            except Exception as e:
                logger.error(f"Failed to add column 'is_super_admin': {e}")

        # Phase 4: Channel config team scoping - add team_agent_id column
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='channel_configs' AND column_name='team_agent_id'"
        ))
        if not result.fetchone():
            logger.info("Adding missing column 'team_agent_id' to 'channel_configs' table...")
            try:
                conn.execute(text(
                    "ALTER TABLE channel_configs ADD COLUMN team_agent_id INTEGER REFERENCES team_agents(id)"
                ))
                conn.commit()
                logger.info("Column 'team_agent_id' added to channel_configs")
            except Exception as e:
                logger.error(f"Failed to add column 'team_agent_id' to channel_configs: {e}")

        # Remove the pre-team unique constraint on type so each team can have its
        # own LINE/Facebook config, then enforce uniqueness per team.
        try:
            conn.execute(text("ALTER TABLE channel_configs DROP CONSTRAINT IF EXISTS channel_configs_type_key"))
            conn.execute(text("DROP INDEX IF EXISTS ix_channel_configs_type_team"))
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_channel_configs_type_team "
                "ON channel_configs(type, team_agent_id)"
            ))
            conn.commit()
        except Exception as e:
            logger.warning(f"Channel config team index migration skipped/failed: {e}")

        # Create indexes on new columns (IF NOT EXISTS for safety)
        for idx_name, idx_sql in [
            ("ix_api_keys_team_agent_id", "CREATE INDEX IF NOT EXISTS ix_api_keys_team_agent_id ON api_keys(team_agent_id)"),
            ("ix_conversations_team_agent_id", "CREATE INDEX IF NOT EXISTS ix_conversations_team_agent_id ON conversations(team_agent_id)"),
            ("ix_conversations_channel_type", "CREATE INDEX IF NOT EXISTS ix_conversations_channel_type ON conversations(channel_type)"),
            ("ix_tools_owner_team_agent_id", "CREATE INDEX IF NOT EXISTS ix_tools_owner_team_agent_id ON tools(owner_team_agent_id)"),
        ]:
            try:
                conn.execute(text(idx_sql))
                conn.commit()
            except Exception as e:
                logger.warning(f"Index {idx_name}: {e}")

    # Insert default data and run migration
    with get_db() as db:
        # Insert default admin if not exists
        admin_exists = db.query(Admin).filter_by(username="admin").first()
        if not admin_exists:
            password_hash = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            admin = Admin(
                username="admin",
                password_hash=password_hash
            )
            db.add(admin)
            logger.info("Default admin user created (username: admin, password: admin123)")
        else:
            logger.info("Admin user already exists")

        # Create Default Team if not exists
        default_team = db.query(TeamAgent).filter_by(slug="default").first()
        if not default_team:
            default_team = TeamAgent(
                name="Default Team",
                slug="default",
                description="Default team created during migration",
                status="active"
            )
            db.add(default_team)
            db.flush()
            logger.info("Default Team created (slug: default)")

            # Assign all existing agents to Default Team
            agents = db.query(Agent).all()
            starting_agent = None
            for idx, agent in enumerate(agents):
                role = "starting" if agent.is_starting_agent else "member"
                if agent.is_starting_agent:
                    starting_agent = agent
                member = TeamAgentMember(
                    team_agent_id=default_team.id,
                    agent_id=agent.id,
                    role=role,
                    sort_order=idx
                )
                db.add(member)
            logger.info(f"Assigned {len(agents)} existing agents to Default Team")

            # Backfill existing API keys with default team
            api_keys = db.query(ApiKey).filter(ApiKey.team_agent_id.is_(None)).all()
            for key in api_keys:
                key.team_agent_id = default_team.id
            if api_keys:
                logger.info(f"Backfilled {len(api_keys)} API keys to Default Team")

            # Backfill existing conversations with default team
            convs = db.query(Conversation).filter(Conversation.team_agent_id.is_(None)).all()
            for conv in convs:
                conv.team_agent_id = default_team.id
            if convs:
                logger.info(f"Backfilled {len(convs)} conversations to Default Team")

            # Assign existing custom/built-in tools to Default Team
            tools = db.query(Tool).all()
            for tool in tools:
                if tool.owner_team_agent_id is None:
                    if tool.type == "builtin":
                        tool.visibility = "global"
                    else:
                        tool.owner_team_agent_id = default_team.id
                        tool.visibility = "team"
            logger.info(f"Assigned {len(tools)} existing tools to Default Team (builtins set to global)")

            # Backfill channel configs to Default Team
            channels = db.query(ChannelConfig).filter(ChannelConfig.team_agent_id.is_(None)).all()
            for ch in channels:
                ch.team_agent_id = default_team.id
            if channels:
                logger.info(f"Backfilled {len(channels)} channel configs to Default Team")
        else:
            logger.info("Default Team already exists")

        # Always backfill channel configs for runs after migration
        channels = db.query(ChannelConfig).filter(ChannelConfig.team_agent_id.is_(None)).all()
        for ch in channels:
            ch.team_agent_id = default_team.id if default_team else None
        if channels:
            logger.info(f"Backfilled {len(channels)} channel configs to Default Team")

        # Keep legacy/global rows usable even when the default team was created in
        # a previous migration run.
        api_keys = db.query(ApiKey).filter(ApiKey.team_agent_id.is_(None)).all()
        for key in api_keys:
            key.team_agent_id = default_team.id
            if not key.channel_type:
                key.channel_type = "web_widget"
        if api_keys:
            logger.info(f"Backfilled {len(api_keys)} API keys to Default Team")

        convs = db.query(Conversation).filter(Conversation.team_agent_id.is_(None)).all()
        for conv in convs:
            conv.team_agent_id = default_team.id
        if convs:
            logger.info(f"Backfilled {len(convs)} conversations to Default Team")

        tools = db.query(Tool).all()
        changed_tools = 0
        default_admin = db.query(Admin).filter_by(username="admin").first() or db.query(Admin).order_by(Admin.id).first()
        for tool in tools:
            if tool.type == "builtin":
                if tool.owner_team_agent_id is None and default_team:
                    tool.owner_team_agent_id = default_team.id
                    changed_tools += 1
                if tool.visibility != "global":
                    tool.visibility = "global"
                    changed_tools += 1
            elif tool.owner_team_agent_id is None:
                tool.owner_team_agent_id = default_team.id
                tool.visibility = "team"
                changed_tools += 1
            if tool.created_by_admin_id is None and default_admin:
                tool.created_by_admin_id = default_admin.id
                changed_tools += 1
            if tool.owner_team_agent_id is not None:
                existing_assignment = db.query(TeamToolAssignment).filter_by(
                    team_agent_id=tool.owner_team_agent_id,
                    tool_id=tool.id,
                    relationship="owned",
                ).first()
                if not existing_assignment:
                    db.add(TeamToolAssignment(
                        team_agent_id=tool.owner_team_agent_id,
                        tool_id=tool.id,
                        relationship="owned",
                    ))
                    changed_tools += 1
        if changed_tools:
            logger.info(f"Backfilled {changed_tools} tools to Default Team/global visibility")

        if db.query(TeamUserMembership).count() == 0:
            admins = db.query(Admin).all()
            teams = db.query(TeamAgent).all()
            for admin in admins:
                for team in teams:
                    db.add(TeamUserMembership(
                        admin_id=admin.id,
                        team_agent_id=team.id,
                        role="owner",
                    ))
            if admins and teams:
                logger.info(f"Created owner memberships for {len(admins)} admin(s) across {len(teams)} team(s)")

        # Insert builtin tools if not exists
        builtin_tools = [
            {
                "name": "DateTimeTool",
                "type": "builtin",
                "config": {"description": "Get current server date and time with timezone"}
            },
            {
                "name": "WebSearchTool",
                "type": "builtin",
                "config": {"description": "Search the web for information"}
            },
        ]

        default_admin = db.query(Admin).filter_by(username="admin").first() or db.query(Admin).order_by(Admin.id).first()

        for tool_data in builtin_tools:
            exists = db.query(Tool).filter_by(name=tool_data["name"]).first()
            if not exists:
                tool = Tool(
                    **tool_data,
                    owner_team_agent_id=default_team.id if default_team else None,
                    visibility="global",
                    created_by_admin_id=default_admin.id if default_admin else None,
                )
                db.add(tool)
                logger.info(f"Builtin tool '{tool_data['name']}' created")

        # Insert default custom tools
        custom_tools = [
            {
                "name": "get_softnix_info",
                "type": "custom_api",
                "config": {
                    "description": "Get information about Softnix products, services, pricing, and company information from the Softnix GenAI knowledge base. Supports Thai language queries with automatic enrichment.",
                    "api_type": "softnix"
                }
            },
        ]

        for tool_data in custom_tools:
            exists = db.query(Tool).filter_by(name=tool_data["name"]).first()
            if not exists:
                tool = Tool(
                    **tool_data,
                    owner_team_agent_id=default_team.id if default_team else None,
                    visibility="team",
                    created_by_admin_id=default_admin.id if default_admin else None,
                )
                db.add(tool)
                logger.info(f"Custom tool '{tool_data['name']}' created")

        logger.info("Database initialization completed")


def test_connection():
    """Test database connection and return status."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            logger.info(f"Database connection successful: {version}")
            return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
