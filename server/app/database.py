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
    """Update a custom API tool or MCP tool"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Determine tool type from config
    tool_type = config.get("type", "custom_api")

    cursor.execute(
        "UPDATE tools SET name = ?, type = ?, config = ?, icon = ? WHERE id = ? AND type IN ('custom_api', 'mcp_streamable_http')",
        (name, tool_type, json.dumps(config), icon, tool_id)
    )
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


def delete_custom_tool(tool_id: int) -> bool:
    """Delete a custom API tool or MCP tool"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tools WHERE id = ? AND type IN ('custom_api', 'mcp_streamable_http')", (tool_id,))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success


# Initialize database on module import
init_database()
