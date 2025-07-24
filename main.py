import os, random, telebot
import psycopg2
from datetime import datetime, timezone, timedelta
from flask import Flask, request, render_template, abort
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler

# --- Environment ---
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

# --- Utilities ---
def menu(uid):
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "/log", "/voice", "/memories", "/leaderboard",
        "/explore", "/dashboard", "/streak", "/referral",
        "/help", "/about", "/privacy", "/delete"
    ]
    if uid == ADMIN_ID:
        buttons.append("/admin")
    kb.add(*[telebot.types.KeyboardButton(b) for b in buttons])
    return kb


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

# --- Commands ---
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.from_user.id
    name = msg.from_user.username or f"user{uid}"
    now = datetime.now(timezone.utc)
    ref = None
    new_user = False

    if len(msg.text.split()) > 1:
        try: ref = int(msg.text.split()[1])
        except: pass

    # Check if user already exists
    c.execute("SELECT id FROM users WHERE id = %s", (uid,))
    existing = c.fetchone()

    if not existing:
        new_user = True
        c.execute("""
            INSERT INTO users (id, username, referred_by, joined_at)
            VALUES (%s, %s, %s, %s)
        """, (uid, name, ref if ref != uid else None, now))
        if ref and ref != uid:
            c.execute("UPDATE users SET points = points + 5 WHERE id = %s", (ref,))
            bot.send_message(ref, f"🎁 +5 points for inviting @{name}")
        conn.commit()

    if new_user:
        welcome_msg = (
            "🌱 Welcome to SoulGarden!\n\n"
            "This is your peaceful space to grow, reflect, and bloom.\n\n"
            "✨ Get started with:\n"
            "📝 /log – Write your thoughts\n"
            "🎤 /voice – Send a voice memory\n"
            "📜 /memories – View your past logs\n"
            "🌍 /explore – Visit other gardens\n"
            "📊 /dashboard – See your stats\n"
            "🌟 /streak – Keep your daily streak alive\n"
            "🔗 /referral – Invite friends and earn 🌸\n"
            "🗑️ /delete – Want to start over? Use this\n\n"
            "💬 Type a command anytime to interact."
        )
    else:
        welcome_msg = (
            "🌿 Welcome back to SoulGarden!\n\n"
            "Keep growing your journal 🌸\n"
            "Use /log or /voice to share your thoughts,\n"
            "or explore your /memories and /dashboard.\n\n"
            "Need a restart? /delete\n"
            "Want to invite friends? /referral"
        )

    bot.send_message(uid, welcome_msg, reply_markup=menu(uid))



@bot.message_handler(commands=['admin'])
def admin_cmd(msg):
    uid = msg.from_user.id
    if uid != ADMIN_ID:
        bot.send_message(uid, "🚫 This section is restricted.")
        return
    bot.send_message(uid, f"📊 Admin Panel:\n{WEBHOOK_URL}/admin/analytics?uid={uid}")



@bot.message_handler(commands=['log'])
def log_cmd(msg):
    bot.send_message(msg.chat.id, "📝 What's on your mind?")
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

@bot.message_handler(commands=['dashboard'])
def dash_cmd(msg): bot.send_message(msg.chat.id, f"📊 Dashboard:\n{WEBHOOK_URL}/dashboard/{msg.from_user.id}")

@bot.message_handler(commands=['referral'])
def ref_cmd(msg):
    uid = msg.from_user.id
    bot.send_message(uid, f"🔗 Invite:\nhttps://t.me/{bot.get_me().username}?start={uid}")

@bot.message_handler(commands=['streak'])
def streak_cmd(msg):
    uid = msg.from_user.id
    if valid_streak(uid):
        c.execute("UPDATE users SET streak = streak + 1, last_streak = %s, points = points + 1 WHERE id = %s",
                  (datetime.now(timezone.utc), uid))
        s = get_stats(uid)
        bot.send_message(uid, f"✅ +1 Streak! Total: {s['streak']}")
    else:
        bot.send_message(uid, "⏳ Come back after 24 hours.")

@bot.message_handler(commands=['help'])
def help_cmd(msg): bot.send_message(msg.chat.id, "ℹ️ Use /log /voice /memories /explore etc.")

@bot.message_handler(commands=['about'])
def about_cmd(msg): bot.send_message(msg.chat.id, "🧘 SoulGarden is a peaceful journaling space.")

@bot.message_handler(commands=['privacy'])
def privacy_cmd(msg): bot.send_message(msg.chat.id, f"🔒 Privacy:\n{WEBHOOK_URL}/privacy")

@bot.message_handler(commands=['delete'])
def delete_cmd(msg):
    uid = msg.from_user.id
    bot.send_message(uid, "⚠️ Type 'DELETE' to confirm.")
    bot.register_next_step_handler(msg, confirm_delete)

def confirm_delete(msg):
    uid = msg.from_user.id
    if msg.text.strip().upper() == "DELETE":
        delete_all(uid)
        bot.send_message(uid, "🗑️ All data deleted. Send /start to begin again.")
    else:
        bot.send_message(uid, "❎ Cancelled.")

# --- Logging ---
def after_log(msg):
    uid, txt = msg.from_user.id, msg.text.strip()
    c.execute("INSERT INTO memories VALUES (%s, %s, %s, %s, %s)",
              (uid, txt, 0, datetime.now(timezone.utc), None))
    c.execute("UPDATE users SET points = points + 1 WHERE id = %s", (uid,))
    s = get_stats(uid)
    bot.send_message(uid, f"💾 Saved!\nPoints: {s['points']}\n{motivation()}")

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
        bot.send_message(uid, f"🎤 Saved!\nPoints: {s['points']}")

# --- Data ---
def delete_all(uid):
    c.execute("SELECT voice_path FROM memories WHERE user_id = %s", (uid,))
    for (vp,) in c.fetchall():
        if vp and os.path.exists(vp): os.remove(vp)
    c.execute("DELETE FROM memories WHERE user_id = %s", (uid,))
    c.execute("DELETE FROM users WHERE id = %s", (uid,))

def show_memories(uid):
    c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id=%s ORDER BY timestamp DESC LIMIT 5", (uid,))
    rows = c.fetchall()
    if not rows:
        bot.send_message(uid, "📭 No memories yet.")
        return
    msg = "\n".join([f"{r[2].strftime('%Y-%m-%d')} — {r[0]}" for r in rows])
    bot.send_message(uid, f"🗂️ Your Memories:\n{msg}")

def send_leaderboard(uid):
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    board = "\n".join([f"{i+1}. @{u or 'anon'} – {p} pts" for i, (u, p) in enumerate(rows)])
    bot.send_message(uid, f"🏆 Leaderboard:\n{board}\nOr view at: {WEBHOOK_URL}/leaderboard")

def send_explore(uid):
    try:
        c.execute("SELECT DISTINCT user_id FROM memories WHERE user_id != %s ORDER BY RANDOM() LIMIT 5", (uid,))
        users = c.fetchall()

        if not users:
            bot.send_message(uid, "🌱 No new gardens to explore yet.")
            return

        for (other_uid,) in users:
            c.execute("""
                SELECT text, mood, timestamp FROM memories
                WHERE user_id = %s ORDER BY timestamp DESC LIMIT 1
            """, (other_uid,))
            row = c.fetchone()
            if row:
                text, mood, ts = row
                preview = f"🌿 {ts.strftime('%Y-%m-%d')} • Mood: {mood}\n{text}"
                bot.send_message(uid, preview)
    except Exception as e:
        print(f"Explore error: {e}")
        bot.send_message(uid, "⚠️ Something went wrong exploring gardens.")


# --- Flask Webhooks ---
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
def home(): return "🌿 SoulGarden Bot Running"

@app.route("/dashboard/<int:uid>")
def dashboard(uid):
    c.execute("SELECT username, streak, points FROM users WHERE id=%s", (uid,))
    u = c.fetchone()
    if not u: return "Not found", 404
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by=%s", (uid,))
    refs = c.fetchone()[0]
    c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id=%s ORDER BY timestamp DESC", (uid,))
    mems = [{"text": t, "mood": m, "timestamp": ts, "voice": vp} for t, m, ts, vp in c.fetchall()]
    return render_template("dashboard.html", name=u[0] or "anon", streak=u[1], points=u[2],
                           referrals=refs, memories=mems)

@app.route("/privacy")
def privacy(): return "🔒 We don't share or misuse your data."

@app.route("/leaderboard")
def leaderboard_page():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    users = c.fetchall()
    return render_template("leaderboard.html", users=users)

@app.route("/explore")
def explore_page():
    c.execute("SELECT DISTINCT user_id FROM memories ORDER BY RANDOM() LIMIT 5")
    gardens = []
    for (uid,) in c.fetchall():
        c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id=%s ORDER BY timestamp DESC LIMIT 3", (uid,))
        mems = [{"text": t, "mood": m, "timestamp": ts} for t, m, ts in c.fetchall()]
        gardens.append({"memories": mems})
    return render_template("explore.html", gardens=gardens)

@app.route("/visit_garden/<int:uid>")
def visit_garden(uid):
    c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id=%s ORDER BY timestamp DESC LIMIT 5", (uid,))
    mems = [{"text": t, "mood": m, "timestamp": ts, "voice": vp} for t, m, ts, vp in c.fetchall()]
    return render_template("visit.html", memories=mems)

@app.route("/admin/analytics")
def analytics():
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE joined_at >= now() - interval '1 day'")
    today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memories")
    memories = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memories WHERE timestamp >= now() - interval '1 day'")
    new_mems = c.fetchone()[0]
    return render_template("admin.html", total_users=total, new_today=today,
                           total_memories=memories, new_memories=new_mems)

# --- Start Bot ---
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=8080)
