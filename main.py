import os
import sqlite3
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request, render_template
from utils import log_memory, get_user_stats, get_other_memories, calculate_streak

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, static_folder="static")

# --- DB Setup ---
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

# --- Buttons ---
def menu_buttons(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📝 Log Memory", callback_data="log"),
        InlineKeyboardButton("🎤 Voice Note", callback_data="voice"),
        InlineKeyboardButton("🌍 Explore Gardens", callback_data="explore"),
        InlineKeyboardButton("📊 Dashboard", url=f"{WEBHOOK_URL}/dashboard/{user_id}"),
        InlineKeyboardButton("ℹ️ About", callback_data="about")
    )
    return markup

# --- Bot Start ---
@bot.message_handler(commands=['start'])
def start(message):
    print("✅ Received /start") 
    user_id = message.from_user.id
    username = message.from_user.username or f"user{user_id}"
    c.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    
    bot.send_message(
        user_id,
        f"🌸 Welcome to *SoulGarden*, @{username}!\n\n"
        "🪴 This is your peaceful space to grow mentally.\n"
        "📝 Log memories, 🎧 share voice notes, and 🌍 explore thoughts of others anonymously.\n\n"
        "Earn 🌱 by returning daily.\nLet’s grow your garden together!",
        reply_markup=menu_buttons(user_id),
        parse_mode='Markdown'
    )


@bot.message_handler(commands=['help'])
def help_cmd(message):
    bot.send_message(message.chat.id, "Type /start to begin your SoulGarden journey 🌼\nLog memories daily and explore others anonymously.")

# --- Handle Buttons ---
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    user_id = call.from_user.id

    if call.data == "log":
        bot.send_message(user_id, "📝 What's on your mind today?")
        bot.register_next_step_handler(call.message, handle_memory)

    elif call.data == "voice":
        bot.send_message(user_id, "🎤 Send your voice memory now.")

    elif call.data == "explore":
        memories = get_other_memories(user_id)
        if not memories:
            bot.send_message(user_id, "🌱 No public memories to show yet.")
            return

        text = "🌍 *Anonymous Memories from Other Gardens:*\n\n"
        for mem in memories:
            mood = mem[2]
            text += f"🧠 {mem[1]} ({mood})\n\n"
        bot.send_message(user_id, text, parse_mode="Markdown")

    elif call.data == "about":
        bot.send_message(user_id, "💫 *About SoulGarden:*\nThis is a safe space to log thoughts anonymously. Every memory helps grow your unique garden.🌼\n\nEarn 🌱 for streaks. Voice, emojis, and plants included.\nBuilt with love 💜", parse_mode="Markdown")

# --- Text Memory ---
def handle_memory(message):
    user_id = message.from_user.id
    text = message.text.strip()
    if not text:
        bot.send_message(user_id, "❗Please type something to log.")
        return
    markup = InlineKeyboardMarkup()
    for mood in ["😊", "😔", "🤯", "💡", "😴"]:
        markup.add(InlineKeyboardButton(mood, callback_data=f"mood|{mood}|{text}"))
    bot.send_message(user_id, "💬 Choose a mood for this memory:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mood|"))
def handle_mood(call):
    user_id = call.from_user.id
    _, mood, text = call.data.split("|", 2)
    log_memory(user_id, text, mood)
    stats = get_user_stats(user_id)
    bot.send_message(user_id, f"🌱 Memory logged! You're on a {stats['streak']} day streak.\nTotal Points: {stats['points']}")

# --- Voice Notes ---
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

# --- Webhook ---
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

@app.route("/leaderboard")
def leaderboard():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    return render_template("leaderboard.html", users=rows)

@app.route("/" + BOT_TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "", 200

@app.route("/")
def index():
    return "🌸 SoulGarden Bot is alive."

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

# --- Run ---
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=5000)
