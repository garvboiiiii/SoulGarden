import os
import sqlite3
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request, render_template
from utils import log_memory, get_user_stats, get_other_memories

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- DB Setup ---
conn = sqlite3.connect("garden.db", check_same_thread=False)
c = conn.cursor()
c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, streak INTEGER DEFAULT 0, last_entry TEXT, points INTEGER DEFAULT 0)")
c.execute("CREATE TABLE IF NOT EXISTS memories (user_id INTEGER, text TEXT, mood TEXT, timestamp TEXT, voice_path TEXT)")
conn.commit()

# --- Buttons ---
def menu_buttons(user_id):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
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
    user_id = message.from_user.id
    username = message.from_user.username or f"user{user_id}"
    c.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()

    bot.send_message(
        user_id,
        f"🌸 Welcome to *SoulGarden*, @{username}!\nHere, your thoughts blossom.\n\nYou earn 🌱 by logging daily memories. Let’s grow together.",
        reply_markup=menu_buttons(user_id),
        parse_mode='Markdown'
    )

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
    markup = InlineKeyboardMarkup()
    for mood in ["😊", "😔", "🤯", "💡", "😴"]:
        markup.add(InlineKeyboardButton(mood, callback_data=f"mood|{mood}|{text}"))
    bot.send_message(user_id, "💬 Choose a mood for this memory:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mood|"))
def handle_mood(call):
    user_id = call.from_user.id
    _, mood, text = call.data.split("|")
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
    filename = f"voices/{user_id}_{voice.file_id}.ogg"
    os.makedirs("voices", exist_ok=True)

    with open(filename, 'wb') as f:
        f.write(downloaded)

    # Log voice with empty text + neutral mood
    log_memory(user_id, "(voice note)", "🎤", voice_path=filename)
    stats = get_user_stats(user_id)
    bot.send_message(user_id, f"🎧 Voice memory saved! Streak: {stats['streak']} days. Points: {stats['points']}")

# --- Webhook ---
@app.route("/" + BOT_TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "", 200

@app.route("/")
def index():
    return "🌸 SoulGarden Bot is alive."

# --- Run ---
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=5000)
