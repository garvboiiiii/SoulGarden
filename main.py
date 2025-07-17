import os
from flask import Flask, request, render_template
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from db import init_db, add_user, log_memory, get_dashboard_data
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
init_db()

# --- Start ---
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.first_name or "friend"
    add_user(user_id, username)

    welcome = f"🌱 Welcome *{username}* to SoulGarden!\n\n" \
              "Each memory you plant earns you 🌸 points.\n" \
              "Write about your day, thoughts, or voice your feelings.\n\n" \
              "Your garden grows as your soul blossoms 🌼"

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("📝 Write Memory", callback_data="write"),
        InlineKeyboardButton("📊 My Garden", web_app=WebAppInfo(url=f"{WEBHOOK_URL}/dashboard/{user_id}"))
    )

    bot.send_message(message.chat.id, welcome, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "write")
def prompt_write(call):
    bot.send_message(call.message.chat.id, "🪶 Share your memory or thought...")

@bot.message_handler(func=lambda m: True)
def capture_memory(message):
    user_id = message.from_user.id
    if message.text:
        log_memory(user_id, message.text, "text")
        bot.reply_to(message, "🌸 Memory planted! Visit your garden to see it bloom.")

# --- Dashboard Route ---
@app.route("/dashboard/<int:user_id>")
def dashboard(user_id):
    user, entries = get_dashboard_data(user_id)
    if not user:
        return "User not found"

    name, points = user
    return render_template("dashboard.html", name=name, user_id=user_id, points=points, entries=entries)

# --- Webhook Setup ---
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "ok", 200

@app.route("/")
def index():
    return "🌿 SoulGarden Bot Running"

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=5000)
