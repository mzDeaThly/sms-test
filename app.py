# ... (โค้ดส่วน Imports, Configuration, Helper Functions เหมือนเดิมทั้งหมด) ...
from flask import Flask, request, jsonify, abort
import threading
import time
from datetime import datetime, timedelta
import os 
import sys 
import json

try:
    from thaibulksms_api.sms import SMS as ThaiBulkSMS
    THB_SDK_AVAILABLE = True
except ImportError:
    THB_SDK_AVAILABLE = False

try:
    from linebot.v3 import WebhookHandler
    from linebot.v3.exceptions import InvalidSignatureError
    from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
    from linebot.v3.webhooks import MessageEvent, TextMessageContent
    LINE_SDK_AVAILABLE = True
except ImportError:
    LINE_SDK_AVAILABLE = False

app = Flask(__name__)
start_time = datetime.now()

THB_API_KEY = os.environ.get("THB_API_KEY", "YOUR_THB_API_KEY")
THB_API_SECRET = os.environ.get("THB_API_SECRET", "YOUR_THB_API_SECRET")
THB_SENDER_NAME = os.environ.get("THB_SENDER_NAME", "YOUR_APPROVED_SENDER_NAME")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "YOUR_LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "YOUR_LINE_CHANNEL_ACCESS_TOKEN")
DEFAULT_AUTO_RUN_MESSAGE = "นี่คือข้อความที่ถูกกำหนดไว้ในระบบ"
DEFAULT_COUNTRY_CODE = "+66"
LOG_FILE = "sent_log.json"

if THB_SDK_AVAILABLE:
    thaibulksms_client = ThaiBulkSMS(api_key=THB_API_KEY, api_secret=THB_API_SECRET)
else:
    thaibulksms_client = None
if LINE_SDK_AVAILABLE:
    handler = WebhookHandler(LINE_CHANNEL_SECRET)
    line_configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
else:
    handler = None
    line_configuration = None

def format_phone_number(number_str):
    number_str = number_str.strip()
    if number_str.startswith('0') and len(number_str) == 10:
        return f"{DEFAULT_COUNTRY_CODE}{number_str[1:]}"
    elif number_str.startswith('+'):
        return number_str
    else:
        return number_str
def load_sent_log():
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(data)
    except Exception:
        return set()
def save_sent_log(sent_set):
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(sent_set), f, ensure_ascii=False, indent=2)

# ==============================================================================
# Webhooks (จุดรับข้อมูลจากภายนอก)
# ==============================================================================

# 1. Webhook สำหรับรับ "คำสั่ง" จาก LINE OA (ใช้ POST)
@app.route("/webhook", methods=['POST'])
def webhook():
    if not LINE_SDK_AVAILABLE: abort(500)
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 2. Webhook สำหรับรับ "สถานะ" จาก ThaiBulkSMS (ใช้ GET) <<<<<<<<<<< เพิ่มใหม่
@app.route("/thaibulksms-webhook", methods=['GET'])
def thaibulksms_webhook():
    print("--- ได้รับ Webhook จาก ThaiBulkSMS ---")
    # ThaiBulkSMS จะส่งข้อมูลกลับมาเป็น Query Parameter ใน URL
    params = request.args
    print(f"ข้อมูลที่ได้รับ: {params.to_dict()}")
    # คุณสามารถนำข้อมูลนี้ไปอัปเดตสถานะในฐานข้อมูลหรือไฟล์ Log ต่อได้
    # เช่น params.get('credit_remain'), params.get('update_time')
    return "OK", 200 # ตอบกลับสถานะ 200 OK ให้ ThaiBulkSMS ทราบ


# ==============================================================================
# LINE OA Logic - ตรรกะการทำงานของ LINE
# ==============================================================================
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    # ... (โค้ดส่วนนี้เหมือนเดิมทุกประการ) ...
    text_input = event.message.text.strip()
    command_parts = text_input.split(maxsplit=2)
    reply_token = event.reply_token
    if len(command_parts) >= 2 and command_parts[0].lower() == "run":
        target = command_parts[1]
        custom_message = command_parts[2] if len(command_parts) == 3 else DEFAULT_AUTO_RUN_MESSAGE
        def on_complete_callback(s, f, e=None):
            summary_message = f"เกิดข้อผิดพลาด: {e}" if e else f"สรุปผลการส่งสำหรับ '{target}':\n✅ สำเร็จ: {s} รายการ\n❌ ล้มเหลว: {f} รายการ"
            with ApiClient(line_configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=summary_message)]))
        if target.lower().endswith(".txt"):
            threading.Thread(target=run_sms_job_from_line, args=(target, custom_message, on_complete_callback)).start()
        elif target.startswith("0") and len(target) == 10 and target.isdigit():
            threading.Thread(target=process_bulk_sms, args=([target], custom_message, on_complete_callback)).start()
        else:
            reply_command_error(reply_token)
    else:
        reply_command_error(reply_token)

def reply_command_error(reply_token):
    with ApiClient(line_configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        reply_text = "คำสั่งไม่ถูกต้อง รูปแบบคือ:\n- run <เป้าหมาย> [ข้อความ]"
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=reply_text)]))
        
def run_sms_job_from_line(filename, message, callback):
    # ... (โค้ดส่วนนี้เหมือนเดิมทุกประการ) ...
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            phone_numbers = f.read().strip().splitlines()
        process_bulk_sms(phone_numbers, message, callback)
    except FileNotFoundError:
        callback(0, 0, error_message=f"ไม่พบไฟล์ '{filename}' บนเซิร์ฟเวอร์")
    except Exception as e:
        callback(0, 0, error_message=f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")

# ==============================================================================
# Core SMS Processing - ตรรกะการส่ง SMS หลัก
# ==============================================================================
def process_bulk_sms(phone_numbers, message, callback=None):
    # ... (โค้ดส่วนนี้เหมือนเดิมทุกประการ) ...
    print("--- เริ่มงานส่ง SMS (ผ่าน ThaiBulkSMS) ---")
    successful_sends = 0; failed_sends = 0
    sent_log = load_sent_log(); sent_this_run = set()
    for number in phone_numbers:
        formatted_number_plus = format_phone_number(number)
        number_for_thb = formatted_number_plus.replace("+66", "0")
        dedup_key = f"{formatted_number_plus}|{message}"
        if dedup_key in sent_log or dedup_key in sent_this_run:
            print(f"⚠️ ข้ามการส่งซ้ำไปยัง: {number_for_thb}")
            continue
        try:
            response = thaibulksms_client.sms(msisdn=number_for_thb, message=message, sender_name=THB_SENDER_NAME)
            if response.get('status') == 'success':
                print(f"✅ ส่งข้อความเข้าคิวสำเร็จ: {number_for_thb}")
                sent_log.add(dedup_key); sent_this_run.add(dedup_key)
                successful_sends += 1
            else:
                error_detail = response.get('message', 'ไม่ทราบสาเหตุ')
                print(f"❌ ส่งข้อความล้มเหลว: {number_for_thb}, เหตุผล: {error_detail}")
                failed_sends += 1
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดร้ายแรงในการส่ง: {number_for_thb}, เหตุผล: {str(e)}")
            failed_sends += 1
        time.sleep(0.5)
    save_sent_log(sent_log)
    print("--- งานส่ง SMS เสร็จสิ้น ---")
    if callback: callback(successful_sends, failed_sends)
    
# ... (โค้ดส่วนที่เหลือ /api/status, /, และ if __name__ == '__main__' เหมือนเดิมทุกประการ) ...
@app.route('/api/status', methods=['GET'])
def status():
    uptime = datetime.now() - start_time
    uptime_str = str(timedelta(seconds=int(uptime.total_seconds())))
    return jsonify({"สถานะ uptime": uptime_str})

@app.route('/', methods=['GET'])
def main():
    return jsonify({"สถานะบริการ": "ออนไลน์", "ประเภทบริการ": "เกตเวย์สำหรับส่ง SMS (ThaiBulkSMS)"})

if __name__ == '__main__':
    if not THB_SDK_AVAILABLE or not LINE_SDK_AVAILABLE:
        print("!!! ข้อผิดพลาดร้ายแรง: ยังไม่ได้ติดตั้งไลบรารีที่จำเป็น !!!")
        if not THB_SDK_AVAILABLE: print("กรุณารันคำสั่ง: pip install thaibulksms-api")
        if not LINE_SDK_AVAILABLE: print("กรุณารันคำสั่ง: pip install line-bot-sdk")
        sys.exit(1)
    if len(sys.argv) == 2:
        file_path = sys.argv[1]
        def cli_callback(s, f, e=None):
            if e: print(f"สรุปผล -> เกิดข้อผิดพลาด: {e}")
            else: print(f"สรุปผล -> สำเร็จ: {s}, ล้มเหลว: {f}")
        run_sms_job_from_line(file_path, DEFAULT_AUTO_RUN_MESSAGE, callback=cli_callback)
    else:
        print("--- เริ่มต้นการทำงานในโหมดเซิร์ฟเวอร์ ---")
        print("รอรับคำขอ API และคำสั่งจาก LINE... กด CTRL+C เพื่อหยุดการทำงาน")
    app.run(debug=True, host='0.0.0.0', port=5000)
