# utils.py
import sqlite3
import datetime
import os

DB_PATH = os.getenv("DB_PATH", "garden.db")

def get_db_connection():
    """Returns a new connection to the database."""
    return sqlite3.connect(DB_PATH)

def log_memory(user_id, text, mood, voice_path=None):
    """Logs a memory with streak and points logic."""
    now = datetime.datetime.utcnow().isoformat()  # use UTC for consistency
    try:
        with get_db_connection() as conn:
            c = conn.cursor()

            # Insert memory
            c.execute("""
                INSERT INTO memories (user_id, text, mood, timestamp, voice_path)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, text, mood, now, voice_path))

            # Fetch user streak and last entry
            c.execute("SELECT last_entry, streak, points FROM users WHERE id = ?", (user_id,))
            row = c.fetchone()

            if row:
                last_entry, current_streak, current_points = row
                today = datetime.datetime.utcnow().date()

                if last_entry:
                    try:
                        last_date = datetime.datetime.fromisoformat(last_entry).date()
                        diff = (today - last_date).days
                    except ValueError:
                        diff = None
                else:
                    diff = None

                # Update streak
                if diff == 1:
                    new_streak = current_streak + 1
                elif diff == 0:
                    new_streak = current_streak
                else:
                    new_streak = 1

                # Update points: +1 per memory, +2 bonus every 5 streak
                bonus = 2 if new_streak % 5 == 0 else 0
                new_points = current_points + 1 + bonus

                c.execute("""
                    UPDATE users SET last_entry = ?, streak = ?, points = ? WHERE id = ?
                """, (now, new_streak, new_points, user_id))

            conn.commit()

    except Exception as e:
        print(f"[log_memory] Error: {e}")

def get_user_stats(user_id):
    """Returns a dictionary of user streak and points."""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT streak, points FROM users WHERE id = ?", (user_id,))
            row = c.fetchone()
            return {"streak": row[0], "points": row[1]} if row else {"streak": 0, "points": 0}
    except Exception as e:
        print(f"[get_user_stats] Error: {e}")
        return {"streak": 0, "points": 0}

def calculate_streak(user_id):
    """Returns current streak count."""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT streak FROM users WHERE id = ?", (user_id,))
            row = c.fetchone()
            return row[0] if row else 0
    except Exception as e:
        print(f"[calculate_streak] Error: {e}")
        return 0

def get_other_memories(user_id, limit=10):
    """Returns random memories from other users."""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT user_id, text, mood FROM memories
                WHERE user_id != ?
                ORDER BY RANDOM() LIMIT ?
            """, (user_id, limit))
            return c.fetchall()
    except Exception as e:
        print(f"[get_other_memories] Error: {e}")
        return []
