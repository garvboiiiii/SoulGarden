import os, random, telebot
import psycopg2
import urllib.parse as up
from datetime import datetime, timezone, timedelta
from flask import Flask, request, render_template, abort
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler

# --- Environment ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1335511330"))
up.uses_netloc.append("postgres")
DATABASE_URL = os.getenv("DATABASE_URL")

# --- DB & App ---
conn = psycopg2.connect(DATABASE_URL)
c = conn.cursor()
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, template_folder="templates", static_folder="static")
scheduler = BackgroundScheduler()
scheduler.start()

# --- Create Tables ---
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

pending_voice = {}
# --- Helpers ---
def menu(uid):
    kb = InlineKeyboardMarkup(row_width=2)
    items = [
        ("📝 Log", "log"), ("🎤 Voice", "voice"), ("📜 Memories", "memories"),
        ("🏆 Leaderboard", "leaderboard"), ("🌍 Explore", "explore"), ("📊 Dashboard", "dashboard"),
        ("🌟 Streak", "streak"), ("🔗 Referral", "referral"), ("📖 Help", "help"),
        ("🔒 Privacy", "privacy"), ("🧘 About", "about"), ("🗑️ Delete", "delete")
    ]
    if uid == ADMIN_ID: items.append(("📊 Admin", "admin"))
    kb.add(*[InlineKeyboardButton(t, callback_data=d) for t, d in items])
    return kb

def motivation():
    return random.choice([
        "🌞 You're doing great!", "🌻 Keep expressing yourself.", "💫 Growth is beautiful.",
        "🍃 Reflect. Express. Heal.", "🌼 Journaling is self-care.", "🌿 You are heard."
    ])

def get_stats(uid):
    c.execute("SELECT streak, points FROM users WHERE id=%s", (uid,))
    r = c.fetchone() or (0, 0)
    return {"streak": r[0], "points": r[1]}

def valid_streak(uid):
    c.execute("SELECT last_streak FROM users WHERE id=%s", (uid,))
    row = c.fetchone()
    return not row or not row[0] or datetime.now(timezone.utc) - row[0] >= timedelta(hours=24)

# --- Bot Handlers ---
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.from_user.id
    name = msg.from_user.username or f"user{uid}"
    ref = None
    if len(msg.text.split()) > 1:
        try: ref = int(msg.text.split()[1])
        except: pass
    if uid != ref:
        c.execute("""
            INSERT INTO users (id, username, referred_by, joined_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (uid, name, ref, datetime.now(timezone.utc)))
        if ref:
            c.execute("UPDATE users SET points = points + 5 WHERE id=%s", (ref,))
            bot.send_message(ref, f"🎁 +5 points for inviting @{name}")
        conn.commit()
    bot.send_message(uid, "🌱 Welcome to SoulGarden!", reply_markup=menu(uid))

@bot.message_handler(commands=['log'])
def log_cmd(msg):
    bot.send_message(msg.chat.id, "📝 What's on your mind?")
    bot.register_next_step_handler(msg, after_log)

def after_log(msg):
    uid = msg.from_user.id
    text = msg.text.strip()
    c.execute("INSERT INTO memories VALUES (%s, %s, %s, %s, %s)",
              (uid, text, 0, datetime.now(timezone.utc), None))
    c.execute("UPDATE users SET points = points + 1 WHERE id = %s", (uid,))
    conn.commit()
    stats = get_stats(uid)
    bot.send_message(uid, f"💾 Saved!\nPoints: {stats['points']}\n{motivation()}", reply_markup=menu(uid))

@bot.message_handler(commands=['voice'])
def voice_cmd(msg):
    pending_voice[msg.chat.id] = True
    bot.send_message(msg.chat.id, "🎤 Send your voice note.")

@bot.message_handler(content_types=['voice'])
def voice_handler(msg):
    uid = msg.chat.id
    if pending_voice.pop(uid, False):
        f = bot.get_file(msg.voice.file_id)
        file_data = bot.download_file(f.file_path)
        os.makedirs("static/voices", exist_ok=True)
        path = f"static/voices/{uid}_{msg.message_id}.ogg"
        with open(path, "wb") as out: out.write(file_data)
        c.execute("INSERT INTO memories VALUES (%s, %s, %s, %s, %s)",
                  (uid, "(voice)", 5, datetime.now(timezone.utc), path))
        c.execute("UPDATE users SET points = points + 1 WHERE id = %s", (uid,))
        conn.commit()
        stats = get_stats(uid)
        bot.send_message(uid, f"🎤 Voice saved!\nPoints: {stats['points']}", reply_markup=menu(uid))
# --- Callback Queries ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    uid, data = call.from_user.id, call.data

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
    elif data == "referral":
        bot.send_message(uid, f"🔗 Invite:\nhttps://t.me/{bot.get_me().username}?start={uid}")
    elif data == "help":
        bot.send_message(uid, "ℹ️ Log memories, send voice, earn streaks & grow.")
    elif data == "about":
        bot.send_message(uid, "🧘 SoulGarden is your peaceful journaling garden.")
    elif data == "privacy":
        bot.send_message(uid, f"🔒 Privacy:\n{WEBHOOK_URL}/privacy")
    elif data == "streak":
        if valid_streak(uid):
            c.execute("UPDATE users SET streak=streak+1, last_streak=%s, points=points+1 WHERE id=%s",
                      (datetime.now(timezone.utc), uid))
            conn.commit()
            s = get_stats(uid)
            bot.send_message(uid, f"✅ +1 Streak! Total: {s['streak']}", reply_markup=menu(uid))
        else:
            bot.send_message(uid, "⏳ Come back after 24hrs.", reply_markup=menu(uid))
    elif data == "delete":
        kb = InlineKeyboardMarkup().row(
            InlineKeyboardButton("❌ Yes", callback_data="confirm"),
            InlineKeyboardButton("🙅 Cancel", callback_data="cancel"))
        bot.send_message(uid, "⚠️ Confirm delete?", reply_markup=kb)
    elif data == "confirm":
        delete_all(uid)
    elif data == "cancel":
        bot.send_message(uid, "✅ Cancelled. You're safe.", reply_markup=menu(uid))
    elif data == "admin" and uid == ADMIN_ID:
        bot.send_message(uid, f"🔍 Admin Panel:\n{WEBHOOK_URL}/admin/analytics?uid={uid}")

# --- Utility Functions ---
def show_memories(uid):
    c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id=%s ORDER BY timestamp DESC LIMIT 5", (uid,))
    rows = c.fetchall()
    if not rows:
        bot.send_message(uid, "📭 No memories yet.", reply_markup=menu(uid))
    else:
        msg = "\n".join([f"{r[2].strftime('%Y-%m-%d')} — {r[0]}" for r in rows])
        bot.send_message(uid, f"🗂️ Your Memories:\n{msg}", reply_markup=menu(uid))

def send_leaderboard(uid):
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    msg = "\n".join([f"{i+1}. @{u or 'anon'} – {p} pts" for i, (u, p) in enumerate(rows)])
    bot.send_message(uid, f"🏆 Leaderboard:\n{msg}", reply_markup=InlineKeyboardMarkup().row(
        InlineKeyboardButton("🌐 View Site", url=f"{WEBHOOK_URL}/leaderboard")
    ))

def send_explore(uid):
    c.execute("SELECT DISTINCT user_id FROM memories WHERE user_id != %s ORDER BY RANDOM() LIMIT 5", (uid,))
    others = c.fetchall()
    if not others:
        bot.send_message(uid, "🌱 No new gardens to explore yet. Try later.", reply_markup=menu(uid))
        return
    for (other_uid,) in others:
        c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id=%s ORDER BY timestamp DESC LIMIT 1", (other_uid,))
        row = c.fetchone()
        if row:
            t, m, ts = row
            bot.send_message(uid, f"🌿 {ts.strftime('%Y-%m-%d')} • Mood: {m}\n{t}",
                reply_markup=InlineKeyboardMarkup().row(
                    InlineKeyboardButton("🌸 Visit Garden", url=f"{WEBHOOK_URL}/visit_garden/{other_uid}")
                ))

def delete_all(uid):
    c.execute("SELECT voice_path FROM memories WHERE user_id=%s", (uid,))
    for (p,) in c.fetchall():
        if p and os.path.exists(p): os.remove(p)
    c.execute("DELETE FROM memories WHERE user_id=%s", (uid,))
    c.execute("DELETE FROM users WHERE id=%s", (uid,))
    conn.commit()
    bot.send_message(uid, "🗑️ Your data is deleted. Send /start to begin again.")

# --- Flask Routes ---
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        if "update_id" not in data:
            return "Ignored", 200
        update = telebot.types.Update.de_json(request.data.decode("utf-8"))
        bot.process_new_updates([update])
        return "OK"
    except Exception as e:
        print("Webhook error:", e)
        return abort(500)

@app.route("/")
def home(): return "🌿 SoulGarden Running"

@app.route("/dashboard/<int:uid>")
def dashboard(uid):
    try:
        c.execute("SELECT username, points, streak FROM users WHERE id=%s", (uid,))
        u = c.fetchone()
        if not u: return "User not found", 404
        c.execute("SELECT COUNT(*) FROM users WHERE referred_by=%s", (uid,))
        ref = c.fetchone()[0]
        c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id=%s", (uid,))
        mems = [{"text": t, "mood": m, "timestamp": ts, "voice": vp} for t, m, ts, vp in c.fetchall()]
        return render_template("dashboard.html", name=u[0], points=u[1], streak=u[2], referrals=ref, memories=mems)
    except Exception as e:
        return f"Error: {e}", 500

@app.route("/leaderboard")
def leaderboard():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    return render_template("leaderboard.html", users=c.fetchall())

@app.route("/visit_garden/<int:uid>")
def visit(uid):
    c.execute("SELECT username FROM users WHERE id=%s", (uid,))
    u = c.fetchone()
    if not u: return "User not found", 404
    c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id=%s ORDER BY timestamp DESC LIMIT 10", (uid,))
    mems = [{"text": t, "mood": m, "timestamp": ts, "voice": vp} for t, m, ts, vp in c.fetchall()]
    return render_template("visit_garden.html", name=u[0], memories=mems)

@app.route("/privacy")
def privacy(): return render_template("privacy.html")

@app.route("/admin/analytics")
def analytics():
    try:
        uid = int(request.args.get("uid", 0))
        if uid != ADMIN_ID: return "403", 403
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE DATE(joined_at)=CURRENT_DATE")
        new_today = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM memories")
        total_mem = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM memories WHERE DATE(timestamp)=CURRENT_DATE")
        new_mem = c.fetchone()[0]
        return render_template("admin_analytics.html", total_users=total_users, new_today=new_today,
                               total_memories=total_mem, new_memories=new_mem)
    except Exception as e:
        return f"Error: {e}", 500

# --- Daily Prompt ---
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

# --- Start ---
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=8080)
