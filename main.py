import os
import sqlite3
import random
import telebot
from flask import Flask, request, render_template
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", 1335511330))  # Ensure it's integer

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, static_folder="static", template_folder="templates")
scheduler = BackgroundScheduler()
scheduler.start()

conn = sqlite3.connect("garden.db", check_same_thread=False)
c = conn.cursor()

# DB setup
c.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,
    referred_by INTEGER,
    streak INTEGER DEFAULT 0,
    last_entry TEXT,
    points INTEGER DEFAULT 0,
    joined_at TEXT,
    is_new INTEGER DEFAULT 1
)""")
c.execute("""CREATE TABLE IF NOT EXISTS memories (
    user_id INTEGER,
    text TEXT,
    mood TEXT,
    timestamp TEXT,
    voice_path TEXT
)""")
conn.commit()

# Helpers
def get_user_stats(uid):
    c.execute("SELECT streak, points FROM users WHERE id = ?", (uid,))
    row = c.fetchone()
    return {"streak": row[0], "points": row[1]} if row else {"streak": 0, "points": 0}

def calculate_streak(uid):
    c.execute("SELECT last_entry FROM users WHERE id = ?", (uid,))
    row = c.fetchone()
    if not row or not row[0]:
        return 0
    last = datetime.fromisoformat(row[0]).date()
    today = datetime.utcnow().date()
    delta = (today - last).days
    return max(0, 1 if delta == 0 else 0)

def log_memory(uid, text, mood, voice_path=None):
    now = datetime.utcnow().isoformat()
    c.execute("INSERT INTO memories (user_id, text, mood, timestamp, voice_path) VALUES (?, ?, ?, ?, ?)",
              (uid, text, mood, now, voice_path))
    c.execute("UPDATE users SET streak = streak + 1, last_entry = ?, points = points + 1 WHERE id = ?", (now, uid))
    conn.commit()

# UI
def menu_buttons(uid):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📝 Log Memory", callback_data="log"),
        InlineKeyboardButton("🎤 Voice Note", callback_data="voice"),
        InlineKeyboardButton("📜 My Memories", callback_data="memories"),
        InlineKeyboardButton("🏆 Leaderboard", url=f"{WEBHOOK_URL}/leaderboard"),
        InlineKeyboardButton("🌍 Explore", callback_data="explore"),
        InlineKeyboardButton("📊 Dashboard", url=f"{WEBHOOK_URL}/dashboard/{uid}"),
        InlineKeyboardButton("🌟 Streak", callback_data="streak"),
        InlineKeyboardButton("🔒 Privacy", url=f"{WEBHOOK_URL}/privacy"),
        InlineKeyboardButton("🗑️ Delete Data", callback_data="delete")
    )
    return markup

user_memory_temp = {}
user_voice_pending = {}

# Start
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    username = message.from_user.username or f"user{uid}"
    referred_by = None
    if len(message.text.split()) > 1:
        try:
            ref = int(message.text.split()[1])
            referred_by = ref if ref != uid else None
        except: pass
    c.execute("SELECT id FROM users WHERE id = ?", (uid,))
    if not c.fetchone():
        now = datetime.utcnow().isoformat()
        c.execute("INSERT INTO users (id, username, referred_by, joined_at) VALUES (?, ?, ?, ?)", (uid, username, referred_by, now))
        if referred_by:
            c.execute("UPDATE users SET points = points + 5 WHERE id = ?", (referred_by,))
            bot.send_message(referred_by, f"🎁 You earned 5 points for inviting @{username}!")
    c.execute("UPDATE users SET is_new = 0 WHERE id = ?", (uid,))
    conn.commit()
    bot.send_message(uid, f"🌱 Welcome @{username} to SoulGarden!\n🧘 Your safe space to grow emotionally.", reply_markup=menu_buttons(uid))

# Button callbacks
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    uid = call.from_user.id
    if call.data == "log":
        bot.send_message(uid, "📝 What's on your mind today?")
        bot.register_next_step_handler_by_chat_id(uid, handle_memory)
    elif call.data == "voice":
        user_voice_pending[uid] = True
        bot.send_message(uid, "🎤 Please send your voice message.")
    elif call.data == "memories":
        return memories_cmd(call.message)
    elif call.data == "explore":
        return explore_cmd(call.message)
    elif call.data == "about":
        return about_cmd(call.message)
    elif call.data == "streak":
    streak = calculate_streak(uid)
    bot.send_message(uid, f"📆 Your current streak is: {streak} days!", reply_markup=menu_buttons(uid))
    elif call.data == "delete":
        return delete_cmd(call.message)
    elif call.data.startswith("mood|"):
        mood = call.data.split("|")[1]
        text = user_memory_temp.pop(uid, None)
        if not text:
            return bot.send_message(uid, "⏳ Timeout. Try again.")
        log_memory(uid, text, mood)
        stats = get_user_stats(uid)
        bot.send_message(uid, f"🌿 Logged!\n📆 Streak: {stats['streak']} | 🌟 Points: {stats['points']}", reply_markup=menu_buttons(uid))

# Memory logging
def handle_memory(message):
    uid = message.from_user.id
    user_memory_temp[uid] = message.text.strip()
    markup = InlineKeyboardMarkup()
    for mood in ["😊 Happy", "😔 Sad", "🤯 Stressed", "💡 Inspired", "😴 Tired"]:
        markup.add(InlineKeyboardButton(mood, callback_data=f"mood|{mood}"))
    bot.send_message(uid, "🧠 Pick a mood:", reply_markup=markup)

# Voice handler
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    uid = message.from_user.id
    if not user_voice_pending.get(uid):
        return
    file_info = bot.get_file(message.voice.file_id)
    downloaded = bot.download_file(file_info.file_path)
    os.makedirs("static/voices", exist_ok=True)
    path = f"static/voices/{uid}_{file_info.file_unique_id}.ogg"
    with open(path, "wb") as f:
        f.write(downloaded)
    log_memory(uid, "(voice note)", "🎧", voice_path=path)
    del user_voice_pending[uid]
    stats = get_user_stats(uid)
    bot.send_message(uid, f"🎧 Voice saved!\n📆 Streak: {stats['streak']} • 🌟 Points: {stats['points']}", reply_markup=menu_buttons(uid))

# Memories
def memories_cmd(message):
    uid = message.chat.id
    c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5", (uid,))
    rows = c.fetchall()
    if not rows:
        return bot.send_message(uid, "📭 No memories yet.")
    msg = "📜 <b>Your recent memories:</b>\n\n"
    for r in rows:
        msg += f"{r[2][:10]} - {r[1]}\n{r[0]}\n\n"
    bot.send_message(uid, msg, parse_mode="HTML")

# Explore
def explore_cmd(message):
    uid = message.chat.id
    c.execute("SELECT DISTINCT user_id FROM memories ORDER BY RANDOM() LIMIT 5")
    for (u,) in c.fetchall():
        c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1", (u,))
        mem = c.fetchone()
        if not mem: continue
        txt = f"🌿 <b>{mem[2][:10]}</b> — {mem[1]}\n{mem[0]}"
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Visit Garden", url=f"{WEBHOOK_URL}/explore/garden/{u}"))
        bot.send_message(uid, txt, parse_mode="HTML", reply_markup=markup)

# Delete
def delete_cmd(message):
    uid = message.chat.id
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("❌ Yes, delete", callback_data="confirm_delete"),
        InlineKeyboardButton("🙅 Cancel", callback_data="cancel_delete")
    )
    bot.send_message(uid, "⚠️ Are you sure you want to delete your data?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["confirm_delete", "cancel_delete"])
def confirm_delete(call):
    uid = call.from_user.id
    if call.data == "cancel_delete":
        return bot.send_message(uid, "🔒 Your data is safe.")
    c.execute("SELECT voice_path FROM memories WHERE user_id = ?", (uid,))
    for path in [r[0] for r in c.fetchall() if r[0]]:
        try: os.remove(path)
        except: pass
    c.execute("DELETE FROM memories WHERE user_id = ?", (uid,))
    c.execute("DELETE FROM users WHERE id = ?", (uid,))
    conn.commit()
    bot.send_message(uid, "🗑️ Data deleted. You can start fresh with /start")

# About
def about_cmd(message):
    bot.send_message(message.chat.id, "🌸 SoulGarden helps you track emotions and grow mentally. Private & safe.")

# Leaderboard
@bot.message_handler(commands=['leaderboard'])
def leaderboard_cmd(message):
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    msg = "🏆 <b>Top Gardeners</b>\n\n" + "\n".join([f"{i+1}. @{r[0]} — {r[1]} pts" for i, r in enumerate(rows)])
    bot.send_message(message.chat.id, msg, parse_mode="HTML")

# Web dashboard
@app.route("/dashboard/<int:user_id>")
def dashboard(user_id):
    c.execute("SELECT username, points FROM users WHERE id = ?", (user_id,))
    u = c.fetchone()
    if not u: return "User not found", 404
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,))
    ref_count = c.fetchone()[0]
    c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id = ?", (user_id,))
    mems = [{"text": r[0], "mood": r[1], "timestamp": r[2]} for r in c.fetchall()]
    return render_template("dashboard.html", name=u[0], points=u[1], streak=calculate_streak(user_id), memories=mems, referrals=ref_count)

# Admin analytics
@app.route("/admin/analytics")
def admin():
    uid = int(request.args.get("uid", 0))
    if uid != ADMIN_ID:
        return "Unauthorized", 403
    today = datetime.utcnow().date().isoformat()
    c.execute("SELECT COUNT(*) FROM users"); total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{today}%",)); new = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memories"); memories = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memories WHERE timestamp LIKE ?", (f"{today}%",)); new_m = c.fetchone()[0]
    return render_template("admin_analytics.html", total_users=total, new_today=new, total_memories=memories, new_memories=new_m)

# Privacy
@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

# Leaderboard
@app.route("/leaderboard")
def leaderboard():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    return render_template("leaderboard.html", leaderboard=rows)




#Status of Bot
@app.route("/")
def index():
    return "🌱 SoulGarden Bot is up."

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.data.decode("utf-8"))
    if update: bot.process_new_updates([update])
    return "OK"

# Daily reminders
def send_daily_reminders():
    c.execute("SELECT id FROM users")
    for (uid,) in c.fetchall():
        try:
            bot.send_message(uid, random.choice([
                "🧘 Reflect a little today?",
                "🌿 How are you feeling?",
                "💬 Log your thoughts — it helps!"
            ]))
        except: continue

scheduler.add_job(send_daily_reminders, 'cron', hour=8)

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=8080)
