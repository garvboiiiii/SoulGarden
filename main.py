import os
import sqlite3
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask, request, render_template
from utils import log_memory, get_user_stats, get_other_memories, calculate_streak

# --- Config ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__, static_folder="static", template_folder="templates")

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

# --- Temp Store ---
user_memory_temp = {}

# --- Bot Commands ---
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

# --- /start ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    uname = message.from_user.username or f"user{uid}"
    c.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)", (uid, uname))
    conn.commit()
    bot.send_message(
        uid,
        f"🌸 Welcome to <b>SoulGarden</b>, @{uname}!\n\n🪴 A peaceful space to log memories anonymously and grow your mental garden.\nEarn 🌱 by returning daily.",
        parse_mode='HTML',
        reply_markup=menu_buttons(uid),
    )

# --- /help ---
@bot.message_handler(commands=['help'])
def help_cmd(m):
    bot.send_message(m.chat.id, "Use /start to launch the bot. Log memories, voice notes, explore, view leaderboard or dashboard anytime.")

# --- /leaderboard ---
@bot.message_handler(commands=['leaderboard'])
def leaderboard_cmd(m):
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    text = "🏆 <b>Top Gardeners</b>\n\n"
    if rows:
        for i, (u,p) in enumerate(rows,1):
            text += f"{i}. @{u} — {p} pts\n"
    else:
        text += "No points yet."
    markup = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🌐 View on website", url=f"{WEBHOOK_URL}/leaderboard")
    )
    bot.send_message(m.chat.id, text, parse_mode='HTML', reply_markup=markup)

# --- /explore ---
@bot.message_handler(commands=['explore'])
def explore_cmd(m=None):
    rows = get_other_memories(m.chat.id if m else None)
    if not rows:
        bot.send_message(m.chat.id, "🌱 No public memories yet.")
        return
    markup = InlineKeyboardMarkup()
    seen = set()
    for uid, text, mood in rows:
        if uid in seen: continue
        seen.add(uid)
        markup.add(
            InlineKeyboardButton("Visit a SoulGarden 🌿", url=f"{WEBHOOK_URL}/explore/garden/{uid}")
        )
    bot.send_message(m.chat.id, "🌍 Explore someone’s SoulGarden:", reply_markup=markup)

# --- /about ---
@bot.message_handler(commands=['about'])
def about_cmd(m):
    bot.send_message(
        m.chat.id,
        "💫 <b>About SoulGarden:</b>\nA safe, anonymous place to log thoughts. Earn points, maintain streaks, and visit others' gardens.",
        parse_mode='HTML'
    )

# --- Inline Button Handler ---
@bot.callback_query_handler(func=lambda call: True)
def cb_handler(call):
    uid = call.from_user.id
    data = call.data
    if data == "log":
        msg = bot.send_message(uid, "📝 Type your memory:")
        bot.register_next_step_handler(msg, handle_memory)
    elif data == "voice":
        bot.send_message(uid, "🎤 Send a voice note.")
    elif data == "memories":
        c.execute("SELECT text, mood, timestamp FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5", (uid,))
        rows = c.fetchall()
        text = "📜 <b>Your Recent Memories:</b>\n\n"
        if rows:
            for t, m2, ts in rows:
                text += f"{ts[:10]} {m2} — {t}\n\n"
        else:
            text = "📭 You have no memories logged."
        bot.send_message(uid, text, parse_mode='HTML')
    elif data == "explore":
        explore_cmd(call.message)
    elif data == "about":
        about_cmd(call.message)

# --- Memory Text Handler ---
def handle_memory(msg):
    uid = msg.from_user.id
    text = msg.text.strip()
    if not text:
        bot.send_message(uid, "❗Type something meaningful.")
        return
    user_memory_temp[uid] = text
    markup = InlineKeyboardMarkup()
    for mood in ["😊","😔","🤯","💡","😴"]:
        markup.add(InlineKeyboardButton(mood, callback_data=f"mood|{mood}"))
    bot.send_message(uid, "Choose a mood:", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith("mood|"))
def mood_handler(c):
    uid = c.from_user.id
    mood = c.data.split("|",1)[1]
    text = user_memory_temp.pop(uid, None)
    if not text:
        bot.send_message(uid, "❗Memory expired. Use /log again.")
        return
    log_memory(uid, text, mood)
    stats = get_user_stats(uid)
    bot.send_message(uid, f"🌱 Logged! Streak: {stats['streak']} days. Points: {stats['points']}")

# --- Voice Handler ---
@bot.message_handler(content_types=['voice'])
def voice_handler(msg):
    uid = msg.from_user.id
    file_info = bot.get_file(msg.voice.file_id)
    data = bot.download_file(file_info.file_path)
    os.makedirs("static/voices", exist_ok=True)
    fname = f"static/voices/{uid}_{msg.voice.file_id}.ogg"
    with open(fname, 'wb') as f:
        f.write(data)
    log_memory(uid, "(voice)", "🎧", voice_path=fname)
    stats = get_user_stats(uid)
    bot.send_message(uid, f"🎧 Saved! Streak: {stats['streak']} days. Points: {stats['points']}")

# --- Web Dashboard ---
@app.route("/dashboard/<int:uid>")
def dashboard(uid):
    c.execute("SELECT username, points FROM users WHERE id = ?", (uid,))
    u = c.fetchone()
    if not u: return "User not found", 404
    name, pts = u
    streak = calculate_streak(uid)
    c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id = ? ORDER BY timestamp DESC", (uid,))
    mems = [{
        "text": row[0], "mood": row[1], "timestamp": row[2], "voice": row[3]
    } for row in c.fetchall()]
    return render_template("dashboard.html", name=name, points=pts, streak=streak, memories=mems)

# --- Leaderboard Page ---
@app.route("/leaderboard")
def leaderboard_web():
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    return render_template("leaderboard.html", users=c.fetchall())

# --- Explore Gardens Index ---
@app.route("/explore")
def explore_web():
    c.execute("SELECT DISTINCT user_id FROM memories ORDER BY RANDOM() LIMIT 5")
    uids = [r[0] for r in c.fetchall()]
    gardens = []
    for x in uids:
        c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT 3", (x,))
        gardens.append({"user_id": x, "memories": c.fetchall()})
    return render_template("explore.html", gardens=gardens)

# --- Visit Single Garden ---
@app.route("/explore/garden/<int:uid>")
def visit_garden(uid):
    c.execute("SELECT text, mood, timestamp, voice_path FROM memories WHERE user_id = ? ORDER BY timestamp DESC", (uid,))
    rows = c.fetchall()
    if not rows: return "Empty garden", 404
    mems = [{"text": r[0], "mood": r[1], "timestamp": r[2], "voice": r[3]} for r in rows]
    return render_template("visit_garden.html", memories=mems)

# --- Webhook endpoint ---
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.get_data(as_text=True))
    bot.process_new_updates([update])
    return "OK"

@app.route("/")
def index():
    return "🌸 SoulGarden running!"

# --- Start App ---
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
