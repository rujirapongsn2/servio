"""
SQLAlchemy ORM Models for Voice Agents SDK Application

This module defines all database models using SQLAlchemy 2.0 with typed mappings.

Tables:
- Core Configuration: admins, agents, tools, agent_tools, agent_handoffs, file_stores, file_store_files
- Analytics: conversations, conversation_messages, conversation_analytics, analytics_daily_summary
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String, Integer, Boolean, Text, Float, DateTime, ForeignKey,
    JSON, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models"""
    pass


# ============================================================================
# Core Configuration Models
# ============================================================================

class Admin(Base):
    """Admin user accounts for authentication"""
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Agent(Base):
    """AI agent configurations with instructions and model settings"""
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(100), default="gpt-4o-mini")
    is_starting_agent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tools: Mapped[List["Tool"]] = relationship(
        secondary="agent_tools",
        back_populates="agents",
        lazy="selectin"
    )
    handoff_to: Mapped[List["Agent"]] = relationship(
        secondary="agent_handoffs",
        primaryjoin="Agent.id==AgentHandoff.from_agent_id",
        secondaryjoin="Agent.id==AgentHandoff.to_agent_id",
        lazy="selectin",
        viewonly=True
    )


class Tool(Base):
    """Tool/function registry for agents (builtin, custom_api, mcp, gemini)"""
    __tablename__ = "tools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)  # builtin, custom_api, mcp, gemini
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    agents: Mapped[List["Agent"]] = relationship(
        secondary="agent_tools",
        back_populates="tools"
    )


class AgentTool(Base):
    """Many-to-many junction table between agents and tools"""
    __tablename__ = "agent_tools"

    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True)


class AgentHandoff(Base):
    """Agent transfer/handoff relationships"""
    __tablename__ = "agent_handoffs"

    from_agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)
    to_agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)


class FileStore(Base):
    """Gemini file search stores"""
    __tablename__ = "file_stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    gemini_store_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    file_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    files: Mapped[List["FileStoreFile"]] = relationship(
        back_populates="file_store",
        cascade="all, delete-orphan"
    )



class FileStoreFile(Base):
    """Files within file stores"""
    __tablename__ = "file_store_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_store_id: Mapped[int] = mapped_column(ForeignKey("file_stores.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    file_store: Mapped["FileStore"] = relationship(back_populates="files")


class VoIPProvider(Base):
    """VoIP Providers configuration (e.g. Twilio)"""
    __tablename__ = "voip_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="twilio")
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



# ============================================================================
# Analytics Models
# ============================================================================

class Conversation(Base):
    """Conversation session tracking"""
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    user_messages: Mapped[int] = mapped_column(Integer, default=0)
    agent_messages: Mapped[int] = mapped_column(Integer, default=0)
    agents_involved: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    tools_used: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    outcome: Mapped[str] = mapped_column(String(50), default="ongoing", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    messages: Mapped[List["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan"
    )
    analytics: Mapped[Optional["ConversationAnalytics"]] = relationship(
        back_populates="conversation",
        uselist=False,
        cascade="all, delete-orphan"
    )


class ConversationMessage(Base):
    """Individual messages within conversations"""
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    tool_calls: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class ConversationAnalytics(Base):
    """LLM-powered conversation insights and analytics"""
    __tablename__ = "conversation_analytics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)

    # Sentiment Analysis
    overall_sentiment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sentiment_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Topic Analysis
    primary_topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    topics: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Quality Metrics
    resolution_quality: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    agent_performance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    response_clarity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    empathy_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Issue Tracking
    issues_identified: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    customer_pain_points: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    suggestions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Business Intelligence
    customer_intent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    urgency_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    follow_up_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    follow_up_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    llm_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    analysis_version: Mapped[str] = mapped_column(String(50), default="v1.0")

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="analytics")


class AnalyticsDailySummary(Base):
    """Daily aggregated analytics metrics"""
    __tablename__ = "analytics_daily_summary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime] = mapped_column(DateTime, unique=True, nullable=False, index=True)
    total_conversations: Mapped[int] = mapped_column(Integer, default=0)
    avg_duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    avg_messages_per_conversation: Mapped[float] = mapped_column(Float, default=0.0)
    resolution_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    positive_sentiment_count: Mapped[int] = mapped_column(Integer, default=0)
    neutral_sentiment_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_sentiment_count: Mapped[int] = mapped_column(Integer, default=0)
    top_topics: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    top_agents: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
