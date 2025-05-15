from api.endpoints import *
import time
from datetime import datetime
from utils.scheduler_instance import scheduler
from models.token_model import init_db
from utils.auto_refresh_jobs import auto_refresh_tokens

# เริ่มต้นฐานข้อมูล
init_db()
print("✅ เริ่มต้นฐานข้อมูลเรียบร้อยแล้ว")

# เริ่มต้น scheduler
print("🔄 กำลังเริ่ม scheduler...")
scheduler.start()
print("✅ เริ่ม scheduler สำเร็จ")

# เพิ่ม job เข้าไปใน scheduler
try:
    scheduler.add_job(
        auto_refresh_tokens, 
        'interval', 
        minutes=15,  
        id='auto_refresh_tokens_job',
        replace_existing=True
    )
    print("✅ เพิ่ม job auto_refresh_tokens สำเร็จ (ทำงานทุก 1 นาที)")
except Exception as e:
    print(f"❌ ไม่สามารถเพิ่ม job ได้: {e}")


auto_refresh_tokens()

# ตรวจสอบจำนวน jobs ใน scheduler
jobs = scheduler.get_jobs()
print(f"📋 จำนวน jobs ใน scheduler: {len(jobs)}")
for job in jobs:
    print(f"  - Job ID: {job.id}, Next run: {job.next_run_time}")

print("\n🔄 scheduler กำลังทำงานในพื้นหลัง...")
print("FastAPI จะเริ่มทำงานเมื่อมีการ import แอปพลิเคชัน")