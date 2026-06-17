import sqlite3
from datetime import datetime

def init_db():
    conn = sqlite3.connect('moodwatch.db')
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
    
    conn.commit()
    conn.close()


def save_feedback(title_id, feedback_type):
    conn = sqlite3.connect('moodwatch.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO feedback (title_id, feedback_type, timestamp)
        VALUES (?, ?, ?)
    ''', (title_id, feedback_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()


def load_feedback():
    conn = sqlite3.connect('moodwatch.db')
    cursor = conn.cursor()
    cursor.execute('SELECT title_id, feedback_type FROM feedback')
    rows = cursor.fetchall()
    conn.close()
    liked = [r[0] for r in rows if r[1] == 'like']
    disliked = [r[0] for r in rows if r[1] == 'dislike']
    return liked, disliked


if __name__ == "__main__":
    init_db()
    print("DB initialized successfully")


