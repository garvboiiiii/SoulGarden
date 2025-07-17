# utils.py
from datetime import datetime, timedelta
import sqlite3

DB = "data.db"

# --- Utility Functions ---
def get_db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    return conn, conn.cursor()

def get_today():
    return datetime.utcnow().strftime("%Y-%m-%d")

def get_yesterday():
    return (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

def update_streak(user_id):
    conn, c = get_db()
    today = get_today()
    yesterday = get_yesterday()

    c.execute("SELECT last_log, streak FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()

    if not row:
        c.execute("INSERT INTO users (id, streak, last_log, points) VALUES (?, ?, ?, ?)",
                  (user_id, 1, today, 10))
    else:
        last_log, streak = row
        if last_log == today:
            pass  # Already logged today
        elif last_log == yesterday:
            c.execute("UPDATE users SET streak = streak + 1, last_log = ?, points = points + 10 WHERE id = ?", (today, user_id))
        else:
            c.execute("UPDATE users SET streak = 1, last_log = ?, points = points + 10 WHERE id = ?", (today, user_id))
    conn.commit()
    conn.close()

def get_user_stats(user_id):
    conn, c = get_db()
    c.execute("SELECT streak, points FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    return row if row else (0, 0)

def store_memory(user_id, text, mood, voice_path=None):
    conn, c = get_db()
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO memories (user_id, content, mood, timestamp, voice_path) VALUES (?, ?, ?, ?, ?)",
              (user_id, text, mood, timestamp, voice_path))
    conn.commit()
    conn.close()

def get_memories(user_id):
    conn, c = get_db()
    c.execute("SELECT content, mood, timestamp, voice_path FROM memories WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
    rows = c.fetchall()
    return rows
