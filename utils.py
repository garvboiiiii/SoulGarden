# utils.py
import sqlite3
import datetime

db_path = "garden.db"

def log_memory(user_id, text, mood, voice_path=None):
    now = datetime.datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()

        # Insert memory
        c.execute("INSERT INTO memories (user_id, text, mood, timestamp, voice_path) VALUES (?, ?, ?, ?, ?)",
                  (user_id, text, mood, now, voice_path))

        # Update streak logic
        c.execute("SELECT last_entry, streak, points FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        if row:
            last_entry, current_streak, current_points = row
            today = datetime.datetime.now().date()
            if last_entry:
                last_date = datetime.datetime.fromisoformat(last_entry).date()
                diff = (today - last_date).days

                if diff == 1:
                    new_streak = current_streak + 1
                elif diff == 0:
                    new_streak = current_streak
                else:
                    new_streak = 1
            else:
                new_streak = 1

            # 1 point per memory, + bonus every 5 streak
            bonus = 2 if new_streak % 5 == 0 else 0
            new_points = current_points + 1 + bonus

            c.execute("UPDATE users SET last_entry = ?, streak = ?, points = ? WHERE id = ?",
                      (now, new_streak, new_points, user_id))
        conn.commit()

def get_user_stats(user_id):
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute("SELECT streak, points FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        return {"streak": row[0], "points": row[1]} if row else {"streak": 0, "points": 0}

def calculate_streak(user_id):
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute("SELECT streak FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        return row[0] if row else 0

def get_other_memories(user_id):
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, text, mood FROM memories WHERE user_id != ? ORDER BY RANDOM() LIMIT 10", (user_id,))
        return c.fetchall()
