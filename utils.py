# utils.py
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect("data.db", check_same_thread=False)
c = conn.cursor()

def get_today():
    return datetime.utcnow().strftime("%Y-%m-%d")

def get_yesterday():
    return (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

def log_memory(user_id):
    today = get_today()
    c.execute("SELECT last_logged, streak FROM users WHERE id = ?", (user_id,))
    result = c.fetchone()

    if not result:
        c.execute("INSERT INTO users (id, last_logged, streak, points) VALUES (?, ?, 1, 5)", (user_id, today))
    else:
        last_logged, streak = result
        if last_logged == today:
            return  # Already logged today
        elif last_logged == get_yesterday():
            streak += 1
        else:
            streak = 1

        c.execute("UPDATE users SET last_logged = ?, streak = ?, points = points + 5 WHERE id = ?", (today, streak, user_id))
    conn.commit()

def get_user_data(user_id):
    c.execute("SELECT streak, points FROM users WHERE id = ?", (user_id,))
    return c.fetchone() or (0, 0)

def save_memory(user_id, mood, text):
    today = get_today()
    c.execute("INSERT INTO memories (user_id, mood, text, date) VALUES (?, ?, ?, ?)", (user_id, mood, text, today))
    conn.commit()
    log_memory(user_id)

def save_voice(user_id, file_id):
    today = get_today()
    c.execute("INSERT INTO voices (user_id, file_id, date) VALUES (?, ?, ?)", (user_id, file_id, today))
    conn.commit()
    log_memory(user_id)

def get_memories(user_id):
    c.execute("SELECT mood, text, date FROM memories WHERE user_id = ? ORDER BY date DESC", (user_id,))
    return c.fetchall()

def get_voices(user_id):
    c.execute("SELECT file_id, date FROM voices WHERE user_id = ? ORDER BY date DESC", (user_id,))
    return c.fetchall()
