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
ADMIN_ID = os.getenv("ADMIN_ID")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, static_folder="static", template_folder="templates")
scheduler = BackgroundScheduler()
scheduler.start()

conn = sqlite3.connect("garden.db", check_same_thread=False)
c = conn.cursor()

# DB Setup
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

# Helper: Stats
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

# Menu
def menu_buttons(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📝 Log Memory", callback_data="log"),
        InlineKeyboardButton("🎤 Voice Note", callback_data="voice"),
        InlineKeyboardButton("📜 My Memories", callback_data="memories"),
        InlineKeyboardButton("🏆 Leaderboard", url=f"{WEBHOOK_URL}/leaderboard"),
        InlineKeyboardButton("🌍 Explore", callback_data="explore"),
        InlineKeyboardButton("📊 Dashboard", url=f"{WEBHOOK_URL}/dashboard/{user_id}"),
        InlineKeyboardButton("ℹ️ About", callback_data="about"),
        InlineKeyboardButton("🗑️ Delete Data", callback_data="delete")
    )
    return markup

user_memory_temp = {}

# Commands
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    username = message.from_user.username or f"user{uid}"
    referred_by = None
    if len(message.text.split()) > 1:
        try:
            ref = int(message.text.split()[1])
            referred_by = ref if ref != uid else None
        except:
            pass

    c.execute("SELECT id FROM users WHERE id = ?", (uid,))
    if not c.fetchone():
        now = datetime.utcnow().isoformat()
        c.execute("INSERT INTO users (id, username, referred_by, joined_at) VALUES (?, ?, ?, ?)",
                  (uid, username, referred_by, now))
        if referred_by:
            c.execute("UPDATE users SET points = points + 4 WHERE id = ?", (referred_by,))
            bot.send_message(referred_by, f"🎁 You earned 4 points for inviting @{username}!")
        conn.commit()
        bot.send_message(uid,
            f"🌱 <b>Welcome to SoulGarden</b>, @{username}!\n"
            "Your mental health sanctuary.\n\n"
            "✅ Log daily thoughts\n🎤 Share voice notes\n🌍 Explore anonymous gardens\n🏆 Earn points & streaks\n",
            parse_mode="HTML")
        bot.send_photo(uid, photo=open("static/sprout.jpg", "rb"))
    else:
        c.execute("UPDATE users SET is_new = 0 WHERE id = ?", (uid,))
    conn.commit()
    bot.send_message(uid, "🌸 Welcome back to SoulGarden!" if referred_by is None else "🌸 Enjoy your growth journey!", reply_markup=menu_buttons(uid))

@bot.message_handler(commands=['referral'])
def referral(message):
    uid = message.from_user.id
    bot.send_message(uid, f"🔗 Your referral link:\nhttps://t.me/s0ulGarden_Bot?start={uid}")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    bot.send_message(message.chat.id, "💡 Use /log to write, /voice to record, or /explore to discover other gardens.")

# Logging
@bot.message_handler(commands=['log'])
def log_cmd(message):
    bot.send_message(message.chat.id, "📝 What's on your mind today?")
    bot.register_next_step_handler(message, handle_memory)

def handle_memory(message):
    uid = message.from_user.id
    text = message.text.strip()
    if not text:
        bot.send_message(uid, "❗Please type something.")
        return
    user_memory_temp[uid] = text
    markup = InlineKeyboardMarkup()
    for mood in ["😊 Happy", "😔 Sad", "🤯 Stressed", "💡 Inspired", "😴 Tired"]:
        markup.add(InlineKeyboardButton(mood, callback_data=f"mood|{mood}"))
    bot.send_message(uid, "💬 Pick a mood:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mood|"))
def handle_mood(call):
    uid = call.from_user.id
    mood = call.data.split("|", 1)[1]
    text = user_memory_temp.pop(uid, None)
    if not text:
        bot.send_message(uid, "⏳ Timeout! Try again.")
        return
    log_memory(uid, text, mood)
    now = datetime.utcnow().isoformat()
    c.execute("UPDATE users SET streak = streak + 1, last_entry = ?, points = points + 1 WHERE id = ?", (now, uid))
    conn.commit()
    stats = get_user_stats(uid)
    bot.send_message(uid, f"🌱 Memory saved!\n📆 Streak: {stats['streak']} days\n🌟 Points: {stats['points']}")
    bot.send_message(uid, random.choice([
        "🌟 You're doing better than you think.",
        "💪 Logging emotions is an act of bravery.",
        "🌿 Healing begins with self-awareness.",
        "🌸 You planted a seed of strength today.",
        "✨ You matter, and so do your memories."
    ]), reply_markup=menu_buttons(uid))

# Voice
@bot.message_handler(commands=['voice'])
def voice_cmd(message):
    bot.send_message(message.chat.id, "🎤 Send your voice note now.")

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    uid = message.from_user.id
    file_info = bot.get_file(message.voice.file_id)
    downloaded = bot.download_file(file_info.file_path)
    os.makedirs("static/voices", exist_ok=True)
    path = f"static/voices/{uid}_{file_info.file_unique_id}.ogg"
    with open(path, "wb") as f:
        f.write(downloaded)
    log_memory(uid, "(voice note)", "🎧", voice_path=path)
    now = datetime.utcnow().isoformat()
    c.execute("UPDATE users SET streak = streak + 1, last_entry = ?, points = points + 1 WHERE id = ?", (now, uid))
    conn.commit()
    stats = get_user_stats(uid)
    bot.send_message(uid, f"🎧 Voice saved!\n📆 Streak: {stats['streak']} • 🌟 Points: {stats['points']}")
    bot.send_message(uid, random.choice([
        "🌟 You're doing better than you think.",
        "💪 Logging emotions is an act of bravery.",
        "🌿 Healing begins with self-awareness.",
        "🌸 You planted a seed of strength today.",
        "✨ You matter, and so do your memories."
    ]))

# Memories
@bot.message_handler(commands=['memories'])
def memories_cmd(message):
    uid = message.from_user.id
    c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5", (uid,))
    rows = c.fetchall()
    if not rows:
        bot.send_message(uid, "📭 No memories yet.")
        return
    reply = "🧠 <b>Your Memories:</b>\n\n"
    for r in rows:
        reply += f"{r[2][:10]} - {r[1]}\n{r[0]}\n\n"
    bot.send_message(uid, reply, parse_mode="HTML")

# Explore
@bot.message_handler(commands=['explore'])
def explore_cmd(message):
    uid = message.chat.id
    c.execute("SELECT DISTINCT user_id FROM memories ORDER BY RANDOM() LIMIT 5")
    for u, in c.fetchall():
        c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1", (u,))
        mem = c.fetchone()
        if not mem:
            continue
        txt = f"🌿 <b>{mem[2][:10]}</b> — {mem[1]}\n{mem[0]}"
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Visit Garden", url=f"{WEBHOOK_URL}/explore/garden/{u}"))
        bot.send_message(uid, txt, parse_mode="HTML", reply_markup=markup)

# Delete
@bot.message_handler(commands=['delete'])
def delete_cmd(message):
    uid = message.from_user.id
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("❌ Yes, delete", callback_data="confirm_delete"),
        InlineKeyboardButton("🙅 Cancel", callback_data="cancel_delete")
    )
    bot.send_message(uid, "⚠️ Are you sure you want to delete your data?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["confirm_delete", "cancel_delete"])
def handle_delete(call):
    uid = call.from_user.id
    if call.data == "cancel_delete":
        bot.send_message(uid, "🔒 Your garden is safe.")
    else:
        c.execute("SELECT voice_path FROM memories WHERE user_id = ?", (uid,))
        for path in [r[0] for r in c.fetchall() if r[0]]:
            try: os.remove(path)
            except: pass
        c.execute("DELETE FROM memories WHERE user_id = ?", (uid,))
        c.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.commit()
        bot.send_message(uid, "🗑️ Data deleted. Start again with /start")

# About
@bot.message_handler(commands=['about'])
def about_cmd(message):
    bot.send_message(message.chat.id, "🌸 SoulGarden helps you track emotions and grow mentally. Safe & private.")

@bot.message_handler(commands=["leaderboard"])
def leaderboard_cmd(message):
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    msg = "🏆 <b>Top Gardeners</b>\n\n" + "\n".join([f"{i+1}. @{r[0]} — {r[1]} pts" for i, r in enumerate(rows)])
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🌐 View Online", url=f"{WEBHOOK_URL}/leaderboard"))
    bot.send_message(message.chat.id, msg, parse_mode="HTML", reply_markup=markup)

# Web Dashboard
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

@app.route("/admin/analytics")
def admin_analytics():
    uid = int(request.args.get("uid", 0))
    if uid != ADMIN_ID:
        return "Unauthorized", 403
    today = datetime.utcnow().date().isoformat()
    c.execute("SELECT COUNT(*) FROM users"); total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{today}%",)); new_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memories"); total_memories = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memories WHERE timestamp LIKE ?", (f"{today}%",)); new_memories = c.fetchone()[0]
    return render_template("admin_analytics.html", **{
        "total_users": total_users, "new_today": new_today,
        "total_memories": total_memories, "new_memories": new_memories
    })

@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.data.decode("utf-8"))
    if update:
        bot.process_new_updates([update])
    return "OK"

@app.route("/")
def index():
    return "🌸 SoulGarden Bot is live."

# Daily push notification
def send_daily_reminders():
    c.execute("SELECT id FROM users")
    for row in c.fetchall():
        try:
            bot.send_message(row[0], random.choice([
                "🌞 New day, new thoughts. Share something!",
                "💭 Take 2 mins and write a memory today.",
                "🪴 Your garden is waiting for a new entry."
            ]))
        except: continue

scheduler.add_job(send_daily_reminders, 'cron', hour=9)

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=8080)
