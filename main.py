# main.py

import os
import sqlite3
from datetime import datetime
from flask import Flask, request, render_template, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from utils import log_memory, get_streak_data, add_voice_memory

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# Database Setup
conn = sqlite3.connect("data.db", check_same_thread=False)
c = conn.cursor()
c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        streak INTEGER DEFAULT 0,
        last_log TEXT,
        points INTEGER DEFAULT 0
    )
""")
c.execute("""
    CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        mood TEXT,
        text TEXT,
        voice TEXT,
        timestamp TEXT
    )
""")
conn.commit()

# --- Bot Commands ---
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.first_name
    c.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    welcome_msg = f"🌱 *Welcome to SoulGarden, {username}!*\n\nHere, you plant memories daily and watch your garden grow.\n\nLog your mood, record your thoughts, and earn 🌼 points to evolve your soul garden."
    bot.send_message(user_id, welcome_msg, reply_markup=main_menu(user_id), parse_mode="Markdown")

@bot.message_handler(commands=['about'])
def about(message):
    bot.send_message(message.chat.id, "🌿 *SoulGarden* is your emotional memory garden.\nEach day you log your mood, your garden grows with flowers.\nEarn 🌼 points for consistency and bloom your own soul forest!", parse_mode="Markdown")

# --- Keyboard Buttons ---
def main_menu(user_id):
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🌼 Add Memory", callback_data="log_memory"),
        InlineKeyboardButton("📈 View Garden", web_app=WebAppInfo(url=f"{WEBHOOK_URL}/dashboard/{user_id}")),
        InlineKeyboardButton("🎧 Add Voice", callback_data="add_voice"),
        InlineKeyboardButton("🧠 About", callback_data="about")
    )
    return markup

# --- Callback Queries ---
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    user_id = call.from_user.id

    if call.data == "log_memory":
        bot.send_message(user_id, "📝 What's your memory today? Start with your mood (happy, sad, angry, etc.)")
        bot.register_next_step_handler(call.message, process_mood)

    elif call.data == "add_voice":
        bot.send_message(user_id, "🎤 Send a voice note to add a memory.")

    elif call.data == "about":
        about(call.message)

# --- Mood and Text Logging ---
def process_mood(message):
    user_id = message.from_user.id
    mood = message.text.strip()
    bot.send_message(user_id, f"💬 Great! Now tell me your memory for today under that mood '{mood}'.")
    bot.register_next_step_handler(message, lambda m: save_memory(m, mood))

def save_memory(message, mood):
    user_id = message.from_user.id
    text = message.text.strip()
    log_memory(user_id, mood, text)
    bot.send_message(user_id, "🌸 Memory logged successfully! Keep growing your SoulGarden.", reply_markup=main_menu(user_id))

# --- Voice Notes ---
@bot.message_handler(content_types=['voice'])
def receive_voice(message):
    user_id = message.from_user.id
    file_id = message.voice.file_id
    add_voice_memory(user_id, file_id)
    bot.send_message(user_id, "🎧 Voice memory saved to your garden.")

# --- Web Dashboard ---
@app.route("/dashboard/<int:user_id>")
def dashboard(user_id):
    streak_data = get_streak_data(user_id)
    c.execute("SELECT username, points FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    c.execute("SELECT mood, text, timestamp, voice FROM memories WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
    memories = c.fetchall()
    return render_template("dashboard.html", user=user, streak_data=streak_data, memories=memories, user_id=user_id)

@app.route("/" + BOT_TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "", 200

@app.route("/")
def index():
    return "🌷 SoulGarden Bot is running."

# --- Start ---
if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host='0.0.0.0', port=5000)
