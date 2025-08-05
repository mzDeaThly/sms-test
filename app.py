# ==============================================================================
# Imports - ส่วนนำเข้า Library ที่จำเป็น
# ==============================================================================
from flask import Flask, request, jsonify, abort
import threading
import time
from datetime import datetime, timedelta
import os 
import sys 
import json
import requests # <<<<<<< เพิ่ม Library นี้

# เราไม่ต้องการ thaibulksms-api อีกต่อไป

# Import สำหรับ LINE
try:
    from linebot.v3 import WebhookHandler
    from linebot.v3.exceptions import InvalidSignatureError
    from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
    from linebot.v3.webhooks import MessageEvent, TextMessageContent
    LINE_SDK_AVAILABLE = True
except ImportError:
    LINE_SDK_AVAILABLE = False

# ==============================================================================
# Flask App & Global Variables
# ==============================================================================
app = Flask(__name__)
start_time = datetime.now()

# ==============================================================================
# Configuration - ส่วนตั้งค่าต่างๆ
# ==============================================================================
# -- ThaiBulkSMS Configuration --
THB_API_KEY = os.environ.get("THB_API_KEY", "YOUR_THB_API_KEY")
THB_API_SECRET = os.environ.get("THB_API_SECRET", "YOUR_THB_API_SECRET")
# ไม่ต้องมี THB_SENDER_NAME ใน Config แล้ว เพราะจะส่งไปพร้อมกับคำสั่ง

# -- LINE OA Configuration --
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "YOUR_LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "YOUR_LINE_CHANNEL_ACCESS_TOKEN")

# -- App Configuration --
DEFAULT_COUNTRY_CODE = "+66"
LOG_FILE = "sent_log.json"

# -- Clients Initialization --
if LINE_SDK_AVAILABLE:
    handler = WebhookHandler(LINE_CHANNEL_SECRET)
    line_configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
else:
    handler = None
    line_configuration = None

# ... (Helper Functions: format_phone_number, load_sent_log, save_sent_log เหมือนเดิม) ...
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
        with open(LOG_FILE, 'r', encoding='utf-8') as f: return set(json.load(f))
    except Exception: return set()
def save_sent_log(sent_set):
    with open(LOG_FILE, 'w', encoding='utf-8') as f: json.dump(list(sent_set), f, ensure_ascii=False, indent=2)

# ==============================================================================
# LINE OA Webhook - จุดรับคำสั่งจาก LINE
# ==============================================================================
@app.route("/webhook", methods=['POST'])
def webhook():
    # ... (โค้ดส่วนนี้เหมือนเดิมทุกประการ) ...
    if not LINE_SDK_AVAILABLE: abort(500)
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    # ... (โค้ดส่วนนี้เหมือนเดิมทุกประการ) ...
    text_input = event.message.text.strip()
    command_parts = text_input.split(maxsplit=3)
    reply_token = event.reply_token
    if len(command_parts) == 4 and command_parts[0].lower() == "run":
        target = command_parts[1]
        sender_name = command_parts[2]
        custom_message = command_parts[3]
        def on_complete_callback(s, f, e=None):
            summary_message = f"เกิดข้อผิดพลาด: {e}" if e else f"สรุปผลการส่งสำหรับ '{target}'\n(Sender: {sender_name}):\n✅ สำเร็จ: {s}\n❌ ล้มเหลว: {f}"
            with ApiClient(line_configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=summary_message)]))
        if target.lower().endswith(".txt"):
            threading.Thread(target=run_sms_job_from_line, args=(target, sender_name, custom_message, on_complete_callback)).start()
        elif target.startswith("0") and len(target) == 10 and target.isdigit():
            threading.Thread(target=process_bulk_sms, args=([target], sender_name, custom_message, on_complete_callback)).start()
        else:
            reply_command_error(reply_token)
    else:
        reply_command_error(reply_token)

def reply_command_error(reply_token):
    # ... (โค้ดส่วนนี้เหมือนเดิมทุกประการ) ...
    with ApiClient(line_configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        reply_text = "คำสั่งไม่ถูกต้อง รูปแบบคือ:\nrun <เป้าหมาย> <SenderName> <ข้อความ>"
        line_bot_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=reply_text)]))

def run_sms_job_from_line(filename, sender_name, message, callback):
    # ... (โค้ดส่วนนี้เหมือนเดิมทุกประการ) ...
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            phone_numbers = f.read().strip().splitlines()
        process_bulk_sms(phone_numbers, sender_name, message, callback)
    except FileNotFoundError:
        callback(0, 0, error_message=f"ไม่พบไฟล์ '{filename}'")
    except Exception as e:
        callback(0, 0, error_message=f"เกิดข้อผิดพลาด: {e}")

# ==============================================================================
# Core SMS Processing (ส่วนที่แก้ไขหลักตามเอกสาร API v2)
# ==============================================================================
def process_bulk_sms(phone_numbers, sender_name, message, callback=None):
    """
    ฟังก์ชันส่ง SMS ที่เปลี่ยนไปยิง API v2 โดยตรง
    """
    print(f"--- เริ่มงานส่ง SMS (Sender: {sender_name}) ---")
    
    # URL ของ API ตามเอกสาร
    url = "https://api-v2.thaibulksms.com/sms"
    
    headers = {
        'Content-Type': 'application/json',
        'api_key': THB_API_KEY,
        'api_secret': THB_API_SECRET,
    }

    successful_sends = 0; failed_sends = 0
    sent_log = load_sent_log(); sent_this_run = set()

    for number in phone_numbers:
        formatted_number_plus = format_phone_number(number)
        number_for_thb = formatted_number_plus.replace("+", "") # API v2 ต้องการเบอร์แบบไม่มี +
        dedup_key = f"{formatted_number_plus}|{sender_name}|{message}"
        
        if dedup_key in sent_log or dedup_key in sent_this_run:
            print(f"⚠️ ข้ามการส่งซ้ำไปยัง: {number_for_thb}")
            continue
        try:
            # สร้าง Body ของ Request ตามเอกสาร
            payload = {
                "msisdn": number_for_thb,
                "message": message,
                "sender": sender_name
            }
            
            # ส่ง Request
            response = requests.post(url, headers=headers, json=payload)
            response_data = response.json()

            if response.status_code == 201: # 201 Created คือสำเร็จตามเอกสาร
                print(f"✅ ส่งข้อความเข้าคิวสำเร็จ: {number_for_thb}")
                sent_log.add(dedup_key); sent_this_run.add(dedup_key)
                successful_sends += 1
            else:
                error_detail = response_data.get('error', {}).get('description', 'ไม่ทราบสาเหตุ')
                print(f"❌ ส่งข้อความล้มเหลว: {number_for_thb}, เหตุผล: {error_detail}")
                failed_sends += 1
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาดร้ายแรงในการส่ง: {number_for_thb}, เหตุผล: {str(e)}")
            failed_sends += 1
        time.sleep(0.5)
    
    save_sent_log(sent_log)
    print("--- งานส่ง SMS เสร็จสิ้น ---")
    if callback:
        callback(successful_sends, failed_sends)

# ... (ส่วนที่เหลือ /webhook GET, /api/status, /, if __name__ == '__main__' เหมือนเดิม) ...
@app.route("/thaibulksms-webhook", methods=['GET'])
def thaibulksms_webhook():
    print(f"ได้รับ Webhook จาก ThaiBulkSMS: {request.args.to_dict()}")
    return "OK", 200
@app.route('/api/status', methods=['GET'])
def status():
    uptime = datetime.now() - start_time
    return jsonify({"สถานะ uptime": str(timedelta(seconds=int(uptime.total_seconds())))})
@app.route('/', methods=['GET'])
def main():
    return jsonify({"สถานะบริการ": "ออนไลน์", "ประเภทบริการ": "เกตเวย์สำหรับส่ง SMS (ThaiBulkSMS v2)"})
if __name__ == '__main__':
    if not LINE_SDK_AVAILABLE: # ไม่ต้องเช็ค THB_SDK_AVAILABLE แล้ว
        print("!!! ข้อผิดพลาดร้ายแรง: ยังไม่ได้ติดตั้งไลบรารีที่จำเป็น !!!")
        print("กรุณารันคำสั่ง: pip install line-bot-sdk")
        sys.exit(1)
        
    print("--- เริ่มต้นการทำงานในโหมดเซิร์ฟเวอร์ ---")
    print("รอรับคำสั่งจาก LINE... กด CTRL+C เพื่อหยุดการทำงาน")
    app.run(debug=True, host='0.0.0.0', port=5000)
