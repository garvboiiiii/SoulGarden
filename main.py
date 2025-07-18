import os
import sqlite3
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask, request, render_template
from utils import log_memory, get_user_stats, get_other_memories, calculate_streak

# --- Configuration ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, static_folder="static", template_folder="templates")

# --- Database Setup ---
conn = sqlite3.connect("garden.db", check_same_thread=False)
c = conn.cursor()
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

# --- In-Memory Temp Store ---
user_memory_temp = {}

# --- Bot Menu ---
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

# --- Commands ---
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

@bot.message_handler(commands=['help'])
def help_cmd(message):
    bot.send_message(message.chat.id, "Type /start to begin your SoulGarden journey 🌼\nLog memories daily and explore others anonymously.")

@bot.message_handler(commands=["leaderboard"])
def leaderboard_cmd(message):
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "No users have points yet 🌱")
        return

    text = "🏆 <b>Top Gardeners</b>\n\n"
    for i, row in enumerate(rows, 1):
        text += f"{i}. @{row[0]} — {row[1]} pts\n"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🌐 View on Website", url=f"{WEBHOOK_URL}/leaderboard"))
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(commands=['explore'])
def explore_cmd(message):
    memories = get_other_memories(message.from_user.id)
    if not memories:
        bot.send_message(message.chat.id, "🌱 No public memories to show yet.")
        return
    text = "🌍 <b>Anonymous Memories from Other Gardens:</b>\n\n"
    for mem in memories:
        mood = mem[2]
        text += f"🧠 {mem[1]} ({mood})\n\n"
    bot.send_message(message.chat.id, text, parse_mode="HTML")

@bot.message_handler(commands=['about'])
def about_cmd(message):
    bot.send_message(
        message.chat.id,
        "💫 <b>About SoulGarden:</b>\nThis is a safe space to log thoughts anonymously. Every memory helps grow your unique garden.🌼\n\n"
        "Earn 🌱 for streaks. Voice, emojis, and plants included.\nBuilt with love 💜",
        parse_mode="HTML"
    )

# --- Callback Handler ---
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    user_id = call.from_user.id
    data = call.data

    if data == "log":
        bot.send_message(user_id, "📝 What's on your mind today?")
        bot.register_next_step_handler(call.message, handle_memory)

    elif data == "voice":
        bot.send_message(user_id, "🎤 Send your voice memory now.")

    elif data == "memories":
        c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5", (user_id,))
        rows = c.fetchall()
        if not rows:
            bot.send_message(user_id, "📭 No memories logged yet.")
            return
        text = "📜 <b>Your Recent Memories:</b>\n\n"
        for r in rows:
            text += f"{r[2][:10]} - {r[1]}\n🧠 {r[0]}\n\n"
        bot.send_message(user_id, text, parse_mode="HTML")

    elif data == "explore":
        explore_cmd(call.message)

    elif data == "about":
        about_cmd(call.message)

# --- Memory Logging ---
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

    text = user_memory_temp.get(user_id)
    if not text:
        bot.send_message(user_id, "❗Memory expired. Please log again.")
        return

    log_memory(user_id, text, mood)
    stats = get_user_stats(user_id)
    user_memory_temp.pop(user_id, None)

    bot.send_message(user_id, f"🌱 Memory logged! You're on a {stats['streak']} day streak.\nTotal Points: {stats['points']}")

# --- Voice Note Logging ---
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
    bot.send_message(user_id, f"🎧 Voice memory saved! Streak: {stats['streak']} days. Points: {stats['points']}")

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
    memories_raw = c.fetchall()

    memories = [{
        "text": row[0],
        "mood": row[1],
        "timestamp": row[2],
        "voice": row[3] if row[3] else None
    } for row in memories_raw]

    return render_template("dashboard.html", name=name, points=points, streak=streak, memories=memories)

@app.route("/leaderboard")
def leaderboard():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    return render_template("leaderboard.html", users=rows)

@app.route("/explore")
def explore_gardens():
    c.execute("SELECT DISTINCT user_id FROM memories ORDER BY RANDOM() LIMIT 5")
    user_ids = [r[0] for r in c.fetchall()]

    gardens = []
    for uid in user_ids:
        c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT 3", (uid,))
        memories = c.fetchall()
        gardens.append({"user_id": uid, "memories": memories})

    return render_template("explore.html", gardens=gardens)

@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.get_data(as_text=True))
    if update:
        bot.process_new_updates([update])
    return "OK", 200

@app.route("/")
def index():
    return "🌸 SoulGarden Bot is running."

# --- Launch ---
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=8080)
