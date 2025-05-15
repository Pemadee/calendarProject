# src/utils/auto_refresh_jobs.py
from datetime import datetime
from utils.scheduler_instance import scheduler
from utils.token_db import get_all_tokens
from utils.func import refresh_token_safe

def auto_refresh_tokens():
    """ฟังก์ชันตรวจสอบและรีเฟรช tokens"""
    try:
        print(f"🔁 ตรวจสอบ token ทั้งหมด... ({datetime.now()})")
        all_tokens = get_all_tokens()
        
        if not all_tokens:
            print("❌ ไม่พบ token ใดๆ ในฐานข้อมูล")
            return
            
        print(f"📊 พบ token ทั้งหมด {len(all_tokens)} รายการ")
        
        for token in all_tokens:
            if not token.expiry:
                print(f"⚠️ Token {token.email} ไม่มีข้อมูลวันหมดอายุ → รีเฟรช")
                refresh_token_safe(token.email)
            else:
                seconds_left = (token.expiry - datetime.utcnow()).total_seconds()
                if seconds_left < 600:  # ถ้าเหลือน้อยกว่า 10 นาที
                    print(f"🔄 Token {token.email} จะหมดใน {int(seconds_left)} วินาที → รีเฟรช")
                    refresh_token_safe(token.email)
                else:
                    print(f"✅ Token {token.email} ยังไม่หมดอายุ เหลือเวลาอีก {int(seconds_left)} วินาที")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดใน auto_refresh_tokens: {str(e)}")
        import traceback
        print(traceback.format_exc())

