"""
Configure Dtwin Agent to use offline-safe tools and remove MCP tools.

Usage:
  python server/scripts/configure_dtwin_fallback.py

Effects:
- Finds agent named like 'Dtwin Agent' (case-insensitive)
- Removes any MCP tools (type == 'mcp_streamable_http') from that agent
- Ensures built-in tool 'get_past_orders' is attached
"""

import os
import sqlite3


def db_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "agents.db")


def main():
    path = os.path.abspath(db_path())
    if not os.path.exists(path):
        raise SystemExit(f"Database not found: {path}")

    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()

        # Find Dtwin agent (case-insensitive)
        cur.execute(
            "SELECT id, name FROM agents WHERE LOWER(name) LIKE LOWER(?)",
            ("%dtwin%",),
        )
        row = cur.fetchone()
        if not row:
            raise SystemExit("No agent matching 'Dtwin' found.")
        agent_id, agent_name = row

        # Find get_past_orders tool id
        cur.execute(
            "SELECT id FROM tools WHERE name = ?",
            ("get_past_orders",),
        )
        trow = cur.fetchone()
        if not trow:
            raise SystemExit("Built-in tool 'get_past_orders' not found in tools table.")
        past_orders_tool_id = trow[0]

        # Remove MCP tools from this agent
        cur.execute(
            """
            DELETE FROM agent_tools
            WHERE agent_id = ?
              AND tool_id IN (
                SELECT id FROM tools WHERE type = 'mcp_streamable_http'
              )
            """,
            (agent_id,),
        )

        # Ensure get_past_orders attached
        cur.execute(
            "SELECT 1 FROM agent_tools WHERE agent_id = ? AND tool_id = ?",
            (agent_id, past_orders_tool_id),
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO agent_tools (agent_id, tool_id) VALUES (?, ?)",
                (agent_id, past_orders_tool_id),
            )

        conn.commit()
        print(
            f"Updated agent '{agent_name}' (id={agent_id}): removed MCP tools and added get_past_orders."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()

