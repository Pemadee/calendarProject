# 1. Standard Library Imports
import asyncio
import os
import random
import sys
import time as timeTest
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from urllib.parse import quote_plus, unquote_plus

# 2. Third-party Library Imports
import holidays
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from typing import Dict, Optional

from requests import request



# 3. Local Application Imports
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from config import *
from models.schemas import *
from models.token_model import TokenResponse
from utils.func import  *
from utils.token_db import *
from utils.scheduler_instance import scheduler
import httpx

logging.basicConfig(level=logging.INFO)


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
templates_path = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=templates_path)


app = FastAPI(title="Google Calendar API", 
              description="API สำหรับดึงข้อมูลการลงเวลาจาก Google Calendar")

# เพิ่ม CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ถ้าใช้จริงควรระบุเฉพาะโดเมนที่อนุญาต เดียวแก้
    allow_credentials=True, # อนุญาตให้ส่ง cookies
    allow_methods=["*"], # อนุญาตทุก HTTP methods
    allow_headers=["*"], # อนุญาตทุก headers
)


REDIRECT_URI = 'http://localhost:8000/'  # กำหนด redirect URI 
# ปอดการแจ้งเตือน INFO:googleapiclient.discovery_cache:file_cache is only supported with oauth2client<4.0.0
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
base_url = os.environ.get('BASE_URL2')

CLIENT_SECRET_FILE = os.getenv("CLIENT_SECRET_FILE2")

@app.middleware("http")
async def catch_all(request: Request, call_next):
    response = await call_next(request)
    if response.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={"error": "Path not found", "path": str(request.url)}
        )
    return response

@app.on_event("shutdown")
async def shutdown_event():
    print("📴 กำลังปิด scheduler...")
    if scheduler.running:
        scheduler.shutdown()
    print("✅ ปิด scheduler เรียบร้อยแล้ว")

@app.get("/")
def read_root():
    return {"message": "ยินดีต้อนรับสู่ Google Calendar API"}

@app.get("/oauth2callback")
def oauth2callback(code: str, state: str = None):
    try:
        # state ควรเป็นอีเมลที่ผู้ใช้ระบุในตอนแรก
        expected_email = state
        
        # สร้าง flow
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
        flow.redirect_uri = f"{base_url}/oauth2callback"
        
        # แลก code เป็น token
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
       

        # สร้าง service
        service = build('calendar', 'v3', credentials=credentials)
        # ดึงข้อมูลปฏิทินเพื่อดูว่าได้รับอนุญาตจากอีเมลอะไร
        calendar = service.calendars().get(calendarId='primary').execute()
        actual_email = calendar.get('id')  # อีเมลของผู้ใช้ที่ใช้ยืนยันตัวตน
        
        # ตรวจสอบว่าอีเมลตรงกันหรือไม่
        if actual_email.lower() != expected_email.lower():
            
            response = httpx.get(f"{base_url}/events/{expected_email}")
            event_data = response.json()
            redirect_url = event_data.get("redirect_url", f"/events/{expected_email}")
            
            return HTMLResponse(f"""
            <html>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #d9534f;">เกิดข้อผิดพลาดในการยืนยันตัวตน</h1>
                    <div style="background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; padding: 15px; margin-bottom: 20px;">
                        <p><strong>อีเมลที่คุณใช้ยืนยันตัวตนไม่ถูกต้อง!</strong></p>
                        <p>คุณกรอกอีเมล <strong>{expected_email}</strong> แต่ยืนยันตัวตนด้วย <strong>{actual_email}</strong></p>
                        <p>กรุณาลองใหม่โดยใช้อีเมลที่ตรงกัน</p>
                    </div>
                    <a href="{redirect_url}" style="background-color: #007bff; color: white; padding: 10px 15px; text-decoration: none; border-radius: 4px;">ลองใหม่</a>
                </body>
            </html>
            """, status_code=400)
        
        # บันทึก token
        # token_path = os.path.join(TOKEN_DIR, f'token_{actual_email}.json')
        # with open(token_path, 'w') as token_file:
        #     token_file.write(credentials.to_json())
        
        update_token(
                email=actual_email,
                access_token=credentials.token,
                refresh_token=credentials.refresh_token,
                expiry=credentials.expiry
            )

        return HTMLResponse("""
        <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #28a745;">การยืนยันตัวตนสำเร็จ!</h1>
                <div style="background-color: #d4edda; border: 1px solid #c3e6cb; border-radius: 4px; padding: 15px; margin-bottom: 20px;">
                    <p>คุณได้ยืนยันตัวตนเรียบร้อยแล้ว</p>
                    <p>คุณสามารถปิดหน้านี้และกลับไปใช้งานแอปพลิเคชันได้</p>
                </div>
            </body>
        </html>
        """)
        
    except Exception as e:
        return HTMLResponse(f"""
        <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #d9534f;">เกิดข้อผิดพลาดในการยืนยันตัวตน</h1>
                <div style="background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; padding: 15px;">
                    <p>ข้อผิดพลาด: {str(e)}</p>
                </div>
            </body>
        </html>
        """, status_code=500)


#================================================API appointment =============================================
# API 1: ดึงวัน - Updated version
import concurrent.futures
@app.post("/events/available-dates")
def get_available_dates(request: LocationRequest):
    """
    ดึงข้อมูลวันที่มีเวลาว่างตรงกันระหว่าง Manager และ Recruiter
    แสดงวันที่มีคู่ว่างให้ครบ 7 วัน โดยเว้นวันเสาร์-อาทิตย์
    รองรับทั้ง LINE และ Facebook Messenger
    """
    start = timeTest.time()
    print(f"[START] API started at {start:.6f}")
    
    # ใช้ฟังก์ชัน get_people เพื่อรับรายชื่ออีเมลผู้ใช้แยกตามประเภท M และ R
    t1 = timeTest.time()
    users_dict = get_people(
        location=request.location
    )
    print(f"[LOG] get_people done in {timeTest.time() - t1:.3f}s")
    
    # กำหนดเวลาเริ่มต้นเป็นวันที่ปัจจุบันเสมอ
    start_datetime = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # กำหนดช่วงเวลาในการดึงข้อมูล - ค้นหาไปข้างหน้าอีก 20 วัน
    end_datetime = start_datetime + timedelta(days=20)
    
    time_min = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_max = end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # สร้างรายการวันที่จะตรวจสอบ (ไม่รวมวันเสาร์-อาทิตย์)
    t2 = timeTest.time()
    years_to_check = list(range(start_datetime.year, end_datetime.year + 1))
    THAI_HOLIDAYS = holidays.Thailand(years=years_to_check)
    
    date_list = []
    current_date = start_datetime.date()
    
    while current_date <= end_datetime.date():
        is_weekend = current_date.weekday() >= 5  # เสาร์=5, อาทิตย์=6
        is_holiday = current_date in THAI_HOLIDAYS
        
        # กำหนดให้ include_holidays เป็น true เสมอ
        include_holidays = True
        
        if not is_weekend and (include_holidays or not is_holiday):
            date_list.append(current_date)
        
        current_date += timedelta(days=1)
    print(f"[LOG] building date_list done in {timeTest.time() - t2:.3f}s")
    
    # ดึงข้อมูลกิจกรรมสำหรับ Recruiter แบบ concurrent
    recruiters_events = {}
    t4 = timeTest.time()
    
    # ใช้ ThreadPoolExecutor เพื่อประมวลผลแบบ concurrent
    max_workers = min(len(users_dict['R']), 5)  # จำกัดไม่เกิน 5 threads
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # สร้าง futures สำหรับแต่ละ recruiter
        future_to_user = {
            executor.submit(check_token_and_fetch_events, user_info, time_min, time_max): user_info
            for user_info in users_dict['R']
        }
        
        # รวบรวมผลลัพธ์
        for future in concurrent.futures.as_completed(future_to_user):
            user_info = future_to_user[future]
            try:
                result = future.result()
                if result is not None:
                    recruiters_events[result['email']] = {
                        'name': result['name'],
                        'events': result['events']
                    }
            except Exception as exc:
                print(f"เกิดข้อผิดพลาดในการประมวลผลสำหรับ {user_info['Email']}: {exc}")
    
    print(f"[LOG] Concurrent token check and fetch events done in {timeTest.time() - t4:.3f}s")
    
    # ตรวจสอบวันที่มีเวลาว่าง
    available_dates = []
    t5 = timeTest.time()
    
    for date in date_list:
        has_available_slot = False
        
        # สร้างช่วงเวลาทุกๆ 30 นาที
        for hour in range(9, 18):
            for minute in [0, 30]:
                slot_start = datetime.combine(date, time(hour, minute)).astimezone(timezone.utc)
                slot_end = (slot_start + timedelta(minutes=30)).astimezone(timezone.utc)
                
                # ตรวจสอบว่ามีคู่ที่ว่างหรือไม่
                for recruiter_email, recruiter_data in recruiters_events.items():
                    recruiter_events = recruiter_data['events']
                    
                    # ตรวจสอบว่าทั้งคู่ว่างหรือไม่
                    recruiter_is_available = is_available(recruiter_events, slot_start, slot_end)
                                       
                    if recruiter_is_available:
                        has_available_slot = True
                        break
                
                if has_available_slot:
                    break
        
        if has_available_slot:
            available_dates.append(date.strftime("%Y-%m-%d"))
            
            # หยุดการค้นหาเมื่อได้วันที่ว่างครบ 7 วัน
            if len(available_dates) >= 7:
                break
    
    print(f"[LOG] Matching available slots done in {timeTest.time() - t5:.3f}s")
    
    # สร้างข้อมูลวันที่สำหรับปุ่ม
    date_items = [(create_thai_date_label(date_str), date_str) for date_str in available_dates]
    
    # สร้างปุ่มสำหรับ LINE
    line_items = create_line_quick_reply_items(date_items, max_items=13, add_back_button=False)
    
    # สร้างปุ่มสำหรับ Facebook
    facebook_items = create_facebook_quick_replies(date_items, max_items=13, add_back_button=False)
    
    # สร้างข้อความสำหรับ LINE
    line_message = {
        "type": "text",
        "text": "กรุณาเลือกวันที่ต้องการนัดประชุม",
        "quickReply": {
            "items": line_items
        }
    }
    
    # สร้างข้อความสำหรับ Facebook
    facebook_message = {
        "text": "กรุณาเลือกวันที่ต้องการนัดประชุม",
        "quick_replies": facebook_items
    }
    
    # จัดการกรณีไม่มีวันที่ว่าง
    if not date_items:
        line_message = {
            "type": "text",
            "text": "ไม่พบวันที่ว่างในระบบ กรุณาติดต่อผู้ดูแลระบบ"
        }
        facebook_message = {
            "text": "ไม่พบวันที่ว่างในระบบ กรุณาติดต่อผู้ดูแลระบบ"
        }
    
    # สร้าง response ที่รองรับทั้งสองแพลตฟอร์ม
    response = {
        "line_payload": [line_message],
        "facebook_payload": [facebook_message],
        "available_dates": available_dates
    }
    
    print(f"[DEBUG] API done at {timeTest.time() - start:.3f}s")
    
    return JSONResponse(
        content=response,
        headers={"Response-Type": "object"}
    )

# API 2: สุ่ม Recruiter ใน Google Sheet
@app.post("/select-recruiter")
async def select_available_recruiter(request: RecruiterRequest):
    """
    สุ่มเลือก recruiter ที่ว่างในวันที่ระบุ
    รับค่า: date, location
    ส่งกลับ: ข้อมูล recruiter (name, email) ที่ว่างในวันนั้น
    """
    
    start = timeTest.time()
    print(f"[START] Select recruiter API started at {start:.6f}")
    
    # ใช้ฟังก์ชัน get_people เพื่อรับรายชื่ออีเมลผู้ใช้แยกตามประเภท M และ R
    t1 = timeTest.time()
    users_dict = get_people(location=request.location)
    print(f"[LOG] get_people done in {timeTest.time() - t1:.3f}s")
    
    # กำหนดวันที่จะตรวจสอบ
    date = datetime.fromisoformat(request.date).date()
    start_datetime = datetime.combine(date, time(0, 0, 0)).astimezone(timezone.utc)
    end_datetime = datetime.combine(date, time(23, 59, 59)).astimezone(timezone.utc)
    
    time_min = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_max = end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # ดึงข้อมูลกิจกรรมสำหรับ Recruiter และเช็คว่าใครว่างบ้าง แบบ concurrent
    t3 = timeTest.time()
    available_recruiters = []
    
    # ใช้ ThreadPoolExecutor เพื่อประมวลผลแบบ concurrent
    max_workers = min(len(users_dict['R']), 5)  # จำกัดไม่เกิน 5 threads
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # สร้าง futures สำหรับแต่ละ recruiter
        future_to_user = {
            executor.submit(check_recruiter_availability, user_info, date, time_min, time_max): user_info
            for user_info in users_dict['R']
        }
        
        # รวบรวมผลลัพธ์
        for future in concurrent.futures.as_completed(future_to_user):
            user_info = future_to_user[future]
            try:
                result = future.result()
                if result is not None:
                    available_recruiters.append(result)
            except Exception as exc:
                print(f"เกิดข้อผิดพลาดในการประมวลผลสำหรับ {user_info['Email']}: {exc}")
    
    print(f"[LOG] concurrent check_available_recruiters done in {timeTest.time() - t3:.3f}s")
    
    # สุ่มเลือก recruiter จากรายการที่ว่าง
    if available_recruiters:
        selected_recruiter = random.choice(available_recruiters)
        thai_date = create_thai_date_label(request.date)
        
        print(f"[LOG] Selected recruiter: {selected_recruiter['name']} ({selected_recruiter['email']})")
        
        response = {
            "success": True,
            "date": request.date,
            "thai_date": thai_date,
            "location": request.location,
            "email": selected_recruiter['email'],
            "name": selected_recruiter['name']
        }
        print(f"Recruiter : {selected_recruiter['email']}")
        print(f"[LOG] Select recruiter API done in {timeTest.time() - start:.3f}s")
        
        return JSONResponse(
            content=response
        )
    else:
        # ไม่พบ recruiter ที่ว่าง
        response = {
            "success": False,
            "message": "ไม่พบ recruiter ที่ว่างในวันที่ระบุ",
            "date": request.date,
            "location": request.location
        }
        
        return JSONResponse(
            content=response,
            status_code=404
        )   

# API 3: ดึงช่วงเวลาว่างของ recruiter ที่ระบุ (แก้ไขจาก API เดิม)
@app.post("/events/available-timeslots")
async def get_available_timeslots(request: TimeslotRequest):
    """
    ดึงข้อมูลช่วงเวลาที่ว่างของ recruiter ที่ระบุในวันที่กำหนด
    แสดงเฉพาะช่วงเวลาว่างในระหว่าง 09:00 - 18:00 โดยแบ่งเป็นช่วงละ 30 นาที
    รองรับทั้ง LINE และ Facebook Messenger
    หมายเหตุ: ตัด validation ออกเพราะ API select-recruiter ได้เช็คแล้ว
    """
    start = timeTest.time()
    print(f"[START] Available timeslots API started at {start:.6f}")
    
    # กำหนดวันที่จะตรวจสอบ
    date = datetime.fromisoformat(request.date).date()
    start_datetime = datetime.combine(date, time(0, 0, 0)).astimezone(timezone.utc)
    end_datetime = datetime.combine(date, time(23, 59, 59)).astimezone(timezone.utc)
    
    time_min = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_max = end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # ดึงข้อมูลกิจกรรมสำหรับ Recruiter ที่ระบุ (ไม่เช็ค validation เพราะเช็คใน API แรกแล้ว)
    t3 = timeTest.time()
    recruiter_email = request.recruiter_email
    recruiter_name = recruiter_email.split('@')[0]  # ใช้ชื่อจาก email เป็น fallback
    recruiter_events = []
    
    try:
        # ดึง token จาก DB
        token_entry = get_token(recruiter_email)
        creds = Credentials(
            token=token_entry.access_token,
            refresh_token=token_entry.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            scopes=SCOPES
        )
        service = build('calendar', 'v3', credentials=creds)
        
        events_result = service.events().list(
            calendarId=recruiter_email,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        recruiter_events = events_result.get('items', [])
        
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ recruiter: {recruiter_email}: {str(e)}")
        # ถ้าเกิด error ก็ให้ recruiter_events เป็น list ว่าง จะได้แสดงทุกช่วงเวลาเป็นว่าง
        recruiter_events = []
    
    print(f"[LOG] get_recruiter_events done in {timeTest.time() - t3:.3f}s")
    
    # หาช่วงเวลาว่าง
    available_timeslots = []
    
    # สร้างช่วงเวลาทุกๆ 30 นาที
    t4 = timeTest.time()
    for hour in range(9, 18):
        for minute in [0, 30]:
            slot_start = datetime.combine(date, time(hour, minute)).astimezone(timezone.utc)
            slot_end = (slot_start + timedelta(minutes=30)).astimezone(timezone.utc)
            
            # แปลงเป็นเวลาท้องถิ่นเพื่อแสดงผล
            local_start = slot_start.astimezone().strftime("%H:%M")
            local_end = slot_end.astimezone().strftime("%H:%M")
            time_slot_key = f"{local_start}-{local_end}"
            
            # ตรวจสอบว่า recruiter ว่างหรือไม่
            if is_available(recruiter_events, slot_start, slot_end):
                available_timeslots.append({
                    "time_slot": time_slot_key,
                    "recruiter": recruiter_name
                })
    
    print(f"[LOG] find_available_time_slots done in {timeTest.time() - t4:.3f}s")
    
    # สร้างรูปแบบวันที่แบบไทย
    thai_date = create_thai_date_label(request.date)
    
    # เตรียมข้อมูลสำหรับปุ่ม quick reply
    slot_items = []
    for i, slot in enumerate(available_timeslots[:12], start=1):
        time_slot = slot["time_slot"]
        # เพิ่มข้อมูลสำหรับปุ่ม (ใช้ช่วงเวลาเป็น label และ text)
        slot_items.append((time_slot, time_slot))

    # สร้างปุ่ม quick reply สำหรับ LINE และ Facebook
    line_items = create_line_quick_reply_items(slot_items, max_items=12, add_back_button=True)
    facebook_items = create_facebook_quick_replies(slot_items, max_items=12, add_back_button=True)

    # สร้างข้อความ
    message_text = f"📅 วันที่ : {thai_date}\n🗓️ กรุณาเลือกช่วงเวลาที่ต้องการ"

    # สร้างข้อความสำหรับ LINE
    line_message = {
        "type": "text",
        "text": message_text,
        "quickReply": {
            "items": line_items
        }
    }
    
    # สร้างข้อความสำหรับ Facebook
    facebook_message = {
        "text": message_text,
        "quick_replies": facebook_items
    }
    
    response = {
        "line_payload": [line_message],
        "facebook_payload": [facebook_message],
        "date": request.date,
        "recruiter_email": recruiter_email,
        "recruiter_name": recruiter_name,
        "available_slots_count": len(available_timeslots)
    }
    
    print(f"[LOG] Available timeslots API done in {timeTest.time() - start:.3f}s")
    
    return JSONResponse(
        content=response,
        headers={
            "Response-Type": "object"
        }
    )

# แปลงวัน iso เป็นวันไทย 
@app.post("/date-convert")
async def date_convert(request: DateConvert):
    thai_date = create_thai_date_label(request.date)
    return {"thai_date": thai_date}

# API 4: สร้างการนัดหมาย 
@app.post("/events/create-bulk")
def create_bulk_events(event_request: BulkEventRequest):
    """สร้างการนัดหมายโดยใช้อีเมลที่ระบุโดยตรง และใช้ name2 ในการตั้งหัวข้อการประชุม (เวอร์ชัน test)"""
    start = timeTest.time()
    thai_date = create_thai_date_label(event_request.date)
    # แมปสถานที่จากภาษาไทยเป็นภาษาอังกฤษ
    location_mapping = {
        "สีลม": "Silom",
        "อโศก": "Asoke", 
        "ภูเก็ต": "Phuket",
        "พัทยา": "Pattaya",
        "สมุย": "Samui",
        "หัวหิน": "Huahin",
        "เชียงใหม่": "Chiangmai"
    }
    
    try:
        # แปลงสถานที่จากภาษาไทยเป็นภาษาอังกฤษ
        english_location = location_mapping.get(event_request.location, event_request.location)
        
        # แปลงเวลาให้เป็นรูปแบบ ISO
        try:
            start_time, end_time = convert_to_iso_format(event_request.date, event_request.time)
        except ValueError as e:
            line_response = {
                "type": "text",
                "text": f"รูปแบบวันที่หรือเวลาไม่ถูกต้อง: {str(e)}"
            }
            facebook_response = {
                "text": f"รูปแบบวันที่หรือเวลาไม่ถูกต้อง: {str(e)}"
            }
            
            return JSONResponse(
                content={
                    "message": "รูปแบบวันที่หรือเวลาไม่ถูกต้อง",
                    "error": str(e),
                    "line_payload": [line_response],
                    "facebook_payload": [facebook_response]
                },
                headers={"Response-Type": "object"}
            )
        
        # ใช้อีเมลและชื่อที่ส่งมาโดยตรง
        user_email = event_request.email
        user_name = event_request.name2
        
        # ตรวจสอบว่าผู้ใช้ได้ยืนยันตัวตนแล้วหรือไม่
        if not is_token_valid(user_email):
            line_response = {
                "type": "text",
                "text": "ไม่สามารถสร้างการนัดหมายได้ เนื่องจากผู้ใช้ยังไม่ได้ยืนยันตัวตน"
            }
            facebook_response = {
                "text": "ไม่สามารถสร้างการนัดหมายได้ เนื่องจากผู้ใช้ยังไม่ได้ยืนยันตัวตน"
            }
            
            return JSONResponse(
                content={
                    "message": "ผู้ใช้ยังไม่ได้ยืนยันตัวตน",
                    "invalid_user": user_email,
                    "line_payload": [line_response],
                    "facebook_payload": [facebook_response]
                },
                headers={"Response-Type": "object"}
            )
            
        # รับ credentials ของผู้ใช้
        token_entry = get_token(user_email)
        creds = Credentials(
            token=token_entry.access_token,
            refresh_token=token_entry.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            scopes=SCOPES
        )
        
        # สร้าง service สำหรับผู้ใช้
        service = build('calendar', 'v3', credentials=creds)
        
        # ตรวจสอบว่ามีกิจกรรมซ้ำซ้อนในช่วงเวลาเดียวกันหรือไม่
        time_min = start_time
        time_max = end_time
        
        # ตรวจสอบปฏิทินของผู้ใช้
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        
        # ถ้ามีกิจกรรมในช่วงเวลาเดียวกัน ให้แจ้งเตือนและยกเลิกการสร้างนัดหมาย
        if events:
            conflict_events = []
            
            # รวบรวมรายการกิจกรรมที่ซ้ำซ้อน
            for event in events:
                conflict_events.append({
                    'title': event.get('summary', 'ไม่มีชื่อ'),
                    'start': event.get('start', {}).get('dateTime', ''),
                    'end': event.get('end', {}).get('dateTime', ''),
                    'calendar_owner': user_email
                })
            
            # สร้าง Line และ Facebook Response สำหรับกรณีที่มีกิจกรรมซ้ำซ้อn
            line_response = {
                "type": "text",
                "text": f"ขออภัย ไม่สามารถทำการสร้างนัดได้เนื่องจากมีกิจกรรมอยู่แล้ว"
            }
            facebook_response = {
                "text": f"ขออภัย ไม่สามารถทำการสร้างนัดได้เนื่องจากมีกิจกรรมอยู่แล้ว"
            }
            
            return JSONResponse(
                content={
                    "message": "มีกิจกรรมซ้ำซ้อนในช่วงเวลาเดียวกัน",
                    "conflict_events": conflict_events,
                    "line_payload": [line_response],
                    "facebook_payload": [facebook_response]
                },
                headers={"Response-Type": "object"}
            )
        
        # เตรียมรายชื่อผู้เข้าร่วมเพิ่มเติม
        additional_attendees = []
        if event_request.attendees:
            additional_attendees = [{'email': email} for email in event_request.attendees]
        
        # กำหนดชื่อหัวข้อตามรูปแบบที่ต้องการ (ใช้ name2)
        event_summary = f"Onsite Interview : K. {user_name} - {english_location}"
        
        # เตรียมข้อมูลกิจกรรม
        event_data = {
            'summary': event_summary,
            'location': english_location,
            'start': {
                'dateTime': start_time,
                'timeZone': 'Asia/Bangkok',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'Asia/Bangkok',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 10}  # แจ้งเตือน 10 นาทีก่อนการประชุม
                ]
            },
            'guestsCanSeeOtherGuests': True,
            'guestsCanModify': False,
            'sendUpdates': 'all'
        }
        
        # ผลลัพธ์การดำเนินการ
        results = []
        
        # สร้างการนัดหมายโดยใช้อีเมลที่ส่งมาเป็น organizer
        try:
            # เพิ่มผู้เข้าร่วม (รวมถึง organizer และผู้เข้าร่วมเพิ่มเติม)
            attendees = [
                {'email': user_email, 'responseStatus': 'accepted', 'organizer': True}
            ] + additional_attendees
            event_data['attendees'] = attendees
            
            # สร้างกิจกรรมในปฏิทิน
            created_event = service.events().insert(
                calendarId="primary",
                body=event_data
            ).execute()
            
            results.append({
                'email': user_email,
                'name': user_name,
                'success': True,
                'message': 'สร้างการนัดหมายสำเร็จ',
                'event_id': created_event['id'],
                'html_link': created_event['htmlLink']
            })
            
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการสร้างการนัดหมาย: {str(e)}")
            results.append({
                'email': user_email,
                'name': user_name,
                'success': False,
                'message': f'เกิดข้อผิดพลาด: {str(e)}'
            })  
            
            # สร้าง Line และ Facebook Response สำหรับกรณีเกิดข้อผิดพลาด
            line_response = {
                "type": "text",
                "text": f"เกิดข้อผิดพลาดในการสร้างการนัดหมาย: {str(e)}"
            }
            facebook_response = {
                "text": f"เกิดข้อผิดพลาดในการสร้างการนัดหมาย: {str(e)}"
            }
            
            print(f"[DEBUG] API done at {timeTest.time() - start:.3f}s")
            return JSONResponse(
                content={
                    "message": "เกิดข้อผิดพลาดในการสร้างการนัดหมาย",
                    "error": str(e),
                    "line_payload": [line_response],
                    "facebook_payload": [facebook_response]
                },
                headers={"Response-Type": "object"}
            )
        
        # สร้าง Line และ Facebook Response สำหรับการสร้างนัดสำเร็จ
        line_response = create_appointment_success_flex_message(
            event_summary, thai_date, event_request.time, user_name, user_email
        )
        
        facebook_response = create_appointment_success_facebook_message(
            event_summary, thai_date, event_request.time, user_name, user_email
        )
        
        # คืนค่าข้อมูลพร้อมกับ Line และ Facebook Response Object
        print(f"[DEBUG] API done at {timeTest.time() - start:.3f}s")
        return JSONResponse(
            content={
                "message": f"ดำเนินการสร้างการนัดหมายสำหรับ K. {user_name} ({user_email})",
                "results": results,
                "line_payload": [line_response],
                "facebook_payload": [facebook_response]
            },
            headers={"Response-Type": "object"}
        )
            
    except Exception as e:
        # สร้าง Line และ Facebook Response สำหรับกรณีเกิดข้อผิดพลาด
        line_response = {
            "type": "text",
            "text": f"เกิดข้อผิดพลาดในการสร้างการนัดหมาย: {str(e)}"
        }
        facebook_response = {
            "text": f"เกิดข้อผิดพลาดในการสร้างการนัดหมาย: {str(e)}"
        }
        
        print(f"[DEBUG] API done at {timeTest.time() - start:.3f}s")
        return JSONResponse(
            content={
                "message": "เกิดข้อผิดพลาดในการสร้างการนัดหมาย",
                "error": str(e),
                "line_payload": [line_response],
                "facebook_payload": [facebook_response]
            },
            headers={"Response-Type": "object"}
        )
    
#========================================= login ===============================================
# Login - ดึงข้อมูลผู้ใช้และยืนยันตัวตน
@app.get("/events/{user_email}")
def get_user_events(
    user_email: str, 
    calendar_id: str = "primary",
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None):
    """ดึงข้อมูลกิจกรรมของผู้ใช้คนเดียว และยืนยันตัวตนหากจำเป็น รองรับทั้ง LINE และ Facebook"""
    # ดึงข้อมูลและยืนยันตัวตนถ้าจำเป็น
    creds_result = get_credentials(user_email)
    print(base_url)
    # ตรวจสอบว่าต้องการการยืนยันตัวตนหรือไม่
    if isinstance(creds_result, dict) and creds_result.get("requires_auth"):
        auth_url = creds_result["auth_url"]
        
        # เข้ารหัส auth_url และ email เพื่อส่งเป็นพารามิเตอร์
        encoded_auth_url = quote_plus(auth_url)
        encoded_email = quote_plus(user_email)
        
        # สร้าง URL ไปยังหน้า redirect ของเรา
        redirect_page_url = f"{base_url}/auth-redirect?auth_url={encoded_auth_url}&email={encoded_email}"
        
        # สร้าง LINE Flex Message
        line_flex_message = {
            "type": "flex",
            "altText": "กรุณาเข้าสู่ระบบ Google Calendar",
            "contents": {
                "type": "bubble",
                "size": "mega",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "md",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": "เข้าสู่ระบบ Google Calendar",
                                    "weight": "bold",
                                    "size": "xl",
                                    "color": "#4285F4",
                                    "align": "center",
                                    "gravity": "center",
                                    "wrap": True
                                }
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "spacing": "sm",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": "อีเมล:",
                                    "size": "sm",
                                    "color": "#999999"
                                },
                                {
                                    "type": "text",
                                    "text": user_email,
                                    "size": "md",
                                    "weight": "bold",
                                    "wrap": True
                                }
                            ]
                        }
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "action": {
                                "type": "uri",
                                "label": "🔗เข้าสู่ระบบกับ Google",
                                "uri": redirect_page_url
                            },
                            "style": "primary",
                            "color": "#4285F4"
                        }
                    ]
                }
            }
        }

        # สร้าง Facebook Button Template
        facebook_button_message = create_facebook_button_template(
            title="กรุณาเข้าสู่ระบบ Google Calendar",
            subtitle=f"อีเมล: {user_email}",
            buttons=[
                {
                    "type": "web_url",
                    "url": redirect_page_url,
                    "title": "🔗เข้าสู่ระบบกับ Google"
                }
            ]
        )
        
        # สร้าง response object พร้อม header ที่ระบุว่าเป็น JSON
        response_data = {
            "email": user_email,
            "is_authenticated": False,
            "auth_required": True,
            "auth_url": auth_url,
            "redirect_url": redirect_page_url,
            "line_payload": [line_flex_message],
            "facebook_payload": [facebook_button_message]
        }
        
        return JSONResponse(
            content=response_data,
            headers={"Response-Type": "object"}
        )
    
    # ถ้ามี credentials แล้ว ส่งข้อความว่าผู้ใช้เข้าสู่ระบบแล้ว
    try:
        # สร้าง LINE Flex Message แจ้งว่าได้เข้าสู่ระบบแล้ว
        line_already_login_message = {
            "type": "flex",
            "altText": "คุณได้ทำการเข้าสู่ระบบแล้ว✅",
            "contents": {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "คุณได้ทำการเข้าสู่ระบบแล้ว✅",
                            "weight": "bold",
                            "size": "lg",
                            "color": "#28a745",
                            "align": "center"
                        },
                        {
                            "type": "text",
                            "text": f"อีเมล: {user_email}",
                            "margin": "md",
                            "align": "center"
                        }
                    ]
                }
            }
        }
        
        # สร้าง Facebook Text Message
        facebook_already_login_message = {
            "text": f"คุณได้ทำการเข้าสู่ระบบแล้ว✅\nอีเมล: {user_email}"
        }
        
        response_data = {
            'email': user_email,
            'is_authenticated': True,
            'message': "คุณได้ทำการเข้าสู่ระบบแล้ว✅",
            'line_payload': [line_already_login_message],
            'facebook_payload': [facebook_already_login_message]
        }
        
        return JSONResponse(
            content=response_data,
            headers={"Response-Type": "object"}
        )
    except Exception as e:
        print(f"เกิดข้อผิดพลาดสำหรับ {user_email}: {str(e)}")
        
        # สร้าง LINE Flex Message สำหรับแสดงข้อผิดพลาด
        line_error_flex_message = {
            "type": "flex",
            "altText": "เกิดข้อผิดพลาด",
            "contents": {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "เกิดข้อผิดพลาด",
                            "weight": "bold",
                            "size": "xl",
                            "color": "#d9534f"
                        },
                        {
                            "type": "text",
                            "text": str(e),
                            "wrap": True,
                            "margin": "md"
                        }
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "action": {
                                "type": "message",
                                "label": "ลองใหม่",
                                "text": f"login {user_email}"
                            },
                            "style": "primary"
                        }
                    ]
                }
            }
        }
        
        # สร้าง Facebook Button Template สำหรับข้อผิดพลาด
        facebook_error_message = {
            "text": f"เกิดข้อผิดพลาด: {str(e)}",
            "quick_replies": [
                {
                    "content_type": "text",
                    "title": "ลองใหม่",
                    "payload": f"login {user_email}"
                }
            ]
        }
        
        error_response = {
            'email': user_email,
            'error': str(e),
            'is_authenticated': False,
            'line_payload': [line_error_flex_message],
            'facebook_payload': [facebook_error_message]
        }
        print(error_response)
        return JSONResponse(
            content=error_response,
            headers={"Response-Type": "object"}
        )

@app.get("/auth-redirect", response_class=HTMLResponse)
async def auth_redirect(request: Request, auth_url: str, email: str = None):
    """หน้าเว็บที่แสดงปุ่มเข้าสู่ระบบ Google โดยไม่มีการ redirect อัตโนมัติ"""
    # ถอดรหัส URL ในกรณีที่มีการเข้ารหัสมา
    decoded_auth_url = unquote_plus(auth_url)
    
    # ส่งค่าตัวแปรไปยัง template
    return templates.TemplateResponse(
        "auth_redirect.html", 
        {
            "request": request,  
            "auth_url": decoded_auth_url,
            "email": email
        }
    )



# =========================================================================================================
@app.post("/test")
def test(request: LocationRequest):
    getPeople = get_people(location=request.location)
    return getPeople

# ======================== ส่วนที่เกี่ยวกับ DB ==================================================================
@app.get("/auto-refresh")
def trigger_auto_refresh():
    """เรียกใช้ auto_refresh_tokens เพื่อทดสอบทันที"""
    from src.utils.auto_refresh_jobs import auto_refresh_tokens
    
    try:
        # เรียกใช้ฟังก์ชันโดยตรง
        auto_refresh_tokens()
        return {"status": "success", "message": "Auto refresh tokens triggered successfully"}
    except Exception as e:
        return {"status": "error", "message": f"Error triggering auto refresh: {str(e)}"}

@app.get("/api/tokens", response_model=List[TokenResponse])
async def read_all_tokens():
    """
    API endpoint สำหรับดึงข้อมูลทั้งหมด
    """
    tokens = get_all_tokens()
    if not tokens:
        return []
    return tokens

@app.get("/api/tokens/{email}", response_model=TokenResponse)
async def read_token(email: str):
    """
    API endpoint สำหรับดึงข้อมูลตามแต่ละ email
    """
    token = get_token(email)
    if token is None:
        raise HTTPException(status_code=404, detail=f"ไม่พบข้อมูลสำหรับ email: {email}")
    return token

# @app.get("/api/emails", response_model=List[EmailResponse])
@app.get("/api/emails", response_model=Dict[str, List[str]])
async def read_all_emails():
    """
    API endpoint สำหรับดึงเฉพาะ email ทั้งหมด
    """
    emails = get_all_emails()
    if not emails:
        return []
    # return emails
    return {"email": emails}

@app.delete("/api/revoke/{user_email}")
def revoke_auth(user_email: str):
    """ยกเลิกการยืนยันตัวตนของผู้ใช้โดยลบข้อมูล token ใน DB"""
    from src.utils.token_db import delete_token
    
    try:
        result = delete_token(user_email)
        if result:
            return {
                "email": user_email,
                "success": True,
                "message": f"ยกเลิกการยืนยันตัวตนสำหรับ {user_email} สำเร็จ"
            }
        else:
            return {
                "email": user_email,
                "success": False,
                "message": f"ไม่พบข้อมูลการยืนยันตัวตนสำหรับ {user_email}"
            }
    except Exception as e:
        return {
            "email": user_email,
            "success": False,
            "message": f"เกิดข้อผิดพลาดในการยกเลิกการยืนยันตัวตน: {str(e)}"
        }
 
@app.post("/api/mock-add-tokens")
def mock_add_tokens():
    """
    สร้างข้อมูลทดสอบ token สำหรับ email จำนวน 50 รายการ
    """
    db = SessionLocal()
    try:
        for i in range(1, 51):
            email = f"user{i:02d}@example.com"
            access_token = f"access_token_{i}"
            refresh_token = f"refresh_token_{i}"
            expiry = datetime.utcnow() + timedelta(days=random.randint(1, 30))

            # ตรวจสอบก่อนว่า email นี้มีอยู่แล้วหรือไม่
            existing = db.query(Token).filter(Token.email == email).first()
            if not existing:
                new_token = Token(
                    email=email,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expiry=expiry,
                    updated_at=datetime.utcnow()
                )
                db.add(new_token)
        db.commit()
        return {"message": "เพิ่ม email mockup แล้ว 50 รายการ"}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()

