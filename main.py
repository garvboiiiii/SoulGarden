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

# DB Tables
c.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, username TEXT UNIQUE, referred_by INTEGER,
    streak INTEGER DEFAULT 0, last_check TEXT, points INTEGER DEFAULT 0,
    joined_at TEXT, last_streak TEXT
)""")
c.execute("""CREATE TABLE IF NOT EXISTS memories (
    user_id INTEGER, text TEXT, mood TEXT,
    timestamp TEXT, voice_path TEXT
)""")
conn.commit()

# Helper Functions
def get_stats(uid):
    c.execute("SELECT streak, points FROM users WHERE id=?", (uid,))
    r = c.fetchone() or (0,0)
    return {"streak": r[0], "points": r[1]}

def valid_streak(uid):
    c.execute("SELECT last_streak FROM users WHERE id=?", (uid,))
    row = c.fetchone()
    if not row or not row[0]: return True
    last = datetime.fromisoformat(row[0])
    return datetime.utcnow() - last >= timedelta(hours=24)

def menu(uid):
    m = InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("📝 Log Memory", "log"), ("🎤 Voice", "voice"),
        ("📜 Memories", "memories"), ("🏆 Leaderboard", "leaderboard"),
        ("🌍 Explore", "explore"), ("📊 Dashboard", f"dashboard"),
        ("🌟 Streak ✅", "streak"), ("🔗 Referral", "referral"),
        ("🔒 Privacy", "privacy"), ("🗑️ Delete", "delete")
    ]
    m.add(*[InlineKeyboardButton(text, callback_data=cd) for text, cd in buttons])
    return m

user_mem = {}
pending_voice = {}

# Commands
@bot.message_handler(commands=['start'])
def start(msg):
    uid, name = msg.from_user.id, msg.from_user.username or f"user{msg.from_user.id}"
    ref = None
    if len(msg.text.split()) > 1:
        try: ref = int(msg.text.split()[1])
        except: pass
    if uid != ref:
        c.execute("INSERT OR IGNORE INTO users (id, username, referred_by, joined_at) VALUES (?,?,?,?)",
                  (uid, name, ref, datetime.utcnow().isoformat()))
        if ref:
            c.execute("UPDATE users SET points=points+5 WHERE id=?", (ref,))
            bot.send_message(ref, f"🎁 +5 points for inviting @{name}")
        conn.commit()
    bot.send_message(uid, "🌱 Welcome to SoulGarden!", reply_markup=menu(uid))

@bot.callback_query_handler(func=lambda c_: True)
def on_callback(c_):
    uid, data = c_.from_user.id, c_.data
    if data == "log":
        bot.send_message(uid, "📝 What's on your mind?")
        bot.register_next_step_handler_by_chat_id(uid, after_mem)
    elif data == "voice":
        pending_voice[uid] = True
        bot.send_message(uid, "🎤 Send your voice message now.")
    elif data == "memories":
        show_memories(uid)
    elif data == "leaderboard":
        send_leaderboard(uid)
    elif data == "explore":
        send_explore(uid)
    elif data == "dashboard":
        bot.send_message(uid, f"📊 Dashboard: {WEBHOOK_URL}/dashboard/{uid}")
    elif data == "streak":
        if valid_streak(uid):
            c.execute("UPDATE users SET streak=streak+1, last_streak=?, points=points+1 WHERE id=?",
                      (datetime.utcnow().isoformat(), uid))
            conn.commit()
            s = get_stats(uid)
            bot.send_message(uid, f"✅ Streak +1! Now at {s['streak']} days.", reply_markup=menu(uid))
        else:
            bot.send_message(uid, "⏳ Wait 24hrs before claiming streak again.", reply_markup=menu(uid))
    elif data == "referral":
        bot.send_message(uid, f"🔗 Share: https://t.me/{bot.get_me().username}?start={uid}")
    elif data == "privacy":
        bot.send_message(uid, f"🔒 Privacy: {WEBHOOK_URL}/privacy")
    elif data == "delete":
        bot.send_message(uid, "⚠️ Confirm delete?", reply_markup=InlineKeyboardMarkup().row(
            InlineKeyboardButton("Yes", callback_data="confirm"),
            InlineKeyboardButton("No", callback_data="cancel")
        ))
    elif data == "confirm":
        delete_all(uid)
    elif data == "cancel":
        bot.send_message(uid, "Cancelled ❌. Your Garden is Safe 😊", reply_markup=menu(uid))

def after_mem(msg):
    uid = msg.from_user.id
    user_mem[uid] = msg.text
    kb = InlineKeyboardMarkup(row_width=2)
    moods = ["😊 Happy", "😔 Sad", "🤯 Stressed", "💡 Inspired", "😴 Tired"]
    kb.add(*[InlineKeyboardButton(m, callback_data="mood|" + m) for m in moods])
    bot.send_message(uid, "Choose your mood:", reply_markup=kb)

@bot.callback_query_handler(lambda c_: c_.data.startswith("mood|"))
def set_mood(c_):
    uid = c_.from_user.id
    mood = c_.data.split("|")[1]
    txt = user_mem.pop(uid, "")
    c.execute("INSERT INTO memories VALUES (?,?,?,?,?)",
              (uid, txt, mood, datetime.utcnow().isoformat(), None))
    c.execute("UPDATE users SET points=points+1 WHERE id=?", (uid,))
    conn.commit()
    s = get_stats(uid)
    bot.send_message(uid, f"🌿 Logged! Streak: {s['streak']} | Points: {s['points']}", reply_markup=menu(uid))

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
                  (uid, "(voice)", "🎧", datetime.utcnow().isoformat(), path))
        c.execute("UPDATE users SET points=points+1 WHERE id=?", (uid,))
        conn.commit()
        s = get_stats(uid)
        bot.send_message(uid, f"🎧 Saved! Points: {s['points']}", reply_markup=menu(uid))

def show_memories(uid):
    c.execute("SELECT text,mood,timestamp FROM memories WHERE user_id=? ORDER BY timestamp DESC LIMIT 5", (uid,))
    rows = c.fetchall()
    if not rows:
        bot.send_message(uid, "No memories yet.", reply_markup=menu(uid))
        return
    msg = "📜 Your recent memories:\n"
    for t, m, ts in rows:
        msg += f"{ts[:10]} – {m} – {t}\n"
    bot.send_message(uid, msg, reply_markup=menu(uid))

def send_leaderboard(uid):
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    if not rows:
        bot.send_message(uid, "No leaderboard data yet.")
        return
    lines = [f"{i+1}. @{u or 'anon'} — {p} pts" for i, (u, p) in enumerate(rows)]
    bot.send_message(uid, "🏆 Top Gardeners:\n" + "\n".join(lines),
                     reply_markup=InlineKeyboardMarkup().row(
                         InlineKeyboardButton("View Web", url=f"{WEBHOOK_URL}/leaderboard")))

def send_explore(uid):
    c.execute("SELECT DISTINCT user_id FROM memories WHERE user_id!=? ORDER BY RANDOM() LIMIT 5", (uid,))
    users = c.fetchall()
    for (other_uid,) in users:
        c.execute("SELECT text,mood,timestamp FROM memories WHERE user_id=? ORDER BY timestamp DESC LIMIT 1", (other_uid,))
        row = c.fetchone()
        if row:
            t, m, ts = row
            bot.send_message(uid, f"🌱 {ts[:10]} – {m}\n{t}",
                             reply_markup=InlineKeyboardMarkup().row(
                                 InlineKeyboardButton("Visit Garden", url=f"{WEBHOOK_URL}/visit_garden/{other_uid}")))

def delete_all(uid):
    c.execute("SELECT voice_path FROM memories WHERE user_id=?", (uid,))
    for (path,) in c.fetchall():
        if path and os.path.exists(path): os.remove(path)
    c.execute("DELETE FROM memories WHERE user_id=?", (uid,))
    c.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    bot.send_message(uid, "🗑️ All data deleted. Use /start to begin again.")

# Web routes
@app.route("/dashboard/<int:uid>")
def dashboard(uid):
    c.execute("SELECT username, points, streak FROM users WHERE id=?", (uid,))
    u = c.fetchone() or ("Unknown", 0, 0)
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (uid,))
    rc = c.fetchone()[0]
    c.execute("SELECT text,mood,timestamp,voice_path FROM memories WHERE user_id=?", (uid,))
    mems = [{"text": t, "mood": m, "time": ts, "voice": vp} for t, m, ts, vp in c.fetchall()]
    return render_template("dashboard.html", name=u[0], points=u[1], streak=u[2], referrals=rc, memories=mems)

@app.route("/leaderboard")
def leaderboard():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    return render_template("leaderboard.html", lb=c.fetchall())

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
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memories")
    memories = c.fetchone()[0]
    return render_template("admin_analytics.html", users=users, memories=memories)

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode())])
    return "OK"

@app.route("/")
def home(): return "🌱 SoulGarden Running"

def daily():
    for (uid,) in c.execute("SELECT id FROM users"):
        try:
            bot.send_message(uid, random.choice([
                "🧘 Reflect today?", "🌿 Feeling okay?", "💬 Time to log thoughts?",
                "✨ Grow with reflection.", "🍃 Journaling = self-care."
            ]))
        except: pass

scheduler.add_job(daily, trigger='cron', hour=8)

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=8080)
