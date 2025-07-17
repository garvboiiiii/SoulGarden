# utils.py
import sqlite3
from datetime import datetime, timedelta

DB_PATH = "data.db"

def connect_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def log_memory(user_id, mood, text, audio_path=None):
    conn = connect_db()
    c = conn.cursor()
    today = datetime.utcnow().strftime('%Y-%m-%d')
    c.execute("""
        INSERT INTO memories (user_id, date, mood, text, audio_path)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, today, mood, text, audio_path))

    # Update points and streak
    c.execute("SELECT last_log_date, streak FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    if user:
        last_date_str, streak = user
        last_date = datetime.strptime(last_date_str, '%Y-%m-%d') if last_date_str else None
        if last_date == datetime.utcnow() - timedelta(days=1):
            streak += 1
        else:
            streak = 1
    else:
        streak = 1

    c.execute("""
        INSERT OR IGNORE INTO users (id, streak, last_log_date, points)
        VALUES (?, ?, ?, ?)
    """, (user_id, streak, today, 10))

    c.execute("""
        UPDATE users SET last_log_date = ?, streak = ?, points = points + 10 WHERE id = ?
    """, (today, streak, user_id))

    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT streak, points FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    c.execute("SELECT date, mood, text, audio_path FROM memories WHERE user_id = ? ORDER BY date DESC", (user_id,))
    memories = c.fetchall()
    conn.close()
    return user, memories
