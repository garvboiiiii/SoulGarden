import sqlite3

conn = sqlite3.connect("memories.db", check_same_thread=False)
c = conn.cursor()

def init_db():
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        name TEXT,
        points INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS memories (
        user_id INTEGER,
        content TEXT,
        type TEXT,  -- text/image/voice
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")

    conn.commit()

def add_user(user_id, name):
    c.execute("INSERT OR IGNORE INTO users (id, name) VALUES (?, ?)", (user_id, name))
    conn.commit()

def log_memory(user_id, content, mem_type):
    c.execute("INSERT INTO memories (user_id, content, type) VALUES (?, ?, ?)",
              (user_id, content, mem_type))
    c.execute("UPDATE users SET points = points + 5 WHERE id = ?", (user_id,))
    conn.commit()

def get_dashboard_data(user_id):
    c.execute("SELECT name, points FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()

    c.execute("SELECT content, type, timestamp FROM memories WHERE user_id = ?", (user_id,))
    files = c.fetchall()

    return user, files
