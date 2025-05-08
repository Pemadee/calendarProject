from datetime import datetime
from src.utils.scheduler_instance import scheduler
from src.utils.token_db import get_all_tokens 
from src.utils.func import refresh_token_safe

def auto_refresh_tokens():
    print("🔁 ตรวจสอบ token ทั้งหมด...")
    all_tokens = get_all_tokens()
    for token in all_tokens:
        if not token.expiry:
            print(f"⚠️ Token {token.email} ไม่มีข้อมูลวันหมดอายุ → รีเฟรช")
            refresh_token_safe(token.email)
        else:
            seconds_left = (token.expiry - datetime.utcnow()).total_seconds()
            if seconds_left < 600:  # ถ้าเหลือน้อยกว่า 10 นาที
                print(f"🔄 Token {token.email} จะหมดใน {int(seconds_left)} วินาที → รีเฟรช")
                refresh_token_safe(token.email)
# เพิ่ม job ลง scheduler ตัวกลาง
scheduler.add_job(auto_refresh_tokens, 'interval', minutes=15)