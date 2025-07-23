# main.py

import os, random, telebot
import psycopg2
from datetime import datetime, timezone, timedelta
from flask import Flask, request, render_template, abort
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler

# --- Setup Environment ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1335511330"))
DATABASE_URL = os.getenv("DATABASE_URL")

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
c = conn.cursor()

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, template_folder="templates", static_folder="static")
scheduler = BackgroundScheduler()
scheduler.start()

# --- Tables ---
c.execute("""CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username TEXT,
    referred_by BIGINT,
    streak INT DEFAULT 0,
    last_streak TIMESTAMP,
    points INT DEFAULT 0,
    joined_at TIMESTAMP
)""")
c.execute("""CREATE TABLE IF NOT EXISTS memories (
    user_id BIGINT,
    text TEXT,
    mood INT,
    timestamp TIMESTAMP,
    voice_path TEXT
)""")

pending_voice = {}

# --- UI ---
def menu(uid):
    kb = InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("📝 Log", "log"), ("🎤 Voice", "voice"), ("📜 Memories", "memories"),
        ("🏆 Leaderboard", "leaderboard"), ("🌍 Explore", "explore"),
        ("📊 Dashboard", "dashboard"), ("🌟 Streak", "streak"),
        ("🔗 Referral", "referral"), ("📖 Help", "help"),
        ("🔒 Privacy", "privacy"), ("🧘 About", "about"),
        ("🗑️ Delete", "delete")
    ]
    if uid == ADMIN_ID:
        buttons.append(("📊 Admin", "admin"))
    kb.add(*[InlineKeyboardButton(t, callback_data=d) for t, d in buttons])
    return kb

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
    return datetime.now(timezone.utc) - row[0] >= timedelta(hours=24)

def motivation():
    return random.choice([
        "🌞 You're doing great!", "🌻 Keep expressing yourself.",
        "🌊 Let your thoughts flow.", "💫 Another day of growth.",
        "🌿 Reflection brings clarity.", "🌸 Peace begins with you.",
        "🍀 You're never alone here.", "✨ Great job journaling!"
    ])

# --- Command Handlers ---
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.from_user.id
    name = msg.from_user.username or f"user{uid}"
    ref = None
    if len(msg.text.split()) > 1:
        try: ref = int(msg.text.split()[1])
        except: pass
    if uid != ref:
        c.execute("""INSERT INTO users (id, username, referred_by, joined_at)
                     VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                  (uid, name, ref, datetime.now(timezone.utc)))
        if ref:
            c.execute("UPDATE users SET points = points + 5 WHERE id = %s", (ref,))
            bot.send_message(ref, f"🎁 +5 points for inviting @{name}")
    bot.send_message(uid, "🌱 Welcome to SoulGarden!", reply_markup=menu(uid))

@bot.message_handler(commands=['log'])
def log_cmd(msg):
    uid = msg.from_user.id
    bot.send_message(uid, "📝 What's on your mind?")
    bot.register_next_step_handler(msg, after_log)

@bot.message_handler(commands=['voice'])
def voice_cmd(msg):
    uid = msg.from_user.id
    pending_voice[uid] = True
    bot.send_message(uid, "🎤 Send your voice note.")

@bot.message_handler(commands=['memories'])
def mem_cmd(msg): show_memories(msg.from_user.id)

@bot.message_handler(commands=['leaderboard'])
def lead_cmd(msg): send_leaderboard(msg.from_user.id)

@bot.message_handler(commands=['explore'])
def explore_cmd(msg): send_explore(msg.from_user.id)

@bot.message_handler(commands=['referral'])
def ref_cmd(msg): bot.send_message(msg.from_user.id,
    f"🔗 Invite Link:\nhttps://t.me/{bot.get_me().username}?start={msg.from_user.id}")

@bot.message_handler(commands=['streak'])
def streak_cmd(msg):
    uid = msg.from_user.id
    if valid_streak(uid):
        c.execute("UPDATE users SET streak = streak + 1, last_streak = %s, points = points + 1 WHERE id = %s",
                  (datetime.now(timezone.utc), uid))
        s = get_stats(uid)
        bot.send_message(uid, f"✅ +1 Streak! Total: {s['streak']}", reply_markup=menu(uid))
    else:
        bot.send_message(uid, "⏳ Come back after 24 hours.", reply_markup=menu(uid))

@bot.message_handler(commands=['dashboard'])
def dash_cmd(msg): bot.send_message(msg.from_user.id, f"📊 Dashboard:\n{WEBHOOK_URL}/dashboard/{msg.from_user.id}")

@bot.message_handler(commands=['help'])
def help_cmd(msg): bot.send_message(msg.from_user.id, "ℹ️ Use menu to log emotions, send voice notes, and grow.")

@bot.message_handler(commands=['about'])
def about_cmd(msg): bot.send_message(msg.from_user.id, "🧘 SoulGarden is a peaceful journal space.")

@bot.message_handler(commands=['privacy'])
def privacy_cmd(msg): bot.send_message(msg.from_user.id, f"🔒 Privacy:\n{WEBHOOK_URL}/privacy")

@bot.message_handler(commands=['delete'])
def delete_cmd(msg):
    uid = msg.from_user.id
    kb = InlineKeyboardMarkup().row(
        InlineKeyboardButton("❌ Yes", callback_data="confirm"),
        InlineKeyboardButton("🙅 Cancel", callback_data="cancel"))
    bot.send_message(uid, "⚠️ Confirm delete?", reply_markup=kb)

# --- Callback Handler ---
@bot.callback_query_handler(func=lambda call: True)
def on_callback(call):
    data = call.data
    fake_msg = call.message  # reuse message object for convenience
    handler_map = {
        "log": log_cmd,
        "voice": voice_cmd,
        "memories": mem_cmd,
        "leaderboard": lead_cmd,
        "explore": explore_cmd,
        "referral": ref_cmd,
        "streak": streak_cmd,
        "dashboard": dash_cmd,
        "help": help_cmd,
        "about": about_cmd,
        "privacy": privacy_cmd,
        "delete": delete_cmd,
        "confirm": lambda msg: delete_all(call.from_user.id),
        "cancel": lambda msg: bot.send_message(call.from_user.id, "✅ Cancelled", reply_markup=menu(call.from_user.id)),
        "admin": lambda msg: bot.send_message(call.from_user.id,
            f"📊 Admin:\n{WEBHOOK_URL}/admin/analytics?uid={call.from_user.id}")
    }
    if data in handler_map:
        handler = handler_map[data]
        handler(fake_msg)

# --- Data Logic ---
def after_log(msg):
    uid = msg.from_user.id
    txt = msg.text.strip()
    c.execute("INSERT INTO memories VALUES (%s, %s, %s, %s, %s)",
              (uid, txt, 0, datetime.now(timezone.utc), None))
    c.execute("UPDATE users SET points = points + 1 WHERE id = %s", (uid,))
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
        with open(path, "wb") as fp: fp.write(data)
        c.execute("INSERT INTO memories VALUES (%s, %s, %s, %s, %s)",
                  (uid, "(voice)", 5, datetime.now(timezone.utc), path))
        c.execute("UPDATE users SET points = points + 1 WHERE id = %s", (uid,))
        s = get_stats(uid)
        bot.send_message(uid, f"🎤 Saved!\nPoints: {s['points']}", reply_markup=menu(uid))

def delete_all(uid):
    c.execute("SELECT voice_path FROM memories WHERE user_id = %s", (uid,))
    for (vp,) in c.fetchall():
        if vp and os.path.exists(vp): os.remove(vp)
    c.execute("DELETE FROM memories WHERE user_id = %s", (uid,))
    c.execute("DELETE FROM users WHERE id = %s", (uid,))
    bot.send_message(uid, "🗑️ All data deleted. Send /start to begin again.")

# --- Explore & Display ---
def show_memories(uid):
    c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id=%s ORDER BY timestamp DESC LIMIT 5", (uid,))
    rows = c.fetchall()
    if not rows:
        bot.send_message(uid, "📭 No memories yet.", reply_markup=menu(uid))
        return
    msg = "\n".join([f"{r[2].strftime('%Y-%m-%d')} — {r[0]}" for r in rows])
    bot.send_message(uid, f"🗂️ Your Memories:\n{msg}", reply_markup=menu(uid))

def send_leaderboard(uid):
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    board = "\n".join([f"{i+1}. @{u or 'anon'} – {p} pts" for i, (u, p) in enumerate(rows)])
    kb = InlineKeyboardMarkup().row(
        InlineKeyboardButton("🌐 View Site", url=f"{WEBHOOK_URL}/leaderboard"))
    bot.send_message(uid, f"🏆 Leaderboard:\n{board}", reply_markup=kb)

def send_explore(uid):
    c.execute("SELECT DISTINCT user_id FROM memories WHERE user_id != %s ORDER BY RANDOM() LIMIT 5", (uid,))
    users = c.fetchall()
    for (other_uid,) in users:
        c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id=%s ORDER BY timestamp DESC LIMIT 1", (other_uid,))
        row = c.fetchone()
        if row:
            t, m, ts = row
            kb = InlineKeyboardMarkup().row(
                InlineKeyboardButton("🌸 Visit Garden", url=f"{WEBHOOK_URL}/visit_garden/{other_uid}"))
            bot.send_message(uid, f"🌿 {ts.strftime('%Y-%m-%d')} • Mood: {m}\n{t}", reply_markup=kb)

# --- Web Routes ---
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.data.decode("utf-8"))
        bot.process_new_updates([update])
        return "OK"
    except Exception as e:
        print("Webhook error:", e)
        return abort(500)

@app.route("/")
def home(): return "🌿 SoulGarden Running"

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=8080)
