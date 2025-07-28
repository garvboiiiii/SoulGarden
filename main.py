import os, random, telebot, traceback
from telegram.ext import CommandHandler
import psycopg2
from datetime import datetime, timezone, timedelta
from flask import Flask, request, render_template, abort
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler

# --- Environment ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1335511330"))
DATABASE_URL = os.getenv("DATABASE_URL")

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
c = conn.cursor()

os.makedirs("static/voices", exist_ok=True)

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
pending_mood = {}

MOOD_LABELS = {
    "🙂 Happy": 5,
    "😊 Grateful": 4,
    "😐 Neutral": 3,
    "😢 Sad": 2,
    "😡 Angry": 1,
    "😨 Anxious": 0
}

MOOD_MAP = {
    5: "🙂 Happy",
    4: "😊 Grateful",
    3: "😐 Neutral",
    2: "😢 Sad",
    1: "😡 Angry",
    0: "😨 Anxious",
    None: "❓ Skipped"
}


MOOD_DISPLAY = {v: k for k, v in MOOD_LABELS.items()}


# --- Utilities ---
def menu(uid):
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "📝 Log Memory", "🎤 Voice",
        "📜 Memories", "🏆 Leaderboard",
        "🌍 Explore", "📊 Dashboard",
        "🔥 Streak", "🔗 Referral",
        "ℹ️ Help", "🧘 About",
        "🔒 Privacy", "🗑️ Delete",
        "💬 Feedback"
    ]
    if uid == ADMIN_ID:
        buttons.append("🛠️ Admin")
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


def poll(update, context):
    question = "🌿 What would you love to see next in SoulGarden?"
    options = [
        "Daily Mood Reminder",
        "More Garden Themes",
        "Voice Notes from Others",
        "Gratitude Journal",
        "Leaderboard / Streak Challenges",
        "Something Else (Type via /suggest)"
    ]

    context.bot.send_poll(
        chat_id=update.effective_chat.id,
        question=question,
        options=options,
        is_anonymous=True,
        allows_multiple_answers=False
    )

# Register this command
dispatcher.add_handler(CommandHandler("poll", poll))



def suggest(update, context):
    user_id = update.effective_user.id
    msg = " ".join(context.args)

    if not msg:
        update.message.reply_text("✍️ Type your suggestion like this:\n`/suggest Add a dark mode UI`", parse_mode='Markdown')
        return

    # Send suggestion to admin
    for admin in ADMIN_ID:
        context.bot.send_message(
            chat_id=admin,
            text=f"💡 Suggestion from {user_id}:\n\n{msg}"
        )

    update.message.reply_text("🌸 Thanks! Your idea has been sent. We're always listening.")

# Register this command too
dispatcher.add_handler(CommandHandler("suggest", suggest))

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



command_map = {
    "📝 Log Memory": "/log",
    "🎤 Voice": "/voice",
    "📜 Memories": "/memories",
    "🏆 Leaderboard": "/leaderboard",
    "🌍 Explore": "/explore",
    "📊 Dashboard": "/dashboard",
    "🔥 Streak": "/streak",
    "🔗 Referral": "/referral",
    "ℹ️ Help": "/help",
    "🧘 About": "/about",
    "🔒 Privacy": "/privacy",
    "🗑️ Delete": "/delete",
    "🛠️ Admin": "/admin",
    "💬 Feedback": "/feedback"
}


@bot.message_handler(func=lambda m: m.text in command_map)
def handle_button_commands(msg):
    actual_command = command_map[msg.text]
    if actual_command == "/log":
        log_cmd(msg)
    elif actual_command == "/voice":
        voice_cmd(msg)
    elif actual_command == "/memories":
        mem_cmd(msg)
    elif actual_command == "/leaderboard":
        lead_cmd(msg)
    elif actual_command == "/explore":
        explore_cmd(msg)
    elif actual_command == "/dashboard":
        dash_cmd(msg)
    elif actual_command == "/streak":
        streak_cmd(msg)
    elif actual_command == "/referral":
        ref_cmd(msg)
    elif actual_command == "/help":
        help_cmd(msg)
    elif actual_command == "/about":
        about_cmd(msg)
    elif actual_command == "/privacy":
        privacy_cmd(msg)
    elif actual_command == "/delete":
        delete_cmd(msg)
    elif actual_command == "/admin" and msg.from_user.id == ADMIN_ID:
        admin_cmd(msg)
    elif actual_command == "/feedback":
        feedback_cmd(msg)


@bot.message_handler(commands=['admin'])
def admin_cmd(msg):
    if msg.from_user.id != ADMIN_ID:
        bot.send_message(msg.chat.id, "🚫 This section is restricted.")
        return
    bot.send_message(msg.chat.id, f"📊 Admin Panel:\n{WEBHOOK_URL}/admin/analytics?uid={msg.from_user.id}")


@bot.message_handler(commands=['feedback'])
def feedback_cmd(msg):
    kb = telebot.types.InlineKeyboardMarkup()
    twitter_button = telebot.types.InlineKeyboardButton("🐦 Give Feedback on Twitter", url="https://twitter.com/s0ulGarden_Bot")
    kb.add(twitter_button)
    bot.send_message(msg.chat.id, "We’d love to hear your thoughts! 💬", reply_markup=kb)

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
def explore_cmd(msg):
    uid = msg.from_user.id
    url = f"https://soulgarden.up.railway.app/explore?uid={uid}"
    bot.send_message(uid, f"🌍 Explore soul gardens here:\n🔗 {url}")

@bot.message_handler(commands=['dashboard'])
def dash_cmd(msg): bot.send_message(msg.chat.id, f"📊 Dashboard:\n{WEBHOOK_URL}/dashboard/{msg.from_user.id}")

@bot.message_handler(commands=['referral'])
def ref_cmd(msg):
    uid = msg.from_user.id
    bot.send_message(uid, f"🔗 Invite:\nhttps://t.me/{bot.get_me().username}?start={uid}")

@bot.message_handler(commands=['streak'])
def streak_cmd(msg):
    uid = msg.from_user.id

    try:
        # Get last streak date
        c.execute("SELECT streak, last_streak, points FROM users WHERE id=%s", (uid,))
        row = c.fetchone()

        if not row:
            bot.send_message(uid, "⚠️ You're not registered yet. Please send /start.", reply_markup=menu(uid))
            return

        streak, last_streak, points = row
        now = datetime.now(timezone.utc).date()

        if last_streak:
            last = last_streak.date()
            days_diff = (now - last).days

            if days_diff == 0:
                # Already claimed today
                bot.send_message(uid, "📆 You've already claimed today's streak!\nCome back tomorrow 🌞", reply_markup=menu(uid))
                return
            elif days_diff > 1:
                # Missed streak
                streak = 0
                c.execute("UPDATE users SET streak = 0 WHERE id = %s", (uid,))
                conn.commit()

        # Eligible for new streak
        new_streak = streak + 1
        new_points = points + 1
        c.execute("""
            UPDATE users
            SET streak = %s, last_streak = %s, points = %s
            WHERE id = %s
        """, (new_streak, datetime.now(timezone.utc), new_points, uid))
        conn.commit()

        bot.send_message(uid, f"✅ +1 Streak!\n🔥 Streak: {new_streak} days\n🏆 Points: {new_points}\n{motivation()}", reply_markup=menu(uid))

    except Exception as e:
        print("[Streak Error]", e)
        bot.send_message(uid, "⚠️ Something went wrong while updating your streak. Please try again later.")



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
    pending_mood[uid] = txt

    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    mood_buttons = list(MOOD_LABELS.keys()) + ["⏭️ Skip"]
    kb.add(*[KeyboardButton(b) for b in mood_buttons])
    bot.send_message(uid, "🧠 How are you feeling?", reply_markup=kb)


@bot.message_handler(content_types=['voice'])
def handle_voice(msg):
    uid = msg.from_user.id
    if pending_voice.pop(uid, None):
        f = bot.get_file(msg.voice.file_id)
        data = bot.download_file(f.file_path)
        path = f"static/voices/{uid}_{msg.message_id}.ogg"
        with open(path, "wb") as fp:
            fp.write(data)
        pending_mood[uid] = "(voice)"
        pending_voice[uid] = path  # reuse for path
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        mood_buttons = list(MOOD_LABELS.keys()) + ["⏭️ Skip"]
        kb.add(*[KeyboardButton(b) for b in mood_buttons])
        bot.send_message(uid, "🧠 How did this voice memory feel?", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in MOOD_LABELS or m.text == "⏭️ Skip")
def handle_mood_choice(msg):
    uid = msg.from_user.id
    text = pending_mood.pop(uid, None)
    voice_path = pending_voice.pop(uid, None) if isinstance(pending_voice.get(uid), str) else None

    if not text:
        bot.send_message(uid, "⚠️ Something went wrong. Please try again.", reply_markup=menu(uid))
        return

    mood = MOOD_LABELS.get(msg.text) if msg.text != "⏭️ Skip" else None

    c.execute("INSERT INTO memories VALUES (%s, %s, %s, %s, %s)",
              (uid, text, mood, datetime.now(timezone.utc), voice_path))
    c.execute("UPDATE users SET points = points + 1 WHERE id = %s", (uid,))
    s = get_stats(uid)
    bot.send_message(uid, f"💾 Saved!\nPoints: {s['points']}\n{motivation()}", reply_markup=menu(uid))
    


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
        c.execute("""
            SELECT DISTINCT ON (user_id) user_id 
            FROM memories 
            WHERE user_id != %s 
            ORDER BY user_id, RANDOM()
        """, (uid,))
        users = c.fetchall()

        if not users:
            bot.send_message(uid, "🌱 No other gardens to explore yet.")
            return

        for (other_uid,) in users:
            c.execute("""
                SELECT text, mood, timestamp 
                FROM memories 
                WHERE user_id = %s 
                ORDER BY timestamp DESC LIMIT 1
            """, (other_uid,))
            row = c.fetchone()
            if row:
                text, mood, ts = row
                text = text or "(No memory text)"
                mood = mood if mood is not None else "Skipped"
                preview = f"🌿 {ts.strftime('%Y-%m-%d')} • Mood: {mood}\n{text}"
                bot.send_message(uid, preview)
    except Exception as e:
        import traceback
        traceback.print_exc()
        bot.send_message(uid, "⚠️ Something went wrong while exploring gardens.")



# --- Flask Web Routes ---
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
                           referrals=refs, memories=mems, mood_display=MOOD_DISPLAY)

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/leaderboard")
def leaderboard_page():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    users = c.fetchall()
    return render_template("leaderboard.html", users=users)

@app.route("/explore")
def explore():
    try:
        uid = request.args.get("uid")
        if not uid:
            return "Missing user ID", 400

        # Get all distinct other user IDs who have memories
        c.execute("""
            SELECT DISTINCT user_id 
            FROM memories 
            WHERE user_id != %s
        """, (uid,))
        all_others = [row[0] for row in c.fetchall()]

        if not all_others:
            return render_template("explore.html", gardens=[], my_uid=uid)

        # Randomly select 5
        random.shuffle(all_others)
        selected_uids = all_others[:5]

        gardens = []
        for other_uid in selected_uids:
            c.execute("""
                SELECT text, mood, timestamp 
                FROM memories 
                WHERE user_id = %s 
                AND (text IS NOT NULL OR voice_path IS NOT NULL)
                ORDER BY timestamp DESC 
                LIMIT 1
            """, (other_uid,))
            row = c.fetchone()
            if row:
                text = row[0] or "(No text)"
                mood = row[1]
                timestamp = row[2]
                mood_display = MOOD_MAP.get(mood, "❓ Skipped")
                gardens.append({
                    "uid": other_uid,
                    "text": text,
                    "mood": mood_display,
                    "timestamp": timestamp
                })

        return render_template("explore.html", gardens=gardens, my_uid=uid)

    except Exception as e:
        print("[Explore Error]", str(e))
        return "Something went wrong while exploring. Please try again.", 500

    

@app.route("/visit_garden/<int:uid>")
def visit_garden(uid):
    try:
        c.execute("""
            SELECT text, mood, timestamp, voice_path 
            FROM memories 
            WHERE user_id=%s 
            AND (text IS NOT NULL OR voice_path IS NOT NULL)
            ORDER BY timestamp DESC 
            LIMIT 5
        """, (uid,))
        rows = c.fetchall()

        memories = []
        for text, mood, timestamp, voice_path in rows:
            memories.append({
                "text": text or "(No text)",
                "mood": MOOD_DISPLAY.get(mood, "❓ Skipped"),
                "timestamp": timestamp,
                "voice": voice_path  # path to audio
            })

        return render_template("visit_garden.html", memories=memories)

    except Exception as e:
        print("[Visit Garden Error]", e)
        return "Something went wrong while visiting the garden.", 500


@app.route("/admin/analytics")
def analytics():
    uid = request.args.get("uid", type=int)
    if uid != ADMIN_ID:
        return "Unauthorized", 403

    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE joined_at >= now() - interval '1 day'")
    today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memories")
    memories = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM memories WHERE timestamp >= now() - interval '1 day'")
    new_mems = c.fetchone()[0]

    return render_template("admin_analytics.html", total_users=total, new_today=today,
                           total_memories=memories, new_memories=new_mems)


# --- Start Bot ---
if __name__ == "__main__":
    print("🌿 SoulGarden bot starting...")
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=8080)
