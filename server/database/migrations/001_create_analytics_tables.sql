-- Analytics Database Schema Migration
-- Created: 2025-01-28
-- Purpose: Add tables for conversation analytics and data collection

-- Conversations Table
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    duration_seconds INTEGER,
    total_messages INTEGER DEFAULT 0,
    user_messages INTEGER DEFAULT 0,
    agent_messages INTEGER DEFAULT 0,
    agents_involved TEXT, -- JSON array of agent names
    tools_used TEXT, -- JSON array of tool calls
    outcome TEXT DEFAULT 'ongoing', -- 'resolved', 'escalated', 'abandoned', 'ongoing'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_conversations_session_id ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_started_at ON conversations(started_at);
CREATE INDEX IF NOT EXISTS idx_conversations_outcome ON conversations(outcome);

-- Messages Table
CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL, -- 'user', 'agent', 'system'
    agent_name TEXT, -- Which agent sent this (if role=agent)
    content TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    tool_calls TEXT, -- JSON array of tool calls in this message
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- Index for faster message queries
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON conversation_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON conversation_messages(timestamp);

-- Enriched Analytics Table (LLM-generated)
CREATE TABLE IF NOT EXISTS conversation_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER UNIQUE NOT NULL,

    -- Sentiment Analysis
    overall_sentiment TEXT, -- 'positive', 'neutral', 'negative'
    sentiment_score REAL, -- -1.0 to 1.0
    sentiment_explanation TEXT,

    -- Topic Classification
    primary_topic TEXT, -- 'product_inquiry', 'technical_support', 'billing', 'complaint', etc.
    topics TEXT, -- JSON array of all topics

    -- Quality Metrics
    resolution_quality TEXT, -- 'excellent', 'good', 'fair', 'poor'
    agent_performance_score REAL, -- 0.0 to 1.0
    response_clarity_score REAL, -- 0.0 to 1.0
    empathy_score REAL, -- 0.0 to 1.0

    -- Issues & Insights
    issues_identified TEXT, -- JSON array of problems found
    customer_pain_points TEXT, -- JSON array
    suggestions TEXT, -- JSON array of improvement suggestions

    -- Business Intelligence
    customer_intent TEXT, -- 'purchase', 'support', 'inquiry', 'complaint', 'feedback'
    urgency_level TEXT, -- 'critical', 'high', 'medium', 'low'
    follow_up_needed BOOLEAN DEFAULT 0,
    follow_up_reason TEXT,

    -- Metadata
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    llm_model TEXT, -- Which model was used for analysis
    analysis_version TEXT DEFAULT 'v1.0', -- Version of analysis prompt/logic

    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- Index for analytics queries
CREATE INDEX IF NOT EXISTS idx_analytics_conversation_id ON conversation_analytics(conversation_id);
CREATE INDEX IF NOT EXISTS idx_analytics_sentiment ON conversation_analytics(overall_sentiment);
CREATE INDEX IF NOT EXISTS idx_analytics_topic ON conversation_analytics(primary_topic);

-- Daily/Hourly Aggregates (for performance)
CREATE TABLE IF NOT EXISTS analytics_daily_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE UNIQUE NOT NULL,
    total_conversations INTEGER DEFAULT 0,
    avg_duration_seconds INTEGER DEFAULT 0,
    avg_messages_per_conversation REAL DEFAULT 0,
    resolution_rate REAL DEFAULT 0, -- % resolved
    avg_sentiment_score REAL DEFAULT 0,
    positive_sentiment_count INTEGER DEFAULT 0,
    neutral_sentiment_count INTEGER DEFAULT 0,
    negative_sentiment_count INTEGER DEFAULT 0,
    top_topics TEXT, -- JSON array
    top_agents TEXT, -- JSON array with counts
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for date-based queries
CREATE INDEX IF NOT EXISTS idx_daily_summary_date ON analytics_daily_summary(date);
