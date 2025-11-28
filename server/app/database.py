import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
import bcrypt

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

DATABASE_PATH = "agents.db"


def get_db_connection():
    """Get a database connection with row factory"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize the database with schema and default admin user"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create admins table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create agents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            instructions TEXT NOT NULL,
            model TEXT NOT NULL DEFAULT 'gpt-4o-mini',
            is_starting_agent BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create tools table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL,
            config TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create agent_tools junction table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_tools (
            agent_id INTEGER,
            tool_id INTEGER,
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
            FOREIGN KEY (tool_id) REFERENCES tools(id) ON DELETE CASCADE,
            PRIMARY KEY (agent_id, tool_id)
        )
    """)

    # Create agent_handoffs junction table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_handoffs (
            from_agent_id INTEGER,
            to_agent_id INTEGER,
            FOREIGN KEY (from_agent_id) REFERENCES agents(id) ON DELETE CASCADE,
            FOREIGN KEY (to_agent_id) REFERENCES agents(id) ON DELETE CASCADE,
            PRIMARY KEY (from_agent_id, to_agent_id)
        )
    """)

    # Create file_stores table for Gemini File Search
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            gemini_store_id TEXT UNIQUE NOT NULL,
            display_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_count INTEGER DEFAULT 0
        )
    """)

    # Create file_store_files table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_store_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_store_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            file_size INTEGER,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (file_store_id) REFERENCES file_stores(id) ON DELETE CASCADE
        )
    """)

    # Create analytics tables
    # Conversations Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            started_at TIMESTAMP NOT NULL,
            ended_at TIMESTAMP,
            duration_seconds INTEGER,
            total_messages INTEGER DEFAULT 0,
            user_messages INTEGER DEFAULT 0,
            agent_messages INTEGER DEFAULT 0,
            agents_involved TEXT,
            tools_used TEXT,
            outcome TEXT DEFAULT 'ongoing',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session_id ON conversations(session_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_started_at ON conversations(started_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_outcome ON conversations(outcome)")

    # Messages Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            agent_name TEXT,
            content TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            tool_calls TEXT,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON conversation_messages(conversation_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON conversation_messages(timestamp)")

    # Enriched Analytics Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER UNIQUE NOT NULL,
            overall_sentiment TEXT,
            sentiment_score REAL,
            sentiment_explanation TEXT,
            primary_topic TEXT,
            topics TEXT,
            resolution_quality TEXT,
            agent_performance_score REAL,
            response_clarity_score REAL,
            empathy_score REAL,
            issues_identified TEXT,
            customer_pain_points TEXT,
            suggestions TEXT,
            customer_intent TEXT,
            urgency_level TEXT,
            follow_up_needed BOOLEAN DEFAULT 0,
            follow_up_reason TEXT,
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            llm_model TEXT,
            analysis_version TEXT DEFAULT 'v1.0',
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_analytics_conversation_id ON conversation_analytics(conversation_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_analytics_sentiment ON conversation_analytics(overall_sentiment)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_analytics_topic ON conversation_analytics(primary_topic)")

    # Daily Summary Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics_daily_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE UNIQUE NOT NULL,
            total_conversations INTEGER DEFAULT 0,
            avg_duration_seconds INTEGER DEFAULT 0,
            avg_messages_per_conversation REAL DEFAULT 0,
            resolution_rate REAL DEFAULT 0,
            avg_sentiment_score REAL DEFAULT 0,
            positive_sentiment_count INTEGER DEFAULT 0,
            neutral_sentiment_count INTEGER DEFAULT 0,
            negative_sentiment_count INTEGER DEFAULT 0,
            top_topics TEXT,
            top_agents TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_summary_date ON analytics_daily_summary(date)")

    # Insert default admin user if not exists
    cursor.execute("SELECT COUNT(*) FROM admins WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        password_hash = hash_password("admin123")
        cursor.execute(
            "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
            ("admin", password_hash)
        )

    # Insert built-in tools if not exists
    builtin_tools = [
        ("get_past_orders", "builtin", json.dumps({"description": "Get past orders from the system"})),
        ("submit_refund_request", "builtin", json.dumps({"description": "Submit a refund request for an order"})),
        ("WebSearchTool", "builtin", json.dumps({"description": "Search the web for information"})),
        ("get_softnix_info", "builtin", json.dumps({"description": "Get information about Softnix products and services"})),
    ]

    for tool_name, tool_type, config in builtin_tools:
        cursor.execute("SELECT COUNT(*) FROM tools WHERE name = ?", (tool_name,))
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO tools (name, type, config) VALUES (?, ?, ?)",
                (tool_name, tool_type, config)
            )

    conn.commit()
    conn.close()


# Admin operations
def get_admin_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get admin user by username"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admins WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_admin_password(username: str, new_password: str) -> bool:
    """Update admin password"""
    conn = get_db_connection()
    cursor = conn.cursor()
    password_hash = hash_password(new_password)
    cursor.execute(
        "UPDATE admins SET password_hash = ? WHERE username = ?",
        (password_hash, username)
    )
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


# Agent operations
def get_all_agents() -> List[Dict[str, Any]]:
    """Get all agents with their tools and handoffs"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM agents ORDER BY created_at DESC")
    agents = [dict(row) for row in cursor.fetchall()]

    for agent in agents:
        # Get tools
        cursor.execute("""
            SELECT t.id, t.name, t.type, t.config
            FROM tools t
            JOIN agent_tools at ON t.id = at.tool_id
            WHERE at.agent_id = ?
        """, (agent["id"],))
        agent["tools"] = [dict(row) for row in cursor.fetchall()]

        # Get handoffs
        cursor.execute("""
            SELECT a.id, a.name
            FROM agents a
            JOIN agent_handoffs ah ON a.id = ah.to_agent_id
            WHERE ah.from_agent_id = ?
        """, (agent["id"],))
        agent["handoffs"] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return agents


def get_agent_by_id(agent_id: int) -> Optional[Dict[str, Any]]:
    """Get a single agent by ID with tools and handoffs"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    agent = dict(row)

    # Get tools
    cursor.execute("""
        SELECT t.id, t.name, t.type, t.config
        FROM tools t
        JOIN agent_tools at ON t.id = at.tool_id
        WHERE at.agent_id = ?
    """, (agent_id,))
    agent["tools"] = [dict(row) for row in cursor.fetchall()]

    # Get handoffs
    cursor.execute("""
        SELECT a.id, a.name
        FROM agents a
        JOIN agent_handoffs ah ON a.id = ah.to_agent_id
        WHERE ah.from_agent_id = ?
    """, (agent_id,))
    agent["handoffs"] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return agent


def create_agent(
    name: str,
    instructions: str,
    model: str,
    tool_ids: List[int],
    handoff_agent_ids: List[int],
    is_starting_agent: bool = False
) -> int:
    """Create a new agent"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # If this is a starting agent, unset other starting agents
    if is_starting_agent:
        cursor.execute("UPDATE agents SET is_starting_agent = FALSE")

    cursor.execute(
        """INSERT INTO agents (name, instructions, model, is_starting_agent, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (name, instructions, model, is_starting_agent, datetime.now())
    )
    agent_id = cursor.lastrowid

    # Add tools
    for tool_id in tool_ids:
        cursor.execute(
            "INSERT INTO agent_tools (agent_id, tool_id) VALUES (?, ?)",
            (agent_id, tool_id)
        )

    # Add handoffs
    for handoff_id in handoff_agent_ids:
        cursor.execute(
            "INSERT INTO agent_handoffs (from_agent_id, to_agent_id) VALUES (?, ?)",
            (agent_id, handoff_id)
        )

    conn.commit()
    conn.close()
    return agent_id


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
    conn = get_db_connection()
    cursor = conn.cursor()

    # If this is a starting agent, unset other starting agents
    if is_starting_agent:
        cursor.execute("UPDATE agents SET is_starting_agent = FALSE WHERE id != ?", (agent_id,))

    cursor.execute(
        """UPDATE agents
           SET name = ?, instructions = ?, model = ?, is_starting_agent = ?, updated_at = ?
           WHERE id = ?""",
        (name, instructions, model, is_starting_agent, datetime.now(), agent_id)
    )

    # Remove old tools and handoffs
    cursor.execute("DELETE FROM agent_tools WHERE agent_id = ?", (agent_id,))
    cursor.execute("DELETE FROM agent_handoffs WHERE from_agent_id = ?", (agent_id,))

    # Add new tools
    for tool_id in tool_ids:
        cursor.execute(
            "INSERT INTO agent_tools (agent_id, tool_id) VALUES (?, ?)",
            (agent_id, tool_id)
        )

    # Add new handoffs
    for handoff_id in handoff_agent_ids:
        cursor.execute(
            "INSERT INTO agent_handoffs (from_agent_id, to_agent_id) VALUES (?, ?)",
            (agent_id, handoff_id)
        )

    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


def delete_agent(agent_id: int) -> bool:
    """Delete an agent"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


# Tool operations
def get_all_tools() -> List[Dict[str, Any]]:
    """Get all tools"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tools ORDER BY type, name")
    tools = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return tools


def get_tool_by_id(tool_id: int) -> Optional[Dict[str, Any]]:
    """Get a single tool by ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tools WHERE id = ?", (tool_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_custom_tool(name: str, config: Dict[str, Any], icon: str = "Wrench") -> int:
    """Create a custom API tool or MCP tool"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Determine tool type from config
    tool_type = config.get("type", "custom_api")

    cursor.execute(
        "INSERT INTO tools (name, type, config, icon) VALUES (?, ?, ?, ?)",
        (name, tool_type, json.dumps(config), icon)
    )
    tool_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return tool_id


def update_custom_tool(tool_id: int, name: str, config: Dict[str, Any], icon: str = "Wrench") -> bool:
    """Update a custom API tool, MCP tool, or Gemini File Search tool"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Determine tool type from config
    tool_type = config.get("type", "custom_api")

    cursor.execute(
        "UPDATE tools SET name = ?, type = ?, config = ?, icon = ? WHERE id = ? AND type IN ('custom_api', 'mcp_streamable_http', 'gemini_file_search')",
        (name, tool_type, json.dumps(config), icon, tool_id)
    )
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


def delete_custom_tool(tool_id: int) -> bool:
    """Delete a custom API tool, MCP tool, or Gemini File Search tool"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tools WHERE id = ? AND type IN ('custom_api', 'mcp_streamable_http', 'gemini_file_search')", (tool_id,))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


# File Store operations
def get_all_file_stores() -> List[Dict[str, Any]]:
    """Get all file stores"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM file_stores ORDER BY created_at DESC")
    stores = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return stores


def get_file_store_by_id(store_id: int) -> Optional[Dict[str, Any]]:
    """Get a single file store by ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM file_stores WHERE id = ?", (store_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_file_store_by_gemini_id(gemini_store_id: str) -> Optional[Dict[str, Any]]:
    """Get a file store by Gemini store ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM file_stores WHERE gemini_store_id = ?", (gemini_store_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_file_store(name: str, gemini_store_id: str, display_name: str = None) -> int:
    """Create a new file store"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO file_stores (name, gemini_store_id, display_name)
           VALUES (?, ?, ?)""",
        (name, gemini_store_id, display_name)
    )
    store_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return store_id


def delete_file_store(store_id: int) -> bool:
    """Delete a file store (cascades to files)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM file_stores WHERE id = ?", (store_id,))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


def add_file_to_store(
    file_store_id: int,
    filename: str,
    original_filename: str,
    file_size: int
) -> int:
    """Add a file record to a store"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO file_store_files (file_store_id, filename, original_filename, file_size)
           VALUES (?, ?, ?, ?)""",
        (file_store_id, filename, original_filename, file_size)
    )
    file_id = cursor.lastrowid

    # Update file count
    cursor.execute(
        """UPDATE file_stores
           SET file_count = (SELECT COUNT(*) FROM file_store_files WHERE file_store_id = ?)
           WHERE id = ?""",
        (file_store_id, file_store_id)
    )

    conn.commit()
    conn.close()
    return file_id


def get_files_by_store(file_store_id: int) -> List[Dict[str, Any]]:
    """Get all files in a store"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM file_store_files WHERE file_store_id = ? ORDER BY uploaded_at DESC",
        (file_store_id,)
    )
    files = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return files


def delete_file(file_id: int) -> bool:
    """Delete a file from a store"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get file_store_id before deleting
    cursor.execute("SELECT file_store_id FROM file_store_files WHERE id = ?", (file_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return False

    file_store_id = row["file_store_id"]

    # Delete file
    cursor.execute("DELETE FROM file_store_files WHERE id = ?", (file_id,))

    # Update file count
    cursor.execute(
        """UPDATE file_stores
           SET file_count = (SELECT COUNT(*) FROM file_store_files WHERE file_store_id = ?)
           WHERE id = ?""",
        (file_store_id, file_store_id)
    )

    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


def update_file_count(file_store_id: int) -> bool:
    """Update file count for a store"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE file_stores
           SET file_count = (SELECT COUNT(*) FROM file_store_files WHERE file_store_id = ?)
           WHERE id = ?""",
        (file_store_id, file_store_id)
    )
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


# Analytics operations
def create_conversation(session_id: str, started_at: str) -> int:
    """Create a new conversation record"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO conversations (session_id, started_at) VALUES (?, ?)",
        (session_id, started_at)
    )
    conversation_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return conversation_id


def get_conversation_by_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get conversation by session ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM conversations WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


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
    conn = get_db_connection()
    cursor = conn.cursor()

    update_fields = []
    values = []

    if ended_at is not None:
        update_fields.append("ended_at = ?")
        values.append(ended_at)
    if duration_seconds is not None:
        update_fields.append("duration_seconds = ?")
        values.append(duration_seconds)
    if total_messages is not None:
        update_fields.append("total_messages = ?")
        values.append(total_messages)
    if user_messages is not None:
        update_fields.append("user_messages = ?")
        values.append(user_messages)
    if agent_messages is not None:
        update_fields.append("agent_messages = ?")
        values.append(agent_messages)
    if agents_involved is not None:
        update_fields.append("agents_involved = ?")
        values.append(agents_involved)
    if tools_used is not None:
        update_fields.append("tools_used = ?")
        values.append(tools_used)
    if outcome is not None:
        update_fields.append("outcome = ?")
        values.append(outcome)

    if not update_fields:
        conn.close()
        return False

    values.append(conversation_id)
    query = f"UPDATE conversations SET {', '.join(update_fields)} WHERE id = ?"

    cursor.execute(query, values)
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


def add_conversation_message(
    conversation_id: int,
    role: str,
    content: str,
    timestamp: str,
    agent_name: Optional[str] = None,
    tool_calls: Optional[str] = None
) -> int:
    """Add a message to a conversation"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO conversation_messages
           (conversation_id, role, content, timestamp, agent_name, tool_calls)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (conversation_id, role, content, timestamp, agent_name, tool_calls)
    )
    message_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return message_id


def get_conversation_messages(conversation_id: int) -> List[Dict[str, Any]]:
    """Get all messages for a conversation"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY timestamp ASC",
        (conversation_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_conversation_analytics(conversation_id: int, analytics_data: Dict[str, Any]) -> int:
    """Save LLM-generated analytics for a conversation"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """INSERT INTO conversation_analytics (
            conversation_id, overall_sentiment, sentiment_score, sentiment_explanation,
            primary_topic, topics, resolution_quality, agent_performance_score,
            response_clarity_score, empathy_score, issues_identified,
            customer_pain_points, suggestions, customer_intent, urgency_level,
            follow_up_needed, follow_up_reason, llm_model, analysis_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            conversation_id,
            analytics_data.get('overall_sentiment'),
            analytics_data.get('sentiment_score'),
            analytics_data.get('sentiment_explanation'),
            analytics_data.get('primary_topic'),
            analytics_data.get('topics'),
            analytics_data.get('resolution_quality'),
            analytics_data.get('agent_performance_score'),
            analytics_data.get('response_clarity_score'),
            analytics_data.get('empathy_score'),
            analytics_data.get('issues_identified'),
            analytics_data.get('customer_pain_points'),
            analytics_data.get('suggestions'),
            analytics_data.get('customer_intent'),
            analytics_data.get('urgency_level'),
            analytics_data.get('follow_up_needed', False),
            analytics_data.get('follow_up_reason'),
            analytics_data.get('llm_model'),
            analytics_data.get('analysis_version', 'v1.0')
        )
    )
    analytics_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return analytics_id


def get_analytics_summary(period: str = 'today') -> Dict[str, Any]:
    """Get analytics summary for dashboard"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Determine date filter based on period
    if period == 'today':
        date_filter = "DATE(started_at) = DATE('now')"
    elif period == 'week':
        date_filter = "DATE(started_at) >= DATE('now', '-7 days')"
    elif period == 'month':
        date_filter = "DATE(started_at) >= DATE('now', '-30 days')"
    else:
        date_filter = "1=1"  # All time

    # Total conversations
    cursor.execute(f"SELECT COUNT(*) FROM conversations WHERE {date_filter}")
    total_conversations = cursor.fetchone()[0]

    # Resolution rate
    cursor.execute(
        f"SELECT COUNT(*) * 100.0 / NULLIF((SELECT COUNT(*) FROM conversations WHERE {date_filter}), 0) FROM conversations WHERE {date_filter} AND outcome = 'resolved'"
    )
    resolution_rate = cursor.fetchone()[0] or 0

    # Average messages per conversation
    cursor.execute(
        f"SELECT AVG(total_messages) FROM conversations WHERE {date_filter} AND total_messages > 0"
    )
    avg_messages = cursor.fetchone()[0] or 0

    # Average sentiment score
    cursor.execute(
        f"""SELECT AVG(ca.sentiment_score)
            FROM conversation_analytics ca
            JOIN conversations c ON ca.conversation_id = c.id
            WHERE {date_filter} AND ca.sentiment_score IS NOT NULL"""
    )
    avg_sentiment = cursor.fetchone()[0] or 0

    # Outcome breakdown
    cursor.execute(
        f"""SELECT outcome, COUNT(*) as count
            FROM conversations
            WHERE {date_filter}
            GROUP BY outcome"""
    )
    outcome_rows = cursor.fetchall()
    outcome_breakdown = {row[0]: row[1] for row in outcome_rows}

    # Sentiment breakdown
    cursor.execute(
        f"""SELECT ca.overall_sentiment, COUNT(*) as count
            FROM conversation_analytics ca
            JOIN conversations c ON ca.conversation_id = c.id
            WHERE {date_filter} AND ca.overall_sentiment IS NOT NULL
            GROUP BY ca.overall_sentiment"""
    )
    sentiment_rows = cursor.fetchall()
    sentiment_breakdown = {row[0]: row[1] for row in sentiment_rows}

    # Topic breakdown
    cursor.execute(
        f"""SELECT ca.primary_topic, COUNT(*) as count
            FROM conversation_analytics ca
            JOIN conversations c ON ca.conversation_id = c.id
            WHERE {date_filter} AND ca.primary_topic IS NOT NULL
            GROUP BY ca.primary_topic
            ORDER BY count DESC
            LIMIT 10"""
    )
    topic_rows = cursor.fetchall()
    topic_breakdown = {row[0]: row[1] for row in topic_rows}

    conn.close()

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
