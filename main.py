# main.py

import os, sqlite3, random, telebot
from datetime import datetime, timedelta
from flask import Flask, request, render_template
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler

# Env vars
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1335511330"))

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, template_folder="templates", static_folder="static")
scheduler = BackgroundScheduler()
scheduler.start()

# Database
conn = sqlite3.connect("garden.db", check_same_thread=False)
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, username TEXT, referred_by INTEGER,
    streak INTEGER DEFAULT 0, last_streak TEXT, points INTEGER DEFAULT 0,
    joined_at TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS memories (
    user_id INTEGER, text TEXT, mood TEXT, timestamp TEXT, voice_path TEXT
)""")
conn.commit()

# Inline menu
def menu(uid):
    m = InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("📝 Log", "log"), ("🎤 Voice", "voice"),
        ("📜 Memories", "memories"), ("🏆 Leaderboard", "leaderboard"),
        ("🌍 Explore", "explore"), ("📊 Dashboard", f"dashboard"),
        ("🌟 Streak", "streak"), ("🔗 Referral", "referral"),
        ("📖 Help", "help"), ("🔒 Privacy", "privacy"),
        ("🧘 About", "about"), ("🗑️ Delete", "delete")
    ]
    m.add(*[InlineKeyboardButton(t, callback_data=cb) for t, cb in buttons])
    return m

# Helpers
user_mem, pending_voice = {}, {}

def get_stats(uid):
    c.execute("SELECT streak, points FROM users WHERE id=?", (uid,))
    r = c.fetchone() or (0, 0)
    return {"streak": r[0], "points": r[1]}

def valid_streak(uid):
    c.execute("SELECT last_streak FROM users WHERE id=?", (uid,))
    r = c.fetchone()
    if not r or not r[0]: return True
    return datetime.utcnow() - datetime.fromisoformat(r[0]) >= timedelta(days=1)

# Start
@bot.message_handler(commands=['start'])
def start(msg):
    uid, username = msg.from_user.id, msg.from_user.username or f"user{msg.from_user.id}"
    ref = None
    if len(msg.text.split()) > 1:
        try: ref = int(msg.text.split()[1])
        except: pass
    if uid != ref:
        c.execute("INSERT OR IGNORE INTO users (id, username, referred_by, joined_at) VALUES (?,?,?,?)",
                  (uid, username, ref, datetime.utcnow().isoformat()))
        if ref:
            c.execute("UPDATE users SET points = points + 5 WHERE id=?", (ref,))
            bot.send_message(ref, f"🎁 You earned 5 points for inviting @{username}")
        conn.commit()
    bot.send_message(uid, f"🌱 Welcome to SoulGarden @{username}!", reply_markup=menu(uid))

# Callback handler
@bot.callback_query_handler(func=lambda call: True)
def on_callback(call):
    uid, data = call.from_user.id, call.data
    if data == "log":
        bot.send_message(uid, "📝 What's on your mind today?")
        bot.register_next_step_handler_by_chat_id(uid, after_memory)
    elif data == "voice":
        pending_voice[uid] = True
        bot.send_message(uid, "🎤 Send your voice note now.")
    elif data == "memories":
        show_memories(uid)
    elif data == "leaderboard":
        show_leaderboard(uid)
    elif data == "explore":
        show_explore(uid)
    elif data == "dashboard":
        bot.send_message(uid, f"📊 View Dashboard:\n{WEBHOOK_URL}/dashboard/{uid}")
    elif data == "streak":
        if valid_streak(uid):
            c.execute("UPDATE users SET streak = streak + 1, last_streak = ?, points = points + 1 WHERE id=?",
                      (datetime.utcnow().isoformat(), uid))
            conn.commit()
            s = get_stats(uid)
            bot.send_message(uid, f"✅ Streak +1!\nStreak: {s['streak']} 🌟 Points: {s['points']}", reply_markup=menu(uid))
        else:
            bot.send_message(uid, "⏳ You can claim streak once every 24 hours.", reply_markup=menu(uid))
    elif data == "referral":
        bot.send_message(uid, f"🔗 Share your referral:\nhttps://t.me/{bot.get_me().username}?start={uid}")
    elif data == "privacy":
        bot.send_message(uid, f"🔒 Privacy Policy:\n{WEBHOOK_URL}/privacy")
    elif data == "about":
        bot.send_message(uid, "🧘 SoulGarden helps you reflect and grow through daily journaling and voice logs.")
    elif data == "help":
        bot.send_message(uid, """📖 Help Guide:

📝 Log - Write your emotion
🎤 Voice - Speak your thoughts
📊 Dashboard - View your stats
🌟 Streak - Daily log bonus
🔗 Referral - Invite & earn points
🗑️ Delete - Remove your data safely
""")
    elif data == "delete":
        bot.send_message(uid, "⚠️ Confirm delete?", reply_markup=InlineKeyboardMarkup().row(
            InlineKeyboardButton("✅ Yes", callback_data="confirm"),
            InlineKeyboardButton("❌ No", callback_data="cancel")))
    elif data == "confirm":
        delete_user(uid)
    elif data == "cancel":
        bot.send_message(uid, "Deletion cancelled.", reply_markup=menu(uid))
    elif data.startswith("mood|"):
        set_mood(uid, data.split("|")[1])

def after_memory(msg):
    user_mem[msg.from_user.id] = msg.text
    kb = InlineKeyboardMarkup(row_width=2)
    moods = ["😊 Happy", "😔 Sad", "🤯 Stressed", "💡 Inspired", "😴 Tired"]
    kb.add(*[InlineKeyboardButton(m, callback_data=f"mood|{m}") for m in moods])
    bot.send_message(msg.chat.id, "Select a mood:", reply_markup=kb)

def set_mood(uid, mood):
    text = user_mem.pop(uid, "(empty)")
    now = datetime.utcnow().isoformat()
    c.execute("INSERT INTO memories VALUES (?, ?, ?, ?, ?)", (uid, text, mood, now, None))
    c.execute("UPDATE users SET points = points + 1 WHERE id=?", (uid,))
    conn.commit()
    mot = random.choice([
        "🌞 You're doing great!", "🌻 Keep expressing yourself.",
        "💫 Another day of growth.", "🌿 Reflection brings clarity.",
        "🍀 You're never alone here.", "🌼 Healing is nonlinear."
    ])
    s = get_stats(uid)
    bot.send_message(uid, f"✅ Logged!\nStreak: {s['streak']} • Points: {s['points']}\n\n<b>{mot}</b>", parse_mode="HTML", reply_markup=menu(uid))

@bot.message_handler(content_types=['voice'])
def on_voice(msg):
    uid = msg.from_user.id
    if pending_voice.pop(uid, None):
        f = bot.get_file(msg.voice.file_id)
        data = bot.download_file(f.file_path)
        os.makedirs("static/voices", exist_ok=True)
        path = f"static/voices/{uid}_{msg.message_id}.ogg"
        with open(path, "wb") as f_: f_.write(data)
        c.execute("INSERT INTO memories VALUES (?, ?, ?, ?, ?)", (uid, "(voice)", "🎧", datetime.utcnow().isoformat(), path))
        c.execute("UPDATE users SET points = points + 1 WHERE id=?", (uid,))
        conn.commit()
        mot = random.choice(["🌼 Great journaling!", "🌙 Let go, let grow.", "✨ Self-expression is healing."])
        s = get_stats(uid)
        bot.send_message(uid, f"🎧 Voice saved!\nPoints: {s['points']}\n\n<b>{mot}</b>", parse_mode="HTML", reply_markup=menu(uid))

# Utility Functions
def show_memories(uid):
    c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id=? ORDER BY timestamp DESC LIMIT 5", (uid,))
    rows = c.fetchall()
    if not rows: return bot.send_message(uid, "No memories yet.", reply_markup=menu(uid))
    msg = "📜 Your last memories:\n" + "\n".join([f"{r[2][:10]} – {r[1]} – {r[0]}" for r in rows])
    bot.send_message(uid, msg, reply_markup=menu(uid))

def show_leaderboard(uid):
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    if not rows:
        bot.send_message(uid, "🏆 No data yet.")
        return
    text = "🏆 Top Gardeners:\n" + "\n".join([f"{i+1}. @{u or 'anon'} — {p} pts" for i, (u, p) in enumerate(rows)])
    bot.send_message(uid, text, reply_markup=InlineKeyboardMarkup().row(
        InlineKeyboardButton("🌐 View Web", url=f"{WEBHOOK_URL}/leaderboard")))

def show_explore(uid):
    c.execute("SELECT DISTINCT user_id FROM memories WHERE user_id != ? ORDER BY RANDOM() LIMIT 5", (uid,))
    for (other,) in c.fetchall():
        c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1", (other,))
        r = c.fetchone()
        if r:
            t, m, ts = r
            bot.send_message(uid, f"🌿 {ts[:10]} – {m}\n{t}",
                             reply_markup=InlineKeyboardMarkup().row(
                                 InlineKeyboardButton("🔍 Visit Garden", url=f"{WEBHOOK_URL}/visit_garden/{other}")))

def delete_user(uid):
    c.execute("SELECT voice_path FROM memories WHERE user_id=?", (uid,))
    for (p,) in c.fetchall():
        if p and os.path.exists(p): os.remove(p)
    c.execute("DELETE FROM memories WHERE user_id=?", (uid,))
    c.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    bot.send_message(uid, "🗑️ All your data has been deleted.")

# Flask Routes
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook(): 
    bot.process_new_updates([telebot.types.Update.de_json(request.data.decode("utf-8"))])
    return "OK"

@app.route("/")
def home(): return "🌱 SoulGarden is alive"

@app.route("/dashboard/<int:uid>")
def dashboard(uid):
    c.execute("SELECT username, points, streak FROM users WHERE id=?", (uid,))
    u = c.fetchone() or ("unknown", 0, 0)
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (uid,))
    referrals = c.fetchone()[0]
    c.execute("SELECT text,mood,timestamp,voice_path FROM memories WHERE user_id=?", (uid,))
    mems = [{"text":t,"mood":m,"time":ts,"voice":vp} for t,m,ts,vp in c.fetchall()]
    return render_template("dashboard.html", name=u[0], points=u[1], streak=u[2], referrals=referrals, memories=mems)

@app.route("/leaderboard")
def leaderboard():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    return render_template("leaderboard.html", users=c.fetchall())

@app.route("/visit_garden/<int:uid>")
def visit(uid):
    c.execute("SELECT username FROM users WHERE id=?", (uid,))
    user = c.fetchone()
    if not user: return "User not found", 404
    c.execute("SELECT text,mood,timestamp,voice_path FROM memories WHERE user_id=? ORDER BY timestamp DESC LIMIT 10", (uid,))
    mems = [{"text": t, "mood": m, "time": ts, "voice": vp} for t, m, ts, vp in c.fetchall()]
    return render_template("visit_garden.html", name=user[0], memories=mems)

@app.route("/privacy")
def privacy(): return render_template("privacy.html")

@app.route("/admin/analytics")
def analytics():
    if int(request.args.get("uid", 0)) != ADMIN_ID: return "403", 403
    c.execute("SELECT COUNT(*) FROM users"); users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memories"); memories = c.fetchone()[0]
    return render_template("admin_analytics.html", users=users, memories=memories)

# Daily Reminder Job
def daily():
    for (uid,) in c.execute("SELECT id FROM users"):
        try:
            bot.send_message(uid, random.choice([
                "🧘 Reflect today?", "🌿 Feeling okay?",
                "💬 Time to log your mind.", "🍃 Breathe. Log. Grow."
            ]))
        except: pass

scheduler.add_job(daily, trigger='cron', hour=8)

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=8080)
