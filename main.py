import os, sqlite3, random, telebot
from datetime import datetime, timedelta
from flask import Flask, request, render_template
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1335511330"))

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, template_folder="templates", static_folder="static")
scheduler = BackgroundScheduler()
scheduler.start()

conn = sqlite3.connect("garden.db", check_same_thread=False)
c = conn.cursor()

# --- DATABASE ---
c.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, username TEXT UNIQUE, referred_by INTEGER,
    streak INTEGER DEFAULT 0, last_check TEXT, points INTEGER DEFAULT 0,
    joined_at TEXT, last_streak TEXT
)""")
c.execute("""CREATE TABLE IF NOT EXISTS memories (
    user_id INTEGER, text TEXT, mood INTEGER,
    timestamp TEXT, voice_path TEXT
)""")
conn.commit()

# --- MOOD MAP ---
MOOD_MAP = {
    "😊 Happy": 1, "😔 Sad": 2, "🤯 Stressed": 3,
    "💡 Inspired": 4, "😴 Tired": 5, "🎧": 0
}
MOOD_REVERSE = {v: k for k, v in MOOD_MAP.items()}

# --- UTILS ---
def get_stats(uid):
    c.execute("SELECT streak, points FROM users WHERE id=?", (uid,))
    r = c.fetchone() or (0, 0)
    return {"streak": r[0], "points": r[1]}

def valid_streak(uid):
    c.execute("SELECT last_streak FROM users WHERE id=?", (uid,))
    row = c.fetchone()
    if not row or not row[0]: return True
    last = datetime.fromisoformat(row[0])
    return datetime.utcnow() - last >= timedelta(hours=24)

def motivation():
    return random.choice([
        "🌞 You're doing great!", "🌻 Keep expressing yourself.",
        "🌊 Let your thoughts flow.", "💫 Another day of growth.",
        "🌿 Reflection brings clarity.", "🌸 Peace begins with you.",
        "🍀 You're never alone here.", "✨ Great job journaling!",
        "🌙 Let go, let grow.", "🌼 Healing is nonlinear."
    ])

# --- INLINE MENU ---
def menu(uid):
    m = InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("📝 Log", "log"), ("🎤 Voice", "voice"),
        ("📜 Memories", "memories"), ("🏆 Leaderboard", "leaderboard"),
        ("🌍 Explore", "explore"), ("📊 Dashboard", "dashboard"),
        ("🌟 Streak", "streak"), ("🔗 Referral", "referral"),
        ("📖 Help", "help"), ("🔒 Privacy", "privacy"),
        ("🧘 About", "about"), ("🗑️ Delete", "delete")
    ]
    for text, cb in buttons:
        m.add(InlineKeyboardButton(text, callback_data=cb))
    if uid == ADMIN_ID:
        m.add(InlineKeyboardButton("📈 Admin Analytics", url=f"{WEBHOOK_URL}/admin/analytics?uid={uid}"))
    return m

user_mem = {}
pending_voice = {}

# --- START ---
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
            c.execute("UPDATE users SET points=points+5 WHERE id=?", (ref,))
            bot.send_message(ref, f"🎁 +5 points for inviting @{username}")
        conn.commit()
    bot.send_message(uid, "🌱 Welcome to SoulGarden!", reply_markup=menu(uid))

# --- CALLBACK HANDLER ---
@bot.callback_query_handler(func=lambda c_: True)
def on_callback(c_):
    uid, data = c_.from_user.id, c_.data
    if data == "log":
        bot.send_message(uid, "📝 What's on your mind?")
        bot.register_next_step_handler_by_chat_id(uid, after_mem)
    elif data == "voice":
        pending_voice[uid] = True
        bot.send_message(uid, "🎤 Send your voice now.")
    elif data == "memories":
        show_memories(uid)
    elif data == "leaderboard":
        send_leaderboard(uid)
    elif data == "explore":
        send_explore(uid)
    elif data == "dashboard":
        bot.send_message(uid, f"📊 Dashboard:\n{WEBHOOK_URL}/dashboard/{uid}")
    elif data == "streak":
        if valid_streak(uid):
            c.execute("UPDATE users SET streak=streak+1, last_streak=?, points=points+1 WHERE id=?",
                      (datetime.utcnow().isoformat(), uid))
            conn.commit()
            s = get_stats(uid)
            bot.send_message(uid, f"✅ +1 Streak! Total: {s['streak']}", reply_markup=menu(uid))
        else:
            bot.send_message(uid, "⏳ Come back after 24hrs.", reply_markup=menu(uid))
    elif data == "referral":
        bot.send_message(uid, f"🔗 Share link:\nhttps://t.me/{bot.get_me().username}?start={uid}")
    elif data == "help":
        bot.send_message(uid, "ℹ️ Use this bot to log emotions & voice notes.\nEarn streaks, refer friends, explore minds.\nStart journaling with one tap!")
    elif data == "about":
        bot.send_message(uid, "🧘 SoulGarden is your emotional garden.\n🌿 Plant daily memories. 🌟 Grow awareness.\n🎤 Reflect with voice, share anonymously.")
    elif data == "privacy":
        bot.send_message(uid, f"🔒 Read privacy policy:\n{WEBHOOK_URL}/privacy")
    elif data == "delete":
        kb = InlineKeyboardMarkup().row(
            InlineKeyboardButton("❌ Yes", callback_data="confirm"),
            InlineKeyboardButton("🙅 Cancel", callback_data="cancel"))
        bot.send_message(uid, "⚠️ Confirm delete your data?", reply_markup=kb)
    elif data == "confirm":
        delete_all(uid)
    elif data == "cancel":
        bot.send_message(uid, "✅ Your garden is safe.", reply_markup=menu(uid))

# --- MOOD FLOW ---
def after_mem(msg):
    uid = msg.from_user.id
    user_mem[uid] = msg.text
    kb = InlineKeyboardMarkup(row_width=2)
    for mood in list(MOOD_MAP.keys())[:-1]:
        kb.add(InlineKeyboardButton(mood, callback_data="mood|" + mood))
    bot.send_message(uid, "Choose mood:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c_: c_.data.startswith("mood|"))
def set_mood(c_):
    uid = c_.from_user.id
    mood = c_.data.split("|")[1]
    mood_val = MOOD_MAP.get(mood, 0)
    txt = user_mem.pop(uid, "")
    c.execute("INSERT INTO memories VALUES (?,?,?,?,?)",
              (uid, txt, mood_val, datetime.utcnow().isoformat(), None))
    c.execute("UPDATE users SET points=points+1 WHERE id=?", (uid,))
    conn.commit()
    s = get_stats(uid)
    bot.send_message(uid, f"🌿 Logged!\nStreak: {s['streak']} | Points: {s['points']}\n\n<b>{motivation()}</b>",
                     parse_mode="HTML", reply_markup=menu(uid))

# --- VOICE HANDLER ---
@bot.message_handler(content_types=['voice'])
def handle_voice(msg):
    uid = msg.from_user.id
    if pending_voice.pop(uid, None):
        f = bot.get_file(msg.voice.file_id)
        data = bot.download_file(f.file_path)
        os.makedirs("static/voices", exist_ok=True)
        path = f"static/voices/{uid}_{msg.message_id}.ogg"
        with open(path, "wb") as f_: f_.write(data)
        c.execute("INSERT INTO memories VALUES (?,?,?,?,?)",
                  (uid, "(voice)", 0, datetime.utcnow().isoformat(), path))
        c.execute("UPDATE users SET points=points+1 WHERE id=?", (uid,))
        conn.commit()
        s = get_stats(uid)
        bot.send_message(uid, f"🎧 Saved!\nPoints: {s['points']}\n<b>{motivation()}</b>", parse_mode="HTML", reply_markup=menu(uid))

# --- FEATURES ---
def show_memories(uid):
    c.execute("SELECT text,mood,timestamp FROM memories WHERE user_id=? ORDER BY timestamp DESC LIMIT 5", (uid,))
    rows = c.fetchall()
    if not rows:
        bot.send_message(uid, "📭 No memories found.", reply_markup=menu(uid))
        return
    msg = "📜 Your Memories:\n\n"
    for t, m, ts in rows:
        mood = MOOD_REVERSE.get(m, "🌿")
        msg += f"{ts[:10]} • {mood}\n{t}\n\n"
    bot.send_message(uid, msg, reply_markup=menu(uid))

def send_leaderboard(uid):
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    if not rows:
        bot.send_message(uid, "No leaderboard data yet.")
        return
    msg = "\n".join([f"{i+1}. @{u or 'anon'} — {p} pts" for i, (u, p) in enumerate(rows)])
    bot.send_message(uid, f"🏆 Top Gardeners:\n{msg}", reply_markup=InlineKeyboardMarkup().row(
        InlineKeyboardButton("🌐 Web View", url=f"{WEBHOOK_URL}/leaderboard")))

def send_explore(uid):
    c.execute("SELECT DISTINCT user_id FROM memories WHERE user_id != ? ORDER BY RANDOM() LIMIT 5", (uid,))
    for (u,) in c.fetchall():
        c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id=? ORDER BY timestamp DESC LIMIT 1", (u,))
        row = c.fetchone()
        if row:
            text, mood_val, ts = row
            mood = MOOD_REVERSE.get(mood_val, "🌿")
            bot.send_message(uid, f"🌱 {ts[:10]} • {mood}\n{text}",
                             reply_markup=InlineKeyboardMarkup().row(
                                 InlineKeyboardButton("🌸 Visit Garden", url=f"{WEBHOOK_URL}/visit_garden/{u}")))

def delete_all(uid):
    c.execute("SELECT voice_path FROM memories WHERE user_id=?", (uid,))
    for (p,) in c.fetchall():
        if p and os.path.exists(p): os.remove(p)
    c.execute("DELETE FROM memories WHERE user_id=?", (uid,))
    c.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    bot.send_message(uid, "🗑️ Your data is deleted. Use /start again.")

# --- FLASK ROUTES ---
@app.route("/dashboard/<int:uid>")
def dashboard(uid):
    c.execute("SELECT username, points, streak FROM users WHERE id=?", (uid,))
    u = c.fetchone() or ("Unknown", 0, 0)
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (uid,))
    referrals = c.fetchone()[0]
    c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id=?", (uid,))
    mems = []
    for t, m, ts, vp in c.fetchall():
        mems.append({
            "text": t, "mood": MOOD_REVERSE.get(m, "🪴"),
            "time": ts[:10] if ts else "N/A",
            "voice": vp if vp and os.path.exists(vp) else None
        })
    return render_template("dashboard.html", name=u[0], points=u[1], streak=u[2], referrals=referrals, memories=mems)

@app.route("/leaderboard")
def leaderboard():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    return render_template("leaderboard.html", lb=c.fetchall())

@app.route("/visit_garden/<int:uid>")
def visit(uid):
    c.execute("SELECT username FROM users WHERE id=?", (uid,))
    u = c.fetchone()
    if not u: return "User not found", 404
    c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id=? ORDER BY timestamp DESC LIMIT 10", (uid,))
    mems = []
    for t, m, ts, vp in c.fetchall():
        mems.append({
            "text": t, "mood": MOOD_REVERSE.get(m, "🪴"),
            "time": ts[:10] if ts else "N/A",
            "voice": vp if vp and os.path.exists(vp) else None
        })
    return render_template("visit_garden.html", name=u[0], memories=mems)

@app.route("/privacy")
def privacy(): return render_template("privacy.html")

@app.route("/admin/analytics")
def analytics():
    if int(request.args.get("uid", 0)) != ADMIN_ID: return "403", 403
    c.execute("SELECT COUNT(*) FROM users"); users = c.fetchone()[0]
    today = datetime.utcnow().date().isoformat()
    c.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{today}%",)); joined_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memories"); mems = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memories WHERE timestamp LIKE ?", (f"{today}%",)); mems_today = c.fetchone()[0]
    return render_template("admin_analytics.html", users=users, today=joined_today, memories=mems, logs_today=mems_today)

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode())])
    return "OK"

@app.route("/")
def home(): return "🌱 SoulGarden is Alive"

def daily():
    for (uid,) in c.execute("SELECT id FROM users"):
        try:
            bot.send_message(uid, random.choice([
                "🧘 Reflect today?", "🌿 Feeling okay?", "💬 Time to log thoughts?",
                "✨ Grow with reflection.", "🍃 Journaling = self-care."
            ]))
        except: continue

scheduler.add_job(daily, trigger='cron', hour=8)

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=8080)
