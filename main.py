import os
import sqlite3
import telebot
from flask import Flask, request, render_template
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from utils import log_memory, get_user_stats, get_other_memories, calculate_streak

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, static_folder="static", template_folder="templates")

conn = sqlite3.connect("garden.db", check_same_thread=False)
c = conn.cursor()

# --- DB Tables ---
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,
    streak INTEGER DEFAULT 0,
    last_entry TEXT,
    points INTEGER DEFAULT 0
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS memories (
    user_id INTEGER,
    text TEXT,
    mood TEXT,
    timestamp TEXT,
    voice_path TEXT
)
""")
conn.commit()

# --- Temporary Store ---
user_memory_temp = {}

# --- Commands Menu ---
bot.set_my_commands([
    BotCommand("start", "Start your SoulGarden"),
    BotCommand("log", "Log a new memory"),
    BotCommand("voice", "Send a voice memory"),
    BotCommand("memories", "View your past memories"),
    BotCommand("leaderboard", "View top users"),
    BotCommand("explore", "Explore other gardens"),
    BotCommand("about", "About SoulGarden"),
    BotCommand("help", "Help with commands")
])

def menu_buttons(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📝 Log Memory", callback_data="log"),
        InlineKeyboardButton("🎤 Voice Note", callback_data="voice"),
        InlineKeyboardButton("📜 My Memories", callback_data="memories"),
        InlineKeyboardButton("🏆 Leaderboard", url=f"{WEBHOOK_URL}/leaderboard"),
        InlineKeyboardButton("🌍 Explore Gardens", callback_data="explore"),
        InlineKeyboardButton("📊 Dashboard", url=f"{WEBHOOK_URL}/dashboard/{user_id}"),
        InlineKeyboardButton("ℹ️ About", callback_data="about")
    )
    return markup

# --- Start ---
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user{user_id}"
    c.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()

    bot.send_message(
        user_id,
        f"🌸 Welcome to <b>SoulGarden</b>, @{username}!\n"
        "🪴 This is your peaceful space to grow mentally.\n"
        "📝 Log memories, 🎧 share voice notes, and 🌍 explore thoughts of others anonymously.\n"
        "Earn 🌱 by returning daily.\n\nLet’s grow your garden together!",
        reply_markup=menu_buttons(user_id),
        parse_mode='HTML'
    )

# --- Help ---
@bot.message_handler(commands=['help'])
def help_cmd(message):
    bot.send_message(message.chat.id, "🌼 Use /log to share a memory, /voice to send a voice note, or /memories to revisit your thoughts.")

# --- Log Memory ---
@bot.message_handler(commands=['log'])
def log_cmd(message):
    bot.send_message(message.chat.id, "📝 What's on your mind today?")
    bot.register_next_step_handler(message, handle_memory)

def handle_memory(message):
    user_id = message.from_user.id
    text = message.text.strip()
    if not text:
        bot.send_message(user_id, "❗Please type something to log.")
        return

    user_memory_temp[user_id] = text
    markup = InlineKeyboardMarkup()
    for mood in ["😊", "😔", "🤯", "💡", "😴"]:
        markup.add(InlineKeyboardButton(mood, callback_data=f"mood|{mood}"))

    bot.send_message(user_id, "💬 Choose a mood for this memory:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mood|"))
def handle_mood(call):
    user_id = call.from_user.id
    mood = call.data.split("|", 1)[1]

    text = user_memory_temp.pop(user_id, None)
    if not text:
        bot.send_message(user_id, "❗Memory expired. Please /log again.")
        return

    log_memory(user_id, text, mood)
    stats = get_user_stats(user_id)
    bot.send_message(user_id, f"🌱 Memory saved!\n📆 Streak: {stats['streak']} days\n🌟 Points: {stats['points']}")

# --- Voice Memory ---
@bot.message_handler(commands=['voice'])
def voice_cmd(message):
    bot.send_message(message.chat.id, "🎤 Send your voice note now...")

@bot.message_handler(content_types=["voice"])
def handle_voice(message):
    user_id = message.from_user.id
    voice = message.voice
    file_info = bot.get_file(voice.file_id)
    downloaded = bot.download_file(file_info.file_path)

    os.makedirs("static/voices", exist_ok=True)
    filename = f"static/voices/{user_id}_{voice.file_id}.ogg"
    with open(filename, 'wb') as f:
        f.write(downloaded)

    log_memory(user_id, "(voice note)", "🎧", voice_path=filename)
    stats = get_user_stats(user_id)
    bot.send_message(user_id, f"🎧 Voice memory saved!\n📆 Streak: {stats['streak']} days\n🌟 Points: {stats['points']}")

# --- Memories ---
@bot.message_handler(commands=['memories'])
def memories_cmd(message):
    user_id = message.from_user.id
    c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5", (user_id,))
    rows = c.fetchall()
    if not rows:
        bot.send_message(user_id, "📭 No memories logged yet.")
        return

    text = "📜 <b>Your Recent Memories:</b>\n\n"
    for r in rows:
        text += f"{r[2][:10]} - {r[1]}\n🧠 {r[0]}\n\n"
    bot.send_message(user_id, text, parse_mode="HTML")

# --- Leaderboard ---
@bot.message_handler(commands=["leaderboard"])
def leaderboard_cmd(message):
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "🌱 No users have points yet.")
        return

    text = "🏆 <b>Top Gardeners</b>\n\n"
    for i, row in enumerate(rows, 1):
        text += f"{i}. @{row[0]} — {row[1]} pts\n"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🌐 View on Website", url=f"{WEBHOOK_URL}/leaderboard"))
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=markup)

# --- Explore ---
@bot.message_handler(commands=['explore'])
def explore_cmd(message):
    explore_cmd_core(message.chat.id)

def explore_cmd_core(chat_id):
    c.execute("SELECT DISTINCT user_id FROM memories ORDER BY RANDOM() LIMIT 5")
    user_ids = [r[0] for r in c.fetchall()]
    if not user_ids:
        bot.send_message(chat_id, "🌱 No gardens to explore yet.")
        return

    for uid in user_ids:
        c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1", (uid,))
        mem = c.fetchone()
        if not mem:
            continue
        msg = f"🧠 <b>{mem[2][:10]}</b> ({mem[1]})\n{mem[0]}"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌿 Visit Garden", url=f"{WEBHOOK_URL}/explore/garden/{uid}"))
        bot.send_message(chat_id, msg, parse_mode="HTML", reply_markup=markup)

# --- About ---
@bot.message_handler(commands=['about'])
def about_cmd(message):
    bot.send_message(
        message.chat.id,
        "💫 <b>About SoulGarden:</b>\nLog your thoughts, emotions, and voice notes anonymously. Every memory helps your digital garden grow.\n\nEarn 🌱 by returning daily. Peaceful, private, and purposeful 🌼",
        parse_mode="HTML"
    )

# --- Callback Buttons ---
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
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

# --- Web Routes ---
@app.route("/dashboard/<int:user_id>")
def dashboard(user_id):
    c.execute("SELECT username, points FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        return "User not found", 404

    name, points = user
    streak = calculate_streak(user_id)
    c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
    memories = [{
        "text": row[0],
        "mood": row[1],
        "timestamp": row[2],
        "voice": row[3]
    } for row in c.fetchall()]

    return render_template("dashboard.html", name=name, points=points, streak=streak, memories=memories)

@app.route("/leaderboard")
def leaderboard():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    return render_template("leaderboard.html", users=rows)

@app.route("/explore/garden/<int:user_id>")
def visit_garden(user_id):
    c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
    memories = [{
        "text": row[0],
        "mood": row[1],
        "timestamp": row[2],
        "voice": row[3]
    } for row in c.fetchall()]
    return render_template("visit_garden.html", memories=memories)

@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.get_data(as_text=True))
    if update:
        bot.process_new_updates([update])
    return "OK", 200

@app.route("/")
def index():
    return "🌸 SoulGarden Bot is running."

# --- Start App ---
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=8080)
