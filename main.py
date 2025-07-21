import os
import sqlite3
import telebot
from flask import Flask, request, render_template
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from utils import log_memory, get_user_stats, calculate_streak
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, static_folder="static", template_folder="templates")

conn = sqlite3.connect("garden.db", check_same_thread=False)
c = conn.cursor()

# --- DB Setup ---
c.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,
    referred_by INTEGER,
    streak INTEGER DEFAULT 0,
    last_entry TEXT,
    points INTEGER DEFAULT 0,
    joined_at TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS memories (
    user_id INTEGER,
    text TEXT,
    mood TEXT,
    timestamp TEXT,
    voice_path TEXT
)""")
conn.commit()

user_memory_temp = {}

# --- Commands ---
bot.set_my_commands([
    BotCommand("start", "Start your SoulGarden"),
    BotCommand("log", "Log a new memory"),
    BotCommand("voice", "Send a voice memory"),
    BotCommand("memories", "View your past memories"),
    BotCommand("leaderboard", "View top users"),
    BotCommand("explore", "Explore other gardens"),
    BotCommand("about", "About SoulGarden"),
    BotCommand("delete", "Delete all your memories"),
    BotCommand("help", "Help and commands"),
    BotCommand("referral", "Share your referral link")
])

# --- Menu Buttons ---
def menu_buttons(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📝 Log Memory", callback_data="log"),
        InlineKeyboardButton("🎤 Voice Note", callback_data="voice"),
        InlineKeyboardButton("📜 My Memories", callback_data="memories"),
        InlineKeyboardButton("🏆 Leaderboard", url=f"{WEBHOOK_URL}/leaderboard"),
        InlineKeyboardButton("🌍 Explore", callback_data="explore"),
        InlineKeyboardButton("📊 Dashboard", url=f"{WEBHOOK_URL}/dashboard/{user_id}"),
        InlineKeyboardButton("🔐 Privacy", url=f"{WEBHOOK_URL}/privacy"),
        InlineKeyboardButton("ℹ️ About", callback_data="about")
    )
    return markup

# --- Start Command with Referral ---
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user{user_id}"
    referred_by = None

    if len(message.text.split()) > 1:
        ref = message.text.split()[1]
        try:
            referred_by = int(ref) if int(ref) != user_id else None
        except:
            pass

    # Check if user is new
    c.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    existing = c.fetchone()

    if not existing:
        now = datetime.utcnow().isoformat()
        c.execute("INSERT INTO users (id, username, referred_by, joined_at) VALUES (?, ?, ?, ?)",
                  (user_id, username, referred_by, now))

        # Referral reward
        if referred_by:
            c.execute("UPDATE users SET points = points + 4 WHERE id = ?", (referred_by,))
            bot.send_message(referred_by, f"🎁 You earned 4 points for inviting @{username}!")

        conn.commit()

        bot.send_message(user_id,
            f"🌱 <b>Welcome to SoulGarden</b>, @{username}!\n"
            "Your mental health sanctuary.\n\n"
            "✅ Log daily thoughts\n🎤 Share voice notes\n🌍 Explore anonymous gardens\n🏆 Earn points & streaks\n"
            f"\nStart by logging a memory or use the buttons below.",
            parse_mode="HTML",
            reply_markup=menu_buttons(user_id)
        )
    else:
        bot.send_message(user_id, "🌸 Welcome back to SoulGarden!", reply_markup=menu_buttons(user_id))

# --- Referral Link ---
@bot.message_handler(commands=['referral'])
def referral_cmd(message):
    uid = message.from_user.id
    bot.send_message(uid, f"🔗 Your invite link:\nhttps://t.me/s0ulGarden_Bot?start={uid}")

# --- Help ---
@bot.message_handler(commands=['help'])
def help_cmd(message):
    bot.send_message(message.chat.id, "💡 Use /log to write, /voice to record, or /explore to discover other gardens.")

# --- Log Memory ---
@bot.message_handler(commands=['log'])
def log_cmd(message):
    bot.send_message(message.chat.id, "📝 What's on your mind today?")
    bot.register_next_step_handler(message, handle_memory)

def handle_memory(message):
    user_id = message.from_user.id
    text = message.text.strip()
    if not text:
        bot.send_message(user_id, "❗Please type something.")
        return

    user_memory_temp[user_id] = text
    markup = InlineKeyboardMarkup()
    for mood in ["😊 Happy", "😔 Sad", "🤯 Stressed", "💡 Inspired", "😴 Tired"]:
        markup.add(InlineKeyboardButton(mood, callback_data=f"mood|{mood}"))
    bot.send_message(user_id, "💬 Pick a mood for this entry:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mood|"))
def handle_mood(call):
    user_id = call.from_user.id
    mood = call.data.split("|", 1)[1]
    text = user_memory_temp.pop(user_id, None)

    if not text:
        bot.send_message(user_id, "⏳ Timeout! Try /log again.")
        return

    log_memory(user_id, text, mood)
    stats = get_user_stats(user_id)
   
    # 🌱 Feedback + Image
    bot.send_message(
        user_id,
        f"🌱 Memory saved!\n\n"
        f"📆 <b>Streak:</b> {stats['streak']} days\n"
        f"🌟 <b>Points:</b> {stats['points']}\n\n"
        "🪴 Your first sprout has grown!\n"
        "Return daily to grow your SoulGarden 🌸",
        parse_mode="HTML"
    )

    bot.send_photo(user_id, photo=open("static/sprout.jpg", "rb"))

    # Show buttons
    bot.send_message(
        user_id,
        "✨ What would you like to do next?",
        reply_markup=menu_buttons(user_id)
    ) 

# --- Voice Note ---
@bot.message_handler(commands=['voice'])
def voice_cmd(message):
    bot.send_message(message.chat.id, "🎤 Send your voice note now.")

@bot.message_handler(content_types=["voice"])
def handle_voice(message):
    user_id = message.from_user.id
    file_info = bot.get_file(message.voice.file_id)
    downloaded = bot.download_file(file_info.file_path)

    os.makedirs("static/voices", exist_ok=True)
    path = f"static/voices/{user_id}_{file_info.file_unique_id}.ogg"
    with open(path, "wb") as f:
        f.write(downloaded)

    log_memory(user_id, "(voice note)", "🎧", voice_path=path)
    stats = get_user_stats(user_id)
    bot.send_message(user_id, f"🎧 Voice saved!\n📆 {stats['streak']} days • 🌟 {stats['points']} pts")

# --- Memories ---
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

# --- Explore ---
@bot.message_handler(commands=["explore"])
def explore_cmd(message):
    uid = message.chat.id
    c.execute("SELECT DISTINCT user_id FROM memories ORDER BY RANDOM() LIMIT 5")
    ids = [row[0] for row in c.fetchall()]
    for u in ids:
        c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1", (u,))
        mem = c.fetchone()
        if not mem:
            continue
        txt = f"🌿 <b>{mem[2][:10]}</b> — {mem[1]}\n{mem[0]}"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔍 Visit Garden", url=f"{WEBHOOK_URL}/explore/garden/{u}"))
        bot.send_message(uid, txt, parse_mode="HTML", reply_markup=markup)

# --- Delete ---
@bot.message_handler(commands=["delete"])
def delete_cmd(message):
    uid = message.from_user.id
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("❌ Yes, delete", callback_data="confirm_delete"),
        InlineKeyboardButton("🙅 Cancel", callback_data="cancel_delete")
    )
    bot.send_message(uid, "⚠️ Are you sure you want to delete all your data?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    if call.data == "log":
        log_cmd(call.message)
    elif call.data == "voice":
        voice_cmd(call.message)
    elif call.data == "memories":
        memories_cmd(call.message)
    elif call.data == "explore":
        explore_cmd(call.message)
    elif call.data == "about":
        about_cmd(call.message)
    elif call.data == "cancel_delete":
        bot.send_message(call.from_user.id, "🔒 Your garden is safe.")
    elif call.data == "confirm_delete":
        uid = call.from_user.id
        c.execute("SELECT voice_path FROM memories WHERE user_id = ?", (uid,))
        for path in [r[0] for r in c.fetchall() if r[0]]:
            try:
                os.remove(path)
            except:
                pass
        c.execute("DELETE FROM memories WHERE user_id = ?", (uid,))
        c.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.commit()
        bot.send_message(uid, "🗑️ All data deleted. Start again anytime with /start.")

# --- Other ---
@bot.message_handler(commands=['about'])
def about_cmd(message):
    bot.send_message(message.chat.id, "🌸 SoulGarden helps you track thoughts and emotions. Safe, private, and gentle growth.")

@bot.message_handler(commands=["leaderboard"])
def leaderboard_cmd(message):
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    msg = "🏆 <b>Top Gardeners</b>\n\n" + "\n".join([f"{i+1}. @{r[0]} — {r[1]} pts" for i, r in enumerate(rows)])
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🌐 View Online", url=f"{WEBHOOK_URL}/leaderboard"))
    bot.send_message(message.chat.id, msg, parse_mode="HTML", reply_markup=markup)

# --- Web App Routes ---
@app.route("/dashboard/<int:user_id>")
def dashboard(user_id):
    c.execute("SELECT username, points FROM users WHERE id = ?", (user_id,))
    u = c.fetchone()
    if not u: return "User not found", 404
    c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
    mems = [{"text": r[0], "mood": r[1], "timestamp": r[2], "voice": r[3]} for r in c.fetchall()]
# Count referrals
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,))
    ref_count = c.fetchone()[0]

    return render_template("dashboard.html", 
        name=u[0],
        points=u[1],
        streak=calculate_streak(user_id),
        memories=mems,
        referrals=ref_count
    )





# --- Admin Analytics ---
@app.route("/admin/analytics")
def admin_analytics():
    admin_id = 1335511330  # Replace with YOUR Telegram ID

    uid = request.args.get("uid")
    if not uid or int(uid) != admin_id:
        return "Unauthorized", 403

    today = datetime.utcnow().date().isoformat()

    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{today}%",))
    new_today = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM memories")
    total_memories = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM memories WHERE timestamp LIKE ?", (f"{today}%",))
    new_memories = c.fetchone()[0]

    return render_template("admin_analytics.html", **{
        "total_users": total_users,
        "new_today": new_today,
        "total_memories": total_memories,
        "new_memories": new_memories
    })
    
@app.route("/leaderboard")
def leaderboard():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    return render_template("leaderboard.html", users=c.fetchall())

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/explore/garden/<int:user_id>")
def visit_garden(user_id):
    c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
    mems = [{"text": r[0], "mood": r[1], "timestamp": r[2], "voice": r[3]} for r in c.fetchall()]
    return render_template("visit_garden.html", memories=mems)

@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.get_data(as_text=True))
    if update:
        bot.process_new_updates([update])
    return "OK", 200

@app.route("/")
def index():
    return "🌼 SoulGarden Bot is live."

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=8080)
