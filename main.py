import os, sqlite3, random, telebot
from datetime import datetime, timedelta
from flask import Flask, request, render_template
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, User, CallbackQuery
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

# DB Setup
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

user_mem = {}
pending_voice = {}

# Menu
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

# Helpers
def get_stats(uid):
    c.execute("SELECT streak, points FROM users WHERE id=?", (uid,))
    r = c.fetchone() or (0,0)
    return {"streak": r[0], "points": r[1]}

def valid_streak(uid):
    c.execute("SELECT last_streak FROM users WHERE id=?", (uid,))
    row = c.fetchone()
    if not row or not row[0]: return True
    return datetime.utcnow() - datetime.fromisoformat(row[0]) >= timedelta(hours=24)

def motivation():
    return random.choice([
        "🌞 You're doing great!", "🌻 Keep expressing yourself.",
        "🌊 Let your thoughts flow.", "💫 Another day of growth.",
        "🌿 Reflection brings clarity.", "🌸 Peace begins with you.",
        "🍀 You're never alone here.", "✨ Great job journaling!",
        "🌙 Let go, let grow.", "🌼 Healing is nonlinear."
    ])

# /start + / commands
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.from_user.id
    name = msg.from_user.username or f"user{uid}"
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

def create_fake_callback(msg, data_value):
    fake_cb = CallbackQuery(
        id=str(msg.message_id),
        from_user=msg.from_user,
        chat_instance=str(msg.chat.id),
        message=None,
        inline_message_id=None,
        data=data_value
    )
    on_callback(fake_cb)

@bot.message_handler(commands=['log'])
def log_cmd(msg): create_fake_callback(msg, "log")

@bot.message_handler(commands=['voice'])
def voice_cmd(msg): create_fake_callback(msg, "voice")

@bot.message_handler(commands=['memories'])
def mem_cmd(msg): create_fake_callback(msg, "memories")

@bot.message_handler(commands=['leaderboard'])
def lead_cmd(msg): create_fake_callback(msg, "leaderboard")

@bot.message_handler(commands=['explore'])
def explore_cmd(msg): create_fake_callback(msg, "explore")

@bot.message_handler(commands=['dashboard'])
def dash_cmd(msg): create_fake_callback(msg, "dashboard")

@bot.message_handler(commands=['referral'])
def ref_cmd(msg): create_fake_callback(msg, "referral")

@bot.message_handler(commands=['streak'])
def streak_cmd(msg): create_fake_callback(msg, "streak")

@bot.message_handler(commands=['delete'])
def delete_cmd(msg): create_fake_callback(msg, "delete")

@bot.message_handler(commands=['privacy'])
def privacy_cmd(msg): create_fake_callback(msg, "privacy")

@bot.message_handler(commands=['help'])
def help_cmd(msg): create_fake_callback(msg, "help")

@bot.message_handler(commands=['about'])
def about_cmd(msg): create_fake_callback(msg, "about")

# Callback
@bot.callback_query_handler(func=lambda c_: True)
def on_callback(c_):
    uid, data = c_.from_user.id, c_.data
    if data == "log":
        bot.send_message(uid, "📝 What's on your mind?")
        bot.register_next_step_handler_by_chat_id(uid, after_log)
    elif data == "voice":
        pending_voice[uid] = True
        bot.send_message(uid, "🎤 Send your voice note.")
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
        bot.send_message(uid, f"🔗 Share:\nhttps://t.me/{bot.get_me().username}?start={uid}")
    elif data == "help":
        bot.send_message(uid, "ℹ️ Log memories, voice notes, earn streaks, grow mindful daily.")
    elif data == "about":
        bot.send_message(uid, "🧘 SoulGarden is your emotional space to grow.")
    elif data == "privacy":
        bot.send_message(uid, f"🔒 Privacy:\n{WEBHOOK_URL}/privacy")
    elif data == "delete":
        kb = InlineKeyboardMarkup().row(
            InlineKeyboardButton("❌ Yes", callback_data="confirm"),
            InlineKeyboardButton("🙅 Cancel", callback_data="cancel"))
        bot.send_message(uid, "⚠️ Confirm delete?", reply_markup=kb)
    elif data == "confirm":
        delete_all(uid)
    elif data == "cancel":
        bot.send_message(uid, "✅ Cancelled. Your Garden is safe.", reply_markup=menu(uid))
    elif data == "admin" and uid == ADMIN_ID:
        bot.send_message(uid, f"🔍 Admin Analytics:\n{WEBHOOK_URL}/admin/analytics?uid={uid}")

def after_log(msg):
    uid = msg.from_user.id
    txt = msg.text.strip()
    c.execute("INSERT INTO memories VALUES (?,?,?,?,?)", (uid, txt, 0, datetime.utcnow().isoformat(), None))
    c.execute("UPDATE users SET points=points+1 WHERE id=?", (uid,))
    conn.commit()
    s = get_stats(uid)
    bot.send_message(uid, f"💾 Saved!\nPoints: {s['points']}\n{motivation()}", reply_markup=menu(uid))

@bot.message_handler(content_types=['voice'])
def handle_voice(msg):
    uid = msg.from_user.id
    if pending_voice.pop(uid, None):
        f = bot.get_file(msg.voice.file_id)
        data = bot.download_file(f.file_path)
        path = f"static/voices/{uid}_{msg.message_id}.ogg"
        os.makedirs("static/voices", exist_ok=True)
        with open(path, "wb") as f_: f_.write(data)
        c.execute("INSERT INTO memories VALUES (?,?,?,?,?)",
                  (uid, "(voice)", 5, datetime.utcnow().isoformat(), path))
        c.execute("UPDATE users SET points=points+1 WHERE id=?", (uid,))
        conn.commit()
        s = get_stats(uid)
        bot.send_message(uid, f"🎤 Saved!\nPoints: {s['points']}", reply_markup=menu(uid))

def show_memories(uid):
    c.execute("SELECT text,mood,timestamp FROM memories WHERE user_id=? ORDER BY timestamp DESC LIMIT 5", (uid,))
    rows = c.fetchall()
    if not rows:
        bot.send_message(uid, "📭 No memories yet.", reply_markup=menu(uid))
        return
    msg = "\n".join([f"{r[2][:10]} — {r[0]}" for r in rows])
    bot.send_message(uid, f"🗂️ Your Memories:\n{msg}", reply_markup=menu(uid))

def send_leaderboard(uid):
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    bot.send_message(uid, "🏆 Leaderboard:\n" + "\n".join([f"{i+1}. @{u or 'anon'} – {p} pts" for i, (u,p) in enumerate(rows)]),
                     reply_markup=InlineKeyboardMarkup().row(
                         InlineKeyboardButton("🌐 View Site", url=f"{WEBHOOK_URL}/leaderboard")))

def send_explore(uid):
    c.execute("SELECT DISTINCT user_id FROM memories WHERE user_id != ? ORDER BY RANDOM() LIMIT 5", (uid,))
    others = c.fetchall()
    if not others:
        bot.send_message(uid, "🌱 No new gardens to explore yet. Come back later!", reply_markup=menu(uid))
        return
    for (other_uid,) in others:
        c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id=? ORDER BY timestamp DESC LIMIT 1", (other_uid,))
        row = c.fetchone()
        if row:
            t, m, ts = row
            bot.send_message(uid, f"🌿 {ts[:10]} • {m}\n{t}",
                reply_markup=InlineKeyboardMarkup().row(
                    InlineKeyboardButton("🌸 Visit Garden", url=f"{WEBHOOK_URL}/visit_garden/{other_uid}")
                )
            )

def delete_all(uid):
    c.execute("SELECT voice_path FROM memories WHERE user_id=?", (uid,))
    for (p,) in c.fetchall():
        if p and os.path.exists(p): os.remove(p)
    c.execute("DELETE FROM memories WHERE user_id=?", (uid,))
    c.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    bot.send_message(uid, "🗑️ Deleted. Send /start to restart.")

# Web routes
@app.route("/dashboard/<int:uid>")
def dashboard(uid):
    c.execute("SELECT username, points, streak FROM users WHERE id=?", (uid,))
    u = c.fetchone()
    if not u: return "User not found", 404
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (uid,))
    ref = c.fetchone()[0]
    c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id=?", (uid,))
    mems = [{"text": t, "mood": m, "timestamp": ts, "voice": vp} for t, m, ts, vp in c.fetchall()]
    return render_template("dashboard.html", name=u[0], points=u[1], streak=u[2], referrals=ref, memories=mems)

@app.route("/leaderboard")
def leaderboard():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    return render_template("leaderboard.html", users=c.fetchall())

@app.route("/visit_garden/<int:uid>")
def visit(uid):
    c.execute("SELECT username FROM users WHERE id=?", (uid,))
    u = c.fetchone()
    if not u: return "User not found", 404
    c.execute("SELECT text,mood,timestamp,voice_path FROM memories WHERE user_id=? ORDER BY timestamp DESC LIMIT 10", (uid,))
    mems = [{"text": t, "mood": m, "timestamp": ts, "voice": vp} for t, m, ts, vp in c.fetchall()]
    return render_template("visit_garden.html", name=u[0], memories=mems)

@app.route("/privacy")
def privacy(): return render_template("privacy.html")

@app.route("/admin/analytics")
def analytics():
    if int(request.args.get("uid", 0)) != ADMIN_ID: return "403", 403
    c.execute("SELECT COUNT(*) FROM users"); total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE DATE(joined_at)=DATE('now')"); new_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memories"); total_mem = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memories WHERE DATE(timestamp)=DATE('now')"); new_mem = c.fetchone()[0]
    return render_template("admin_analytics.html", total_users=total_users, new_today=new_today, total_memories=total_mem, new_memories=new_mem)

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.data.decode("utf-8"))])
    return "OK"

@app.route("/")
def home(): return "🌿 SoulGarden Running"

def daily():
    for (uid,) in c.execute("SELECT id FROM users"):
        try:
            bot.send_message(uid, random.choice([
                "🧘 Reflect today?", "🌿 Feeling okay?", "💬 Time to log thoughts?",
                "✨ Grow with reflection.", "🍃 Journaling = self-care."
            ]))
        except: continue

scheduler.add_job(daily, 'cron', hour=8)

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=8080)
