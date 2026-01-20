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
    from app.orm_models import Base, Admin, Tool

    logger.info("Initializing database schema...")

    # Create all tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")

    # Insert default data
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

        # Insert builtin tools if not exists
        builtin_tools = [
            {
                "name": "WebSearchTool",
                "type": "builtin",
                "config": {"description": "Search the web for information"}
            },
        ]

        for tool_data in builtin_tools:
            exists = db.query(Tool).filter_by(name=tool_data["name"]).first()
            if not exists:
                tool = Tool(**tool_data)
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
                tool = Tool(**tool_data)
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
