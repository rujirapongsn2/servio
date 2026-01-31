import os
import psycopg2
import psycopg2.extras
from sqlalchemy.engine.url import make_url

def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
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
        connection = psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB", "voice_agents"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            host=os.getenv("POSTGRES_HOST", "postgres"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            cursor_factory=psycopg2.extras.RealDictCursor
        )
    return connection

conn = get_db_connection()
cur = conn.cursor()
cur.execute("SELECT name, instructions FROM agents;")
rows = cur.fetchall()
for row in rows:
    print(f"Agent: {row['name']}")
    print(f"Instructions:\n{row['instructions']}")
    print("-" * 40)
cur.close()
conn.close()
