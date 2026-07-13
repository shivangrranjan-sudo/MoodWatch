import sqlite3
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "moodwatch.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _ensure_column(cursor, table, column, definition):
    columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metadata_cache (
            id TEXT PRIMARY KEY,
            title TEXT,
            content_type TEXT,
            poster_url TEXT,
            description TEXT,
            genres TEXT,
            rating REAL,
            runtime TEXT,
            watch_providers TEXT,
            release_year TEXT,
            trailer_url TEXT,
            cached_date TEXT DEFAULT (datetime('now'))
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sentiment_cache (
            title_id TEXT PRIMARY KEY,
            polarity REAL,
            review_snippets TEXT,
            cached_date TEXT DEFAULT (datetime('now'))
        )      
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            title_id TEXT,
            feedback_type TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        )
    ''')

    _ensure_column(cursor, "metadata_cache", "release_year", "TEXT")
    _ensure_column(cursor, "metadata_cache", "trailer_url", "TEXT")
    # Scope feedback to the query it was given for, so a thumbs-up on one query
    # doesn't boost that title across unrelated queries.
    _ensure_column(cursor, "feedback", "query", "TEXT")

    conn.commit()
    conn.close()


def _normalize_query_key(query):
    return (query or "").strip().lower()


def save_feedback(title_id, feedback_type, query=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO feedback (title_id, feedback_type, query, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (title_id, feedback_type, _normalize_query_key(query),
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()


def load_feedback(query=None):
    """Return (liked, disliked) title ids. If a query is given, only feedback
    recorded for that same query is returned, so relevance feedback stays scoped
    to its query instead of leaking into every other search."""
    conn = get_connection()
    cursor = conn.cursor()
    if query is None:
        cursor.execute('SELECT title_id, feedback_type FROM feedback')
    else:
        cursor.execute(
            'SELECT title_id, feedback_type FROM feedback WHERE query = ?',
            (_normalize_query_key(query),),
        )
    rows = cursor.fetchall()
    conn.close()
    liked = [r[0] for r in rows if r[1] == 'like']
    disliked = [r[0] for r in rows if r[1] == 'dislike']
    return liked, disliked


if __name__ == "__main__":
    init_db()
    print("DB initialized successfully")
