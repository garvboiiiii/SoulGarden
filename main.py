import os, random, telebot
import psycopg2
import urllib.parse as up
from datetime import datetime, timedelta
from flask import Flask, request, render_template
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler

# --- Setup Environment ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1335511330"))

up.uses_netloc.append("postgres")
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Connect to PostgreSQL ---
conn = psycopg2.connect(DATABASE_URL)
c = conn.cursor()

# --- Flask & Bot Init ---
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, template_folder="templates", static_folder="static")
scheduler = BackgroundScheduler()
scheduler.start()

# --- Create Tables (PostgreSQL Syntax) ---
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username VARCHAR,
    referred_by BIGINT,
    streak INTEGER DEFAULT 0,
    last_check TIMESTAMP,
    points INTEGER DEFAULT 0,
    joined_at TIMESTAMP,
    last_streak TIMESTAMP
)""")
c.execute("""
CREATE TABLE IF NOT EXISTS memories (
    user_id BIGINT,
    text TEXT,
    mood INTEGER,
    timestamp TIMESTAMP,
    voice_path TEXT
)""")
conn.commit()

# --- Globals ---
pending_voice = {}

# --- Menu ---
def menu(uid):
    m = InlineKeyboardMarkup(row_width=2)
    btns = [
        ("📝 Log", "log"), ("🎤 Voice", "voice"),
        ("📜 Memories", "memories"), ("🏆 Leaderboard", "leaderboard"),
        ("🌍 Explore", "explore"), ("📊 Dashboard", "dashboard"),
        ("🌟 Streak", "streak"), ("🔗 Referral", "referral"),
        ("📖 Help", "help"), ("🔒 Privacy", "privacy"),
        ("🧘 About", "about"), ("🗑️ Delete", "delete")
    ]
    if uid == ADMIN_ID:
        btns.append(("📊 Admin", "admin"))
    m.add(*[InlineKeyboardButton(t, callback_data=d) for t, d in btns])
    return m

# --- Helpers ---
def get_stats(uid):
    c.execute("SELECT streak, points FROM users WHERE id=%s", (uid,))
    r = c.fetchone() or (0, 0)
    return {"streak": r[0], "points": r[1]}

def valid_streak(uid):
    c.execute("SELECT last_streak FROM users WHERE id=%s", (uid,))
    row = c.fetchone()
    if not row or not row[0]:
        return True
    return datetime.utcnow() - row[0] >= timedelta(hours=24)

def motivation():
    return random.choice([
        "🌞 You're doing great!", "🌻 Keep expressing yourself.",
        "🌊 Let your thoughts flow.", "💫 Another day of growth.",
        "🌿 Reflection brings clarity.", "🌸 Peace begins with you.",
        "🍀 You're never alone here.", "✨ Great job journaling!",
        "🌙 Let go, let grow.", "🌼 Healing is nonlinear."
    ])

# --- Command Handlers ---
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.from_user.id
    name = msg.from_user.username or f"user{uid}"
    ref = None
    if len(msg.text.split()) > 1:
        try:
            ref = int(msg.text.split()[1])
        except:
            pass
    if uid != ref:
        c.execute("""
            INSERT INTO users (id, username, referred_by, joined_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (uid, name, ref, datetime.utcnow()))
        if ref:
            c.execute("UPDATE users SET points = points + 5 WHERE id = %s", (ref,))
            bot.send_message(ref, f"🎁 +5 points for inviting @{name}")
        conn.commit()
    bot.send_message(uid, "🌱 Welcome to SoulGarden!", reply_markup=menu(uid))

@bot.message_handler(commands=['log'])
def log_cmd(msg):
    uid = msg.from_user.id
    bot.send_message(uid, "📝 What's on your mind?")
    bot.register_next_step_handler_by_chat_id(uid, after_log)

@bot.message_handler(commands=['voice'])
def voice_cmd(msg):
    uid = msg.from_user.id
    pending_voice[uid] = True
    bot.send_message(uid, "🎤 Send your voice note.")

@bot.message_handler(content_types=['voice'])
def handle_voice(msg):
    uid = msg.from_user.id
    if pending_voice.pop(uid, None):
        f = bot.get_file(msg.voice.file_id)
        data = bot.download_file(f.file_path)
        path = f"static/voices/{uid}_{msg.message_id}.ogg"
        os.makedirs("static/voices", exist_ok=True)
        with open(path, "wb") as f_: f_.write(data)
        c.execute("INSERT INTO memories VALUES (%s, %s, %s, %s, %s)",
                  (uid, "(voice)", 5, datetime.utcnow(), path))
        c.execute("UPDATE users SET points = points + 1 WHERE id = %s", (uid,))
        conn.commit()
        s = get_stats(uid)
        bot.send_message(uid, f"🎤 Saved!\nPoints: {s['points']}", reply_markup=menu(uid))

def after_log(msg):
    uid = msg.from_user.id
    txt = msg.text.strip()
    c.execute("INSERT INTO memories VALUES (%s, %s, %s, %s, %s)",
              (uid, txt, 0, datetime.utcnow(), None))
    c.execute("UPDATE users SET points = points + 1 WHERE id = %s", (uid,))
    conn.commit()
    s = get_stats(uid)
    bot.send_message(uid, f"💾 Saved!\nPoints: {s['points']}\n{motivation()}", reply_markup=menu(uid))

# Web routes
@app.route("/dashboard/<int:uid>")
def dashboard(uid):
    c.execute("SELECT username, points, streak FROM users WHERE id=%s", (uid,))
    u = c.fetchone()
    if not u: return "User not found", 404

    c.execute("SELECT COUNT(*) FROM users WHERE referred_by=%s", (uid,))
    ref = c.fetchone()[0]

    c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id=%s", (uid,))
    mems = [{"text": t, "mood": m, "timestamp": ts, "voice": vp} for t, m, ts, vp in c.fetchall()]
    return render_template("dashboard.html", name=u[0], points=u[1], streak=u[2], referrals=ref, memories=mems)

@app.route("/leaderboard")
def leaderboard():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    return render_template("leaderboard.html", users=c.fetchall())

@app.route("/visit_garden/<int:uid>")
def visit(uid):
    c.execute("SELECT username FROM users WHERE id=%s", (uid,))
    u = c.fetchone()
    if not u: return "User not found", 404

    c.execute("SELECT text,mood,timestamp,voice_path FROM memories WHERE user_id=%s ORDER BY timestamp DESC LIMIT 10", (uid,))
    mems = [{"text": t, "mood": m, "timestamp": ts, "voice": vp} for t, m, ts, vp in c.fetchall()]
    return render_template("visit_garden.html", name=u[0], memories=mems)


@app.route("/privacy")
def privacy(): return render_template("privacy.html")

@app.route("/admin/analytics")
def analytics():
    if int(request.args.get("uid", 0)) != ADMIN_ID:
        return "403", 403

    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE DATE(joined_at)=CURRENT_DATE")
    new_today = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM memories")
    total_mem = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM memories WHERE DATE(timestamp)=CURRENT_DATE")
    new_mem = c.fetchone()[0]

    return render_template("admin_analytics.html",
        total_users=total_users,
        new_today=new_today,
        total_memories=total_mem,
        new_memories=new_mem
    )


# --- Cron Daily Reminder ---
def daily():
    c.execute("SELECT id FROM users")
    for (uid,) in c.fetchall():
        try:
            bot.send_message(uid, random.choice([
                "🧘 Reflect today?", "🌿 Feeling okay?", "💬 Time to log thoughts?",
                "✨ Grow with reflection.", "🍃 Journaling = self-care."
            ]))
        except: continue

scheduler.add_job(daily, 'cron', hour=8)

# --- Flask Webhooks ---
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.data.decode("utf-8"))])
    return "OK"

@app.route("/")
def home():
    return "🌿 SoulGarden Running"

# --- Start Bot ---
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=8080)
