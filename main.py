# main.py
import os
import sqlite3
from flask import Flask, request, render_template, redirect, url_for, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from datetime import datetime, timedelta
from utils import get_streak, award_points, store_memory

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Database
conn = sqlite3.connect("garden.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    points INTEGER DEFAULT 0,
    last_log DATE
)''')
c.execute('''CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    text TEXT,
    mood TEXT,
    date DATE,
    voice TEXT
)''')
conn.commit()

# Bot UI

def main_buttons():
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("📝 Log Memory", callback_data="log_memory"),
        InlineKeyboardButton("🌼 My Garden", web_app=WebAppInfo(url=f"{WEBHOOK_URL}/dashboard")),
        InlineKeyboardButton("❓ About", callback_data="about")
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.first_name
    c.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()

    bot.send_message(
        user_id,
        f"🌱 Welcome *{username}* to *SoulGarden*!\n\nPlant memories daily. Grow your digital soul garden.",
        reply_markup=main_buttons(),
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    user_id = call.from_user.id

    if call.data == "log_memory":
        bot.send_message(user_id, "🌸 What's your memory today? You can also send a voice note optionally.")
        bot.register_next_step_handler(call.message, get_memory_text)

    elif call.data == "about":
        bot.send_message(user_id, "🧠 *SoulGarden* lets you store daily reflections as flowers in a garden.\n🎧 Send text or voice.\n🎯 Earn points for daily logging.\n🌸 Grow streaks and your own personal digital sanctuary.", parse_mode="Markdown")

def get_memory_text(message):
    user_id = message.from_user.id
    text = message.text

    # Ask for mood
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("😊", callback_data=f"mood_happy|{text}"),
        InlineKeyboardButton("😢", callback_data=f"mood_sad|{text}"),
        InlineKeyboardButton("😐", callback_data=f"mood_neutral|{text}")
    )
    bot.send_message(user_id, "What was the mood?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mood_"))
def handle_mood(call):
    user_id = call.from_user.id
    mood, text = call.data.split("|")
    mood = mood.replace("mood_", "")

    store_memory(user_id, text, mood)
    award_points(user_id)
    bot.send_message(user_id, f"🌼 Memory saved with mood *{mood}*. Points awarded!", parse_mode="Markdown")

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    user_id = message.from_user.id
    file_info = bot.get_file(message.voice.file_id)
    file_path = file_info.file_path
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

    text = "Voice Memory"
    mood = "neutral"
    store_memory(user_id, text, mood, voice_url=file_url)
    award_points(user_id)
    bot.send_message(user_id, "🎧 Voice memory saved. 🌸")

@app.route("/" + BOT_TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "", 200

@app.route("/")
def index():
    return "🌱 SoulGarden Bot running."

@app.route("/dashboard")
def dashboard():
    c.execute("SELECT users.username, users.points, users.last_log, memories.text, memories.mood, memories.date, memories.voice FROM users JOIN memories ON users.id = memories.user_id ORDER BY memories.date DESC")
    data = c.fetchall()
    return render_template("dashboard.html", data=data)

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host='0.0.0.0', port=5000)
