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
    JSON, Index, text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models"""
    pass


# ============================================================================
# Core Configuration Models
# ============================================================================

class IntentRule(Base):
    """Rules for manual intent classification overrides"""
    __tablename__ = "intent_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    keywords: Mapped[Optional[list]] = mapped_column(JSON, default=list)  # List of strings
    color: Mapped[str] = mapped_column(String(20), default="#999999")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Admin(Base):
    """Admin user accounts for authentication"""
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)



class LLMProvider(Base):
    """Configuration for external LLM providers (OpenAI compatible)"""
    __tablename__ = "llm_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key: Mapped[str] = mapped_column(String(500), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    agents: Mapped[List["Agent"]] = relationship(back_populates="llm_provider")


class Agent(Base):
    """AI agent configurations with instructions and model settings"""
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(100), default="gpt-4o-mini")
    llm_provider_id: Mapped[Optional[int]] = mapped_column(ForeignKey("llm_providers.id", ondelete="SET NULL"), nullable=True)
    is_starting_agent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    llm_provider: Mapped[Optional["LLMProvider"]] = relationship(back_populates="agents")
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
    owner_team_agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("team_agents.id"), nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(50), default="team")  # team, global
    created_by_admin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("admins.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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


class ChannelConfig(Base):
    """Messaging channel configuration"""
    __tablename__ = "channel_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    team_agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("team_agents.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_channel_configs_type_team", "type", "team_agent_id", unique=True),
    )


class ApiKey(Base):
    """API Keys for WebSocket authentication"""
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # Friendly name for the key
    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)  # The actual API key
    slug: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True, index=True)  # URL-friendly alias
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)  # Track usage
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # Optional expiration
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Admin username
    allowed_domains: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # Domain whitelist for Origin validation
    voice_response_enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # Enable TTS voice responses
    team_agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("team_agents.id"), nullable=True, index=True)
    channel_type: Mapped[str] = mapped_column(String(50), default="web_widget")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)




# ============================================================================
# Team Models
# ============================================================================

class TeamAgent(Base):
    """Primary entity for multi-team workspaces"""
    __tablename__ = "team_agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", index=True)  # active, archived
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TeamAgentMember(Base):
    """Maps Agents into a Team Agent"""
    __tablename__ = "team_agent_members"

    team_agent_id: Mapped[int] = mapped_column(ForeignKey("team_agents.id", ondelete="CASCADE"), primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(50), default="member")  # starting, member
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_team_agent_members_starting", "team_agent_id", unique=True,
              postgresql_where=text("role = 'starting'")),
    )


class TeamToolAssignment(Base):
    """Maps Tools into Team Agents with ownership/visibility"""
    __tablename__ = "team_tool_assignments"

    team_agent_id: Mapped[int] = mapped_column(ForeignKey("team_agents.id", ondelete="CASCADE"), primary_key=True)
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True)
    relationship: Mapped[str] = mapped_column(String(50), default="owned")  # owned, shared_in
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_team_tool_assignments_tool", "tool_id"),
    )


class TeamUserMembership(Base):
    """Maps admin users to Team Agents with roles"""
    __tablename__ = "team_user_memberships"

    admin_id: Mapped[int] = mapped_column(ForeignKey("admins.id", ondelete="CASCADE"), primary_key=True)
    team_agent_id: Mapped[int] = mapped_column(ForeignKey("team_agents.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(50), default="admin")  # owner, admin, operator, viewer
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ============================================================================
# OKF Knowledge Models
# ============================================================================

class OKFBundle(Base):
    """Local file-backed OKF bundle metadata.

    The markdown/YAML files on disk are the canonical source. This table only
    stores ownership and index metadata that can be rebuilt from those files.
    """
    __tablename__ = "okf_bundles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    okf_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="ready")
    concept_count: Mapped[int] = mapped_column(Integer, default=0)
    link_count: Mapped[int] = mapped_column(Integer, default=0)
    validation_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    owner_team_agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("team_agents.id"), nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(50), default="team")
    created_by_admin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("admins.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    concepts: Mapped[List["OKFConceptIndex"]] = relationship(
        back_populates="bundle",
        cascade="all, delete-orphan",
    )
    links: Mapped[List["OKFLinkIndex"]] = relationship(
        back_populates="bundle",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_okf_bundles_owner_visibility", "owner_team_agent_id", "visibility"),
    )


class OKFImportJob(Base):
    """Tracks background local knowledge import jobs for user-visible status."""
    __tablename__ = "okf_import_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    message: Mapped[str] = mapped_column(String(500), default="")
    bundle: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    warnings: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    team_agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("team_agents.id"), nullable=True, index=True)
    created_by_admin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("admins.id"), nullable=True)
    created_by_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_okf_import_jobs_team_created", "team_agent_id", "created_at"),
    )


class OKFConceptIndex(Base):
    """Search/filter cache for one OKF concept document."""
    __tablename__ = "okf_concept_index"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bundle_id: Mapped[int] = mapped_column(ForeignKey("okf_bundles.id", ondelete="CASCADE"), nullable=False, index=True)
    concept_id: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    type: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resource: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    search_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bundle: Mapped["OKFBundle"] = relationship(back_populates="concepts")

    __table_args__ = (
        Index("ix_okf_concepts_bundle_concept", "bundle_id", "concept_id", unique=True),
        Index("ix_okf_concepts_bundle_type", "bundle_id", "type"),
    )


class OKFLinkIndex(Base):
    """Directed markdown links discovered in an OKF bundle."""
    __tablename__ = "okf_link_index"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bundle_id: Mapped[int] = mapped_column(ForeignKey("okf_bundles.id", ondelete="CASCADE"), nullable=False, index=True)
    source_concept_id: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(1000), nullable=False)
    target_concept_id: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, index=True)
    label: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_external: Mapped[bool] = mapped_column(Boolean, default=False)
    is_citation: Mapped[bool] = mapped_column(Boolean, default=False)
    is_broken: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    bundle: Mapped["OKFBundle"] = relationship(back_populates="links")

    __table_args__ = (
        Index("ix_okf_links_bundle_source", "bundle_id", "source_concept_id"),
        Index("ix_okf_links_bundle_target", "bundle_id", "target_concept_id"),
    )


# ============================================================================
# Analytics Models
# ============================================================================

class Conversation(Base):
    """Conversation session tracking"""
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    team_agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("team_agents.id"), nullable=True, index=True)
    channel_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    channel_user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    api_key_id: Mapped[Optional[int]] = mapped_column(ForeignKey("api_keys.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    user_messages: Mapped[int] = mapped_column(Integer, default=0)
    agent_messages: Mapped[int] = mapped_column(Integer, default=0)
    agents_involved: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    tools_used: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    outcome: Mapped[str] = mapped_column(String(50), default="ongoing", index=True)
    enrichment_status: Mapped[str] = mapped_column(String(50), default="pending", index=True)  # pending, processing, completed, failed, skipped
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
