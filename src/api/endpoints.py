# Standard library
import os
from datetime import datetime,time, timedelta, timezone
from pathlib import Path
import random
import time as timeTest
import sys
from urllib.parse import quote_plus, unquote_plus
# Third-party libraries
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from typing import Dict, Optional
import logging
import time as timeTest
import holidays

# Local application
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.config import *
from src.utils.func import *
from src.models.schemas import *
import logging
from src.utils.token_db import *
from src.models.token_model import TokenResponse

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
AUTH_PORT = 8080  # พอร์ต redirect
FILE_PATH = os.path.join(os.path.dirname(__file__), '..', '..', os.getenv("FILE_PATH"))
# ปอดการแจ้งเตือน INFO:googleapiclient.discovery_cache:file_cache is only supported with oauth2client<4.0.0
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
base_url = os.environ.get('BASE_URL')
EMAIL_SENDER = os.getenv("EMAIL_to_SEND_MESSAGE")
EMAIL_PASSWORD = os.getenv("PASSWORD_EMAIL")
CLIENT_SECRET_FILE = os.getenv("CLIENT_SECRET_FILE")
logger = logging.getLogger(__name__)


@app.middleware("http")
async def catch_all(request: Request, call_next):
    response = await call_next(request)
    if response.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={"error": "Path not found", "path": str(request.url)}
        )
    return response

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
            return HTMLResponse(f"""
            <html>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #d9534f;">เกิดข้อผิดพลาดในการยืนยันตัวตน</h1>
                    <div style="background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; padding: 15px; margin-bottom: 20px;">
                        <p><strong>อีเมลที่คุณใช้ยืนยันตัวตนไม่ถูกต้อง!</strong></p>
                        <p>คุณกรอกอีเมล <strong>{expected_email}</strong> แต่ยืนยันตัวตนด้วย <strong>{actual_email}</strong></p>
                        <p>กรุณาลองใหม่โดยใช้อีเมลที่ตรงกัน</p>
                    </div>
                    <a href="/events/{expected_email}" style="background-color: #007bff; color: white; padding: 10px 15px; text-decoration: none; border-radius: 4px;">ลองใหม่</a>
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

@app.post("/events/multiple")
def get_multiple_users_events(request: UsersRequest):
    """ดึงข้อมูลกิจกรรมของผู้ใช้หลายคน (เฉพาะผู้ใช้ที่ยืนยันตัวตนแล้ว)"""
    results = []
    users_without_auth = []
    
    # ตรวจสอบผู้ใช้แต่ละคนว่าได้ยืนยันตัวตนแล้วหรือไม่
    for user in request.users:
        if is_token_valid(user.email):
            # ถ้ามี token ที่ใช้งานได้แล้ว ดึงข้อมูลปฏิทิน
            try:
                # ดึง token จาก DB แทนการอ่านไฟล์
                token_entry = get_token(user.email)
                creds = Credentials(
                    token=token_entry.access_token,
                    refresh_token=token_entry.refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    scopes=SCOPES
                )
                
                service = build('calendar', 'v3', credentials=creds)
                
                # ดึง start_time และ end_time จาก request ถ้าไม่มีให้ใช้ default
                start_time_str = request.start_time or "00:00:00"
                end_time_str = request.end_time or "23:59:59"

                # เอา date + time รวมเป็นรูปแบบ ISO
                time_min = f"{request.start_date}T{start_time_str}+07:00" if request.start_date else datetime.utcnow().isoformat() + "Z"
                time_max = f"{request.end_date}T{end_time_str}+07:00" if request.end_date else (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"

                print(f"กำลังดึงข้อมูลสำหรับ {user.email} จาก {time_min} ถึง {time_max}")
                
                # ดึงข้อมูลกิจกรรม
                events_result = service.events().list(
                    calendarId=user.calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                print(f"พบ {len(events)} กิจกรรมสำหรับ {user.email}")
                
                # แปลงข้อมูลให้เหมาะสม
                formatted_events = []
                for event in events:
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    end = event['end'].get('dateTime', event['end'].get('date'))
                    
                    formatted_events.append({
                        'id': event['id'],
                        'summary': event.get('summary', 'ไม่มีชื่อกิจกรรม'),
                        'start': start,
                        'end': end,
                        'creator': event.get('creator', {}),
                        'attendees': event.get('attendees', []),
                        'status': event.get('status', 'confirmed'),
                        'location': event.get('location', ''),
                        'description': event.get('description', '')
                    })
                
                results.append({
                    'email': user.email,
                    'calendar_id': user.calendar_id,
                    'events': formatted_events,
                    'is_authenticated': True
                })
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ {user.email}: {str(e)}")
                results.append({
                    'email': user.email,
                    'calendar_id': user.calendar_id,
                    'events': [],
                    'error': str(e),
                    'is_authenticated': True
                })
        else:
            # ถ้ายังไม่มี token ที่ใช้งานได้
            users_without_auth.append(user.email)
            results.append({
                'email': user.email,
                'calendar_id': user.calendar_id,
                'events': [],
                'error': 'ผู้ใช้ยังไม่ได้ยืนยันตัวตน กรุณาใช้ /events/{email} ก่อน',
                'is_authenticated': False
            })
    
    # สร้าง response
    response = {"results": results}
    
    if users_without_auth:
        response["users_without_auth"] = users_without_auth
        response["message"] = f"ผู้ใช้ต่อไปนี้ยังไม่ได้ยืนยันตัวตน ใช้ /events/<email> เพื่อยืนยันตัวตน: {', '.join(users_without_auth)}"
    
    return JSONResponse(content=response)

@app.post("/events/multipleMR")
def get_multiple_users_events(request: ManagerRecruiter):
    """ดึงข้อมูลกิจกรรมของผู้ใช้หลายคน (เฉพาะผู้ใช้ที่ยืนยันตัวตนแล้ว) แยกตามประเภท M และ R"""

    results_m = []
    results_r = []
    users_without_auth_m = []
    users_without_auth_r = []
    
    # ใช้ฟังก์ชัน get_people เพื่อรับรายชื่ออีเมลผู้ใช้แยกตามประเภท M และ R
    users_dict = get_people(
        file_path=FILE_PATH,
        location=request.location,
        english_min=request.english_min,
        exp_kind=request.exp_kind,
        age_key=request.age_key
    )
    
    # ประมวลผลสำหรับผู้ใช้ประเภท M
    for user_info in users_dict['M']:
        email = user_info["Email"]
        name = user_info["Name"]
        location = user_info["Location"]
        # ใช้อีเมลเป็น calendar_id ถ้าไม่มีการระบุเพิ่มเติม
        calendar_id = email
        
        if is_token_valid(email):
        # ถ้ามี token ที่ใช้งานได้แล้ว ดึงข้อมูลปฏิทิน
            try:
                # ดึง token จาก DB แทนการอ่านไฟล์
                token_entry = get_token(email)
                creds = Credentials(
                    token=token_entry.access_token,
                    refresh_token=token_entry.refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    scopes=SCOPES
                )
          
                service = build('calendar', 'v3', credentials=creds)
                
                # กำหนดช่วงเวลาในการดึงข้อมูล
                time_min = request.start_date + "T00:00:00Z" if request.start_date else datetime.utcnow().isoformat() + "Z"
                time_max = request.end_date + "T23:59:59Z" if request.end_date else (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"
                
                print(f"กำลังดึงข้อมูลสำหรับ M: {email} ({name}) จาก {time_min} ถึง {time_max}")
                
                # ดึงข้อมูลกิจกรรม
                events_result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                print(f"พบ {len(events)} กิจกรรมสำหรับ M: {email}")
                
                # แปลงข้อมูลให้เหมาะสม
                formatted_events = []
                for event in events:
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    end = event['end'].get('dateTime', event['end'].get('date'))
                    
                    formatted_events.append({
                        'id': event['id'],
                        'summary': event.get('summary', 'ไม่มีชื่อกิจกรรม'),
                        'start': start,
                        'end': end,
                        'creator': event.get('creator', {}),
                        'attendees': event.get('attendees', []),
                        'status': event.get('status', 'confirmed'),
                        'location': event.get('location', ''),
                        'description': event.get('description', '')
                    })
                
                results_m.append({
                    'email': email,
                    'name': name,
                    'location': location,
                    'calendar_id': calendar_id,
                    'events': formatted_events,
                    'is_authenticated': True,
                    'type': 'M'
                })
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ M: {email}: {str(e)}")
                results_m.append({
                    'email': email,
                    'name': name,
                    'location': location,
                    'calendar_id': calendar_id,
                    'events': [],
                    'error': str(e),
                    'is_authenticated': True,
                    'type': 'M'
                })
        else:
            # ถ้ายังไม่มี token ที่ใช้งานได้
            users_without_auth_m.append(email)
            results_m.append({
                'email': email,
                'name': name,
                'location': location,
                'calendar_id': calendar_id,
                'events': [],
                'error': 'ผู้ใช้ยังไม่ได้ยืนยันตัวตน กรุณาใช้ /events/{email} ก่อน',
                'is_authenticated': False,
                'type': 'M'
            })
    
    # ประมวลผลสำหรับผู้ใช้ประเภท R
    for user_info in users_dict['R']:
        email = user_info["Email"]
        name = user_info["Name"]
        location = user_info["Location"]
        # ใช้อีเมลเป็น calendar_id ถ้าไม่มีการระบุเพิ่มเติม
        calendar_id = email
        
        if is_token_valid(email):
        # ถ้ามี token ที่ใช้งานได้แล้ว ดึงข้อมูลปฏิทิน
            try:
                # ดึง token จาก DB แทนการอ่านไฟล์
                token_entry = get_token(email)
                creds = Credentials(
                    token=token_entry.access_token,
                    refresh_token=token_entry.refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    scopes=SCOPES
                )
                
                service = build('calendar', 'v3', credentials=creds)
                
                # กำหนดช่วงเวลาในการดึงข้อมูล
                time_min = request.start_date + "T00:00:00Z" if request.start_date else datetime.utcnow().isoformat() + "Z"
                time_max = request.end_date + "T23:59:59Z" if request.end_date else (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"
                
                print(f"กำลังดึงข้อมูลสำหรับ R: {email} ({name}) จาก {time_min} ถึง {time_max}")
                
                # ดึงข้อมูลกิจกรรม
                events_result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                print(f"พบ {len(events)} กิจกรรมสำหรับ R: {email}")
                
                # แปลงข้อมูลให้เหมาะสม
                formatted_events = []
                for event in events:
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    end = event['end'].get('dateTime', event['end'].get('date'))
                    
                    formatted_events.append({
                        'id': event['id'],
                        'summary': event.get('summary', 'ไม่มีชื่อกิจกรรม'),
                        'start': start,
                        'end': end,
                        'creator': event.get('creator', {}),
                        'attendees': event.get('attendees', []),
                        'status': event.get('status', 'confirmed'),
                        'location': event.get('location', ''),
                        'description': event.get('description', '')
                    })
                
                results_r.append({
                    'email': email,
                    'name': name,
                    'location': location,
                    'calendar_id': calendar_id,
                    'events': formatted_events,
                    'is_authenticated': True,
                    'type': 'R'
                })
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ R: {email}: {str(e)}")
                results_r.append({
                    'email': email,
                    'name': name,
                    'location': location,
                    'calendar_id': calendar_id,
                    'events': [],
                    'error': str(e),
                    'is_authenticated': True,
                    'type': 'R'
                })
        else:
            # ถ้ายังไม่มี token ที่ใช้งานได้
            users_without_auth_r.append(email)
            results_r.append({
                'email': email,
                'name': name,
                'location': location,
                'calendar_id': calendar_id,
                'events': [],
                'error': 'ผู้ใช้ยังไม่ได้ยืนยันตัวตน กรุณาใช้ /events/{email} ก่อน',
                'is_authenticated': False,
                'type': 'R'
            })
    
    # สร้าง response
    response = {
        "manager": results_m,
        "recruiter": results_r
    }
    
    # ข้อความแจ้งเตือนผู้ใช้ที่ยังไม่ได้ยืนยันตัวตน
    if users_without_auth_m:
        response["users_without_auth_manager"] = users_without_auth_m
    
    if users_without_auth_r:
        response["users_without_auth_recruiter"] = users_without_auth_r
    
    if users_without_auth_m or users_without_auth_r:
        all_without_auth = users_without_auth_m + users_without_auth_r
        response["message"] = f"ผู้ใช้ต่อไปนี้ยังไม่ได้ยืนยันตัวตน ใช้ /events/<email> เพื่อยืนยันตัวตน: {', '.join(all_without_auth)}"
    
    return JSONResponse(content=response)
  
@app.post("/getManagerRecruiter")
def get_multiple_users_events(body: getManagerRecruiter):
    try:
        people = get_people(
            file_path=FILE_PATH,          
            location=body.location,
            english_min=body.english_min,
            exp_kind=body.exp_kind,
            age_key=body.age_key
        )
        return {
            # "request": body.model_dump(),   
            "people":  people               
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/events/availableMR")
def get_available_time_slots(request: ManagerRecruiter):
    """
    ดึงข้อมูลเวลาว่างที่ตรงกันระหว่าง Manager และ Recruiter
    แสดงเฉพาะช่วงเวลาว่างในระหว่าง 09:00 - 18:00 โดยแบ่งเป็นช่วงละ 30 นาที
    แสดงผลเรียงตามเวลา โดยแต่ละช่วงเวลาจะแสดงคู่ที่ว่างทั้งหมด
    สามารถกำหนดระยะเวลา (time_period) เพื่อแสดงวันที่มีเวลาว่างตามจำนวนวันที่ต้องการ
    """
    # ใช้ฟังก์ชัน get_people เพื่อรับรายชื่ออีเมลผู้ใช้แยกตามประเภท M และ R
    users_dict = get_people(
        file_path=str(FILE_PATH),
        location=request.location,
        english_min=request.english_min,
        exp_kind=request.exp_kind,
        age_key=request.age_key
    )
    
    # ตรวจสอบว่ามีผู้ใช้ในทั้ง 2 กลุ่มหรือไม่
    if not users_dict['M'] or not users_dict['R']:
        return JSONResponse(content={
            "available_time_slots": [],
            "line_summary": "",
            "message": "ไม่พบผู้ใช้ที่ตรงตามเงื่อนไขที่กำหนด"
        })
    
    # กำหนดเวลาเริ่มต้น
    if request.start_date:
        start_datetime = datetime.fromisoformat(request.start_date).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start_datetime = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    time_min = start_datetime.strftime("%Y-%m-%dT%H:%M:%S+07:00")  # ปรับเป็นเวลาไทย
    
    # กำหนดช่วงเวลาในการดึงข้อมูล โดยใช้ time_period แทน end_date
    if request.time_period:
        days_to_check = max(30, int(request.time_period) * 3)
        end_datetime = start_datetime + timedelta(days=days_to_check)
    elif request.end_date:
        end_datetime = datetime.fromisoformat(request.end_date).replace(hour=23, minute=59, second=59)
    else:
        days_to_check = 7
        end_datetime = start_datetime + timedelta(days=days_to_check)
    
    time_max = end_datetime.strftime("%Y-%m-%dT%H:%M:%S+07:00")  # ปรับเป็นเวลาไทย
    
    print(f"ช่วงเวลาในการตรวจสอบ: {time_min} ถึง {time_max}")
    
    # สร้างรายการวันที่จะตรวจสอบ (ไม่รวมวันหยุดถ้า include_holidays=False)
    years_to_check = list(range(start_datetime.year, end_datetime.year + 1))
    THAI_HOLIDAYS = holidays.Thailand(years=years_to_check)
    
    date_list = []
    current_date = start_datetime.date()
    while current_date <= end_datetime.date():
        is_weekend = current_date.weekday() >= 5  # เสาร์=5, อาทิตย์=6
        is_holiday = current_date in THAI_HOLIDAYS
       

        if not is_weekend and (request.include_holidays or not is_holiday):
            date_list.append(current_date)
        
        current_date += timedelta(days=1)
    
    if not date_list:
        return JSONResponse(content={
            "available_time_slots": [],
            "line_summary": "",
            "message": "ไม่มีวันทำงานในช่วงเวลาที่กำหนด"
        })
    
    
    # ดึงข้อมูลกิจกรรมสำหรับ Manager
    managers_events = {}
    for user_info in users_dict['M']:
        email = user_info["Email"]
        name = user_info["Name"]
        calendar_id = email
        
        if is_token_valid(email):
            try:
                # ดึง token จาก DB
                token_entry = get_token(email)
                creds = Credentials(
                    token=token_entry.access_token,
                    refresh_token=token_entry.refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    scopes=SCOPES
                )
                
                service = build('calendar', 'v3', credentials=creds)
                
                print(f"กำลังดึงข้อมูลสำหรับ M: {email} ({name}) จาก {time_min} ถึง {time_max}")
                
                events_result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                print(f"พบ {len(events)} กิจกรรมสำหรับ M: {email}")
                
                # เก็บข้อมูลกิจกรรม
                managers_events[email] = {
                    'name': name,
                    'events': events
                }
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ M: {email}: {str(e)}")
        else:
            print(f"ผู้ใช้ {email} ยังไม่ได้ยืนยันตัวตน")
    
    # ดึงข้อมูลกิจกรรมสำหรับ Recruiter
    recruiters_events = {}
    for user_info in users_dict['R']:
        email = user_info["Email"]
        name = user_info["Name"]
        calendar_id = email
        
        if is_token_valid(email):
            try:
                # ดึง token จาก DB
                
                token_entry = get_token(email)
                creds = Credentials(
                    token=token_entry.access_token,
                    refresh_token=token_entry.refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    scopes=SCOPES
                )
                events = events_result.get('items', [])
                service = build('calendar', 'v3', credentials=creds)
                print(f"กำลังดึงข้อมูลสำหรับ R: {email} ({name}) จาก {time_min} ถึง {time_max}")
                
                events_result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                endtime = timeTest.time()
                
                print(f"พบ {len(events)} กิจกรรมสำหรับ R: {email}")
                
                # เก็บข้อมูลกิจกรรม
                recruiters_events[email] = {
                    'name': name,
                    'events': events
                }
                
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ R: {email}: {str(e)}")
            
          
            
        else:
            print(f"ผู้ใช้ {email} ยังไม่ได้ยืนยันตัวตน")
    
    # ตรวจสอบว่ามีข้อมูลผู้ใช้ที่ยืนยันตัวตนแล้วหรือไม่
    if not managers_events or not recruiters_events:
        return JSONResponse(content={
            "available_time_slots": [],
            "line_summary": "",
            "message": "ไม่มีผู้ใช้ที่ยืนยันตัวตนแล้วเพียงพอสำหรับการจับคู่"
        })
    
    # เก็บช่วงเวลาว่างตามวันที่
    # โครงสร้าง: time_based_results[date][time_slot] = [{คู่ที่ว่าง}]
    time_based_results = {}
    
    # ปรับเวลาให้เป็นโซนเวลาไทย (UTC+7)
    TH_TIMEZONE = timezone(timedelta(hours=7))
    
    # แก้ไขฟังก์ชัน is_available เพื่อดูว่าช่วงเวลานั้นว่างหรือไม่
    def is_available(events, start_time, end_time):
        """ตรวจสอบว่าช่วงเวลาที่กำหนดว่างหรือไม่"""
        for event in events:
            # ตรวจสอบว่า event มี start และ end หรือไม่
            if 'start' not in event or 'end' not in event:
                continue

            # ดึงเวลาเริ่มต้นและสิ้นสุดของกิจกรรม
            event_start_str = event['start'].get('dateTime', event['start'].get('date'))
            event_end_str = event['end'].get('dateTime', event['end'].get('date'))
            
            if not event_start_str or not event_end_str:
                continue
                
            try:
                # แปลงเป็น datetime object
                if 'T' in event_start_str:  # เป็นรูปแบบ dateTime
                    if event_start_str.endswith('Z'):
                        event_start = datetime.fromisoformat(event_start_str.replace('Z', '+00:00'))
                    else:
                        event_start = datetime.fromisoformat(event_start_str)
                else:  # เป็นรูปแบบ date
                    event_start = datetime.strptime(event_start_str, '%Y-%m-%d').replace(tzinfo=TH_TIMEZONE)
                    
                if 'T' in event_end_str:  # เป็นรูปแบบ dateTime
                    if event_end_str.endswith('Z'):
                        event_end = datetime.fromisoformat(event_end_str.replace('Z', '+00:00'))
                    else:
                        event_end = datetime.fromisoformat(event_end_str)
                else:  # เป็นรูปแบบ date
                    event_end = datetime.strptime(event_end_str, '%Y-%m-%d').replace(tzinfo=TH_TIMEZONE)
                
                # ตรวจสอบว่าซ้อนทับกับช่วงเวลาที่ต้องการหรือไม่
                if (start_time < event_end and end_time > event_start):
                    return False  # ไม่ว่าง
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการแปลงเวลา: {e}, event_start: {event_start_str}, event_end: {event_end_str}")
                continue
                
        return True  # ว่าง
    
    # ตรวจสอบเวลาว่างสำหรับทุกวัน
    for date in date_list:
        time_based_results[date] = {}
        
        # สร้างช่วงเวลาทุกๆ 30 นาที
        time_slots = []
        for hour in range(9, 18):  # 9:00 AM - 5:30 PM
            for minute in [0, 30]:
                slot_start = datetime.combine(date, time(hour, minute)).replace(tzinfo=TH_TIMEZONE)
                slot_end = (slot_start + timedelta(minutes=30)).replace(tzinfo=TH_TIMEZONE)
                time_slots.append((slot_start, slot_end))
        
        # ตรวจสอบแต่ละช่วงเวลา
        for slot_start, slot_end in time_slots:
            # แปลงเป็นเวลาท้องถิ่นเพื่อแสดงผล
            local_start = slot_start.strftime("%H:%M")
            local_end = slot_end.strftime("%H:%M")
            time_slot_key = f"{local_start}-{local_end}"
            
            # เก็บคู่ที่ว่างในช่วงเวลานี้
            available_pairs = []
            
            # ตรวจสอบทุกคู่ M-R
            for manager_email, manager_data in managers_events.items():
                manager_name = manager_data['name']
                manager_events = manager_data['events']
                
                for recruiter_email, recruiter_data in recruiters_events.items():
                    recruiter_name = recruiter_data['name']
                    recruiter_events = recruiter_data['events']
                    
                    # ตรวจสอบว่าทั้งคู่ว่างหรือไม่
                    manager_is_available = is_available(manager_events, slot_start, slot_end)
                    recruiter_is_available = is_available(recruiter_events, slot_start, slot_end)
                    
                    if manager_is_available and recruiter_is_available:
                        available_pairs.append({
                            "pair": f"{manager_name}-{recruiter_name}",
                            "manager": {
                                "email": manager_email,
                                "name": manager_name
                            },
                            "recruiter": {
                                "email": recruiter_email,
                                "name": recruiter_name
                            }
                        })
            
            # เก็บผลลัพธ์เฉพาะช่วงเวลาที่มีคู่ว่างอย่างน้อย 1 คู่
            if available_pairs:
                time_based_results[date][time_slot_key] = available_pairs
    
    # ตรวจสอบว่ามีเวลาว่างหรือไม่
    empty_days = []
    for date, time_slots in time_based_results.items():
        if not time_slots:  # ถ้าวันนี้ไม่มีช่วงเวลาว่าง
            empty_days.append(date)
    
    # ลบวันที่ไม่มีช่วงเวลาว่าง
    for date in empty_days:
        del time_based_results[date]
    
    # เตรียมข้อมูลสำหรับแสดงผล
    line_friendly_results = []
    required_days = int(request.time_period) if request.time_period else (7 if not request.end_date else None)
    
    # ถ้าใช้ time_period ให้ค้นหาวันที่ว่างตามจำนวนที่กำหนด
    if required_days is not None:
        # รวบรวมทุกวันที่มีเวลาว่าง
        available_dates = []
        for date, time_slots in time_based_results.items():
            if time_slots:  # ถ้าวันนี้มีช่วงเวลาว่าง
                available_dates.append(date)
        
        # เรียงลำดับวันที่
        available_dates.sort()
        
        # เลือกเฉพาะ N วันแรกตาม required_days
        selected_dates = available_dates[:required_days] if available_dates else []
        
        # สร้างผลลัพธ์จากวันที่เลือก
        for date in selected_dates:
            date_str = date.strftime("%Y-%m-%d")
            
            date_data = {
                "date": date_str,
                "time_slots": []
            }
            
            for time_slot, pairs in time_based_results[date].items():
                # สร้างข้อความสำหรับแสดงคู่ที่ว่าง
                pair_names = [p["pair"] for p in pairs]
                
                # เพิ่มข้อมูลช่วงเวลา
                date_data["time_slots"].append({
                    "time": time_slot,
                    "available_pairs": pair_names,
                    "pair_details": pairs
                })
            
            # เรียงลำดับตามช่วงเวลา
            date_data["time_slots"].sort(key=lambda x: x["time"])
            
            line_friendly_results.append(date_data)
    else:
        # สร้างผลลัพธ์จากทุกวันที่มี
        for date, time_slots in time_based_results.items():
            if not time_slots:  # ข้ามวันที่ไม่มีเวลาว่าง
                continue
                
            date_str = date.strftime("%Y-%m-%d")
            
            date_data = {
                "date": date_str,
                "time_slots": []
            }
            
            for time_slot, pairs in time_slots.items():
                # สร้างข้อความสำหรับแสดงคู่ที่ว่าง
                pair_names = [p["pair"] for p in pairs]
                
                # เพิ่มข้อมูลช่วงเวลา
                date_data["time_slots"].append({
                    "time": time_slot,
                    "available_pairs": pair_names,
                    "pair_details": pairs
                })
            
            # เรียงลำดับตามช่วงเวลา
            date_data["time_slots"].sort(key=lambda x: x["time"])
            
            line_friendly_results.append(date_data)

    # เรียงผลลัพธ์ตามวันที่
    line_friendly_results.sort(key=lambda x: x["date"])
    
    # สร้างข้อความสรุปสำหรับ LINE
    line_summary = []
    
    if not line_friendly_results:
        return JSONResponse(content={
            "available_time_slots": [],
            "line_summary": "",
            "message": "ไม่พบช่วงเวลาว่างที่ตรงกันในช่วงเวลาที่กำหนด"
        })
    
    for date_data in line_friendly_results:
        line_summary.append(f"วันที่ {date_data['date']}")
        
        for slot in date_data["time_slots"]:
            time_str = slot["time"]
            pairs_str = ", ".join(slot["available_pairs"])
            line_summary.append(f"เวลา {time_str} มีคู่ว่าง: {pairs_str}")
        
        line_summary.append("------------------------")
    
    # สร้าง response
    response = {
        "available_time_slots": line_friendly_results,
        "line_summary": "\n".join(line_summary)
    }
    
    return JSONResponse(content=response)

#================================================API appointment =============================================
# API 1: ดึงวัน
@app.post("/events/available-dates")
def get_available_dates(request: ManagerRecruiter2):
    """
    ดึงข้อมูลวันที่มีเวลาว่างตรงกันระหว่าง Manager และ Recruiter
    แสดงวันที่มีคู่ว่างให้ครบ 7 วัน โดยเว้นวันเสาร์-อาทิตย์
    """
    start = timeTest.time()
    print(f"[START] API started at {start:.6f}")
    # ใช้ฟังก์ชัน get_people เพื่อรับรายชื่ออีเมลผู้ใช้แยกตามประเภท M และ R
    t1 = timeTest.time()
    users_dict = get_people(
        file_path=str(FILE_PATH),
        location=request.location,
        english_min=request.english_min,
        exp_kind=request.exp_kind,
        age_key=request.age_key
    )
    print(f"[LOG] get_people done in {timeTest.time() - t1:.3f}s")
    # กำหนดเวลาเริ่มต้นเป็นวันที่ปัจจุบันเสมอ
    start_datetime = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # กำหนดช่วงเวลาในการดึงข้อมูล - ค้นหาไปข้างหน้าอีก 30 วัน เพื่อให้มีโอกาสเจอวันที่ว่างครบ 7 วัน
    end_datetime = start_datetime + timedelta(days=20)
    
    time_min = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_max = end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    years_to_check = list(range(start_datetime.year, end_datetime.year + 1))
    THAI_HOLIDAYS = holidays.Thailand(years=years_to_check)
    
    # สร้างรายการวันทำการที่จะตรวจสอบ (ไม่รวมวันเสาร์-อาทิตย์และวันหยุดนักขัตฤกษ์)
    date_list = []
    current_date = start_datetime.date()
    t2 = timeTest.time()
    while current_date <= end_datetime.date():
        is_weekend = current_date.weekday() >= 5  # เสาร์=5, อาทิตย์=6
        is_holiday = current_date in THAI_HOLIDAYS
        
        # กำหนดให้ include_holidays เป็น true เสมอ
        include_holidays = True
        
        if not is_weekend and (include_holidays or not is_holiday):
            date_list.append(current_date)
        
        current_date += timedelta(days=1)
    print(f"[LOG] building date_list done in {timeTest.time() - t2:.3f}s")
    # ดึงข้อมูลกิจกรรมสำหรับ Manager และ Recruiter
    managers_events = {}
    t3 = timeTest.time()
    for user_info in users_dict['M']:
        email = user_info["Email"]
        name = user_info["Name"]
        calendar_id = email
        
        if is_token_valid(email):
            try:
                
                # ดึง token จาก DB
                token_entry = get_token(email)
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
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                
                # เก็บข้อมูลกิจกรรม
                managers_events[email] = {
                    'name': name,
                    'events': events
                }
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ M: {email}: {str(e)}")
        else:
            print(f"ผู้ใช้ {email} ยังไม่ได้ยืนยันตัวตน")
    print(f"[LOG] Fetched all Manager events in {timeTest.time() - t3:.3f}s")
    
    recruiters_events = {}
    t4 = timeTest.time()
    for user_info in users_dict['R']:
        email = user_info["Email"]
        name = user_info["Name"]
        calendar_id = email
        
        if is_token_valid(email):
            try:
                token_entry = get_token(email)
                creds = Credentials(
                    token=token_entry.access_token,
                    refresh_token=token_entry.refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    scopes=SCOPES
                )
                events = events_result.get('items', [])
                service = build('calendar', 'v3', credentials=creds)
                
                events_result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                
                # เก็บข้อมูลกิจกรรม
                recruiters_events[email] = {
                    'name': name,
                    'events': events
                }
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ R: {email}: {str(e)}")
        else:
            print(f"ผู้ใช้ {email} ยังไม่ได้ยืนยันตัวตน")
    print(f"[LOG] Fetched all Recruiter events in {timeTest.time() - t4:.3f}s")
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
                for manager_email, manager_data in managers_events.items():
                    if has_available_slot:
                        break
                        
                    manager_events = manager_data['events']
                    
                    for recruiter_email, recruiter_data in recruiters_events.items():
                        recruiter_events = recruiter_data['events']
                        
                        # ตรวจสอบว่าทั้งคู่ว่างหรือไม่
                        manager_is_available = is_available(manager_events, slot_start, slot_end)
                        recruiter_is_available = is_available(recruiter_events, slot_start, slot_end)
                        
                        if manager_is_available and recruiter_is_available:
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
    # สร้างปุ่ม quick reply สำหรับวันที่ที่มีคู่ว่าง
    items = []
    for date_str in available_dates:
        try:
            date_obj = datetime.fromisoformat(date_str)
            thai_year = date_obj.year + 543  # แปลงปี ค.ศ. เป็น พ.ศ.
            thai_date = f"{date_obj.day}/{date_obj.month}/{thai_year}"
            formatted_date = date_str 
            items.append({
                "type": "action",
                "action": {
                    "type": "message",
                    "label": thai_date,
                    "text": formatted_date
                }
            })
        except ValueError:
            pass
    
    # สร้างข้อความ
    line_message = {
        "type": "text",
        "text": "กรุณาเลือกวันที่ต้องการนัดประชุม",
        "quickReply": {
            "items": items[:13]  # จำกัดที่ 13 รายการตามข้อจำกัดของ Line
        }
    }
    
    # สร้าง response ในรูปแบบของ LINE Payload
    if not items:
        line_message = {
            "type": "text",
            "text": "ไม่พบวันที่ว่างในระบบ กรุณาติดต่อผู้ดูแลระบบ"
        }
    
    response = {
        "line_payload": [line_message],
        "available_dates": available_dates  # เก็บข้อมูลเดิมด้วย
    }
    print(f"[DEBUG] API done at {timeTest.time() - start:.3f}s")
    # ส่ง response กลับพร้อม header
    return JSONResponse(
        content=response,
        headers={"Response-Type": "object"}
    )
# API 2: ดึงช่วงเวลาและคู่ในวันที่เลือก
@app.post("/events/available-timeslots")
def get_available_timeslots(request: DateRequest):
    """
    ดึงข้อมูลช่วงเวลาที่ว่างในวันที่ระบุ
    แสดงเฉพาะช่วงเวลาว่างในระหว่าง 09:00 - 18:00 โดยแบ่งเป็นช่วงละ 30 นาที
    """
    start = timeTest.time()
    print(f"[START] API started at {start:.6f}")
    # ใช้ฟังก์ชัน get_people เพื่อรับรายชื่ออีเมลผู้ใช้แยกตามประเภท M และ R
    t1 = timeTest.time()
    users_dict = get_people(
        file_path=str(FILE_PATH),
        location=request.location,
        english_min=request.english_min,
        exp_kind=request.exp_kind,
        age_key=request.age_key
    )
    print(f"[LOG] get_people done in {timeTest.time() - t1:.3f}s")
    # กำหนดวันที่จะตรวจสอบ
    date = datetime.fromisoformat(request.date).date()
    start_datetime = datetime.combine(date, time(0, 0, 0)).astimezone(timezone.utc)
    end_datetime = datetime.combine(date, time(23, 59, 59)).astimezone(timezone.utc)
    
    time_min = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_max = end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # ดึงข้อมูลกิจกรรมสำหรับ Manager และ Recruiter
    t2 = timeTest.time()
    managers_events = {}
    for user_info in users_dict['M']:
        email = user_info["Email"]
        name = user_info["Name"]
        calendar_id = email
        
        if is_token_valid(email):
            try:
                # ดึง token จาก DB
                token_entry = get_token(email)
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
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                
                # เก็บข้อมูลกิจกรรม
                managers_events[email] = {
                    'name': name,
                    'events': events
                }
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ M: {email}: {str(e)}")
        else:
            print(f"ผู้ใช้ {email} ยังไม่ได้ยืนยันตัวตน")
    print(f"[LOG] get_managers_events done in {timeTest.time() - t2:.3f}s")
    
    t3 = timeTest.time()
    recruiters_events = {}
    for user_info in users_dict['R']:
        email = user_info["Email"]
        name = user_info["Name"]
        calendar_id = email
        
        if is_token_valid(email):
            try:
                # ดึง token จาก DB
                token_entry = get_token(email)
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
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                
                # เก็บข้อมูลกิจกรรม
                recruiters_events[email] = {
                    'name': name,
                    'events': events
                }
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ R: {email}: {str(e)}")
        else:
            print(f"ผู้ใช้ {email} ยังไม่ได้ยืนยันตัวตน")
    print(f"[LOG] get_recruiters_events done in {timeTest.time() - t3:.3f}s")
    # เก็บช่วงเวลาว่างและนับจำนวนคู่ที่ว่าง
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
            
            # ตรวจสอบคู่ที่ว่าง
            available_pairs_count = 0
            available_pairs = []
            
            for manager_email, manager_data in managers_events.items():
                manager_events = manager_data['events']
                manager_name = manager_data['name']
                
                for recruiter_email, recruiter_data in recruiters_events.items():
                    recruiter_events = recruiter_data['events']
                    recruiter_name = recruiter_data['name']
                    
                    # ตรวจสอบว่าทั้งคู่ว่างหรือไม่
                    manager_is_available = is_available(manager_events, slot_start, slot_end)
                    recruiter_is_available = is_available(recruiter_events, slot_start, slot_end)
                    
                    if manager_is_available and recruiter_is_available:
                        available_pairs_count += 1
                        # เพิ่มข้อมูลคู่ที่ว่าง
                        available_pairs.append({
                            "pair": f"{manager_name}-{recruiter_name}"
                        })
            
            # เก็บข้อมูลช่วงเวลาที่มีคู่ว่างอย่างน้อย 1 คู่
            if available_pairs_count > 0:
                available_timeslots.append({
                    "time_slot": time_slot_key,
                    "available_pairs_count": available_pairs_count,
                    "available_pairs": available_pairs
                })
    print(f"[LOG] find_available_time_slots done in {timeTest.time() - t4:.3f}s")            
    print("อ่ะ ตรงนี้ๆๆ")
    print(available_timeslots)    
   # แปลงข้อมูลเพื่อสร้างข้อความและปุ่มสำหรับ LINE
    slot_texts = []
    items = []
    
    # สร้างรูปแบบวันที่แบบไทย
    date_obj = datetime.fromisoformat(request.date)
    thai_year = date_obj.year + 543
    selected_date = f"{date_obj.day}/{date_obj.month}/{thai_year}"

    for i, slot in enumerate(available_timeslots[:12], start=1):
        time_slot = slot["time_slot"]
        pairs_text = "\n   " + "\n   ".join([f"👥{pair['pair']}" for pair in slot["available_pairs"]])
        slot_text = f"{i}. เวลา {time_slot}{pairs_text}"
        slot_texts.append(slot_text)
        
        # สร้างปุ่ม quick reply
        items.append({
            "type": "action",
            "action": {
                "type": "message",
                "label": f"({i})",
                "text": time_slot
            }
        })
    
    # เพิ่มปุ่ม 'ย้อนกลับ'
    items.append({
        "type": "action",
        "action": {
            "type": "message",
            "label": "ย้อนกลับ",
            "text": "ย้อนกลับ"
        }
    })
    
    # สร้างข้อความ
    message_text = f"กรุณาเลือกช่วงเวลาที่ต้องการ:\nวันที่ : {selected_date}\n" + "\n".join(slot_texts)
    
    line_message = {
        "type": "text",
        "text": message_text,
        "quickReply": {
            "items": items
        }
    }
    
    response = {
        "line_payload": [line_message],
        "date": request.date,
        "available_timeslots": available_timeslots
    }
    print(f"[LOG] API done at {timeTest.time() - start:.3f}s")
    return JSONResponse(
        content=response,
        headers={"Response-Type": "object"}
    )
# API 3: ดึงรายละเอียดของคู่ที่ว่างในช่วงเวลาที่เลือก
@app.post("/events/available-pairs")
def get_available_pairs(request: TimeSlotRequest):
    """
    ดึงข้อมูลคู่ที่ว่างในช่วงเวลาที่ระบุ
    แสดงรายละเอียดของ manager และ recruiter ที่ว่างในช่วงเวลานั้น
    """
    start = timeTest.time()
    print(f"[START] API started at {start:.6f}")
    # ใช้ฟังก์ชัน get_people เพื่อรับรายชื่ออีเมลผู้ใช้แยกตามประเภท M และ R
    t1 = timeTest.time()
    users_dict = get_people(
        file_path=str(FILE_PATH),
        location=request.location,
        english_min=request.english_min,
        exp_kind=request.exp_kind,
        age_key=request.age_key
    )
    print(f"[LOG] get_people done in {timeTest.time() - t1:.3f}s")
    # แยกเวลาเริ่มต้นและสิ้นสุดจาก time_slot
    time_parts = request.time_slot.split("-")
    start_time_str = time_parts[0]
    end_time_str = time_parts[1]
    
    # สร้าง datetime object
    date = datetime.fromisoformat(request.date).date()
    start_hour, start_minute = map(int, start_time_str.split(":"))
    end_hour, end_minute = map(int, end_time_str.split(":"))
    
    slot_start = datetime.combine(date, time(start_hour, start_minute)).astimezone(timezone.utc)
    slot_end = datetime.combine(date, time(end_hour, end_minute)).astimezone(timezone.utc)
    
    # สร้างช่วงวันสำหรับดึงข้อมูลปฏิทิน (เพื่อดึงข้อมูลทั้งวัน)
    start_datetime = datetime.combine(date, time(0, 0, 0)).astimezone(timezone.utc)
    end_datetime = datetime.combine(date, time(23, 59, 59)).astimezone(timezone.utc)
    
    time_min = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    time_max = end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    t2 = timeTest.time()
    # ดึงข้อมูลกิจกรรมสำหรับ Manager และ Recruiter
    managers_events = {}
    for user_info in users_dict['M']:
        email = user_info["Email"]
        name = user_info["Name"]
        calendar_id = email
        
        if is_token_valid(email):
            try:
                # ดึง token จาก DB
                token_entry = get_token(email)
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
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                
                # เก็บข้อมูลกิจกรรม
                managers_events[email] = {
                    'name': name,
                    'events': events
                }
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ M: {email}: {str(e)}")
        else:
            print(f"ผู้ใช้ {email} ยังไม่ได้ยืนยันตัวตน")
    print(f"[LOG] get_managers_events done in {timeTest.time() - t2:.3f}s")
    t3 = timeTest.time()
    recruiters_events = {}
    for user_info in users_dict['R']:
        email = user_info["Email"]
        name = user_info["Name"]
        calendar_id = email
        
        if is_token_valid(email):
            try:
                # ดึง token จาก DB
                token_entry = get_token(email)
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
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                
                # เก็บข้อมูลกิจกรรม
                recruiters_events[email] = {
                    'name': name,
                    'events': events
                }
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ R: {email}: {str(e)}")
        else:
            print(f"ผู้ใช้ {email} ยังไม่ได้ยืนยันตัวตน")
    print(f"[LOG] get_recruiters_events done in {timeTest.time() - t3:.3f}s")
    # เก็บคู่ที่ว่างในช่วงเวลาที่ระบุ
    available_pairs = []
    t4 = timeTest.time()
    for manager_email, manager_data in managers_events.items():
        manager_name = manager_data['name']
        manager_events = manager_data['events']
        
        for recruiter_email, recruiter_data in recruiters_events.items():
            recruiter_name = recruiter_data['name']
            recruiter_events = recruiter_data['events']
            
            # ตรวจสอบว่าทั้งคู่ว่างหรือไม่
            manager_is_available = is_available(manager_events, slot_start, slot_end)
            recruiter_is_available = is_available(recruiter_events, slot_start, slot_end)
            
            if manager_is_available and recruiter_is_available:
                available_pairs.append({
                    "pair": f"{manager_name}-{recruiter_name}",
                    "manager": {
                        "email": manager_email,
                        "name": manager_name
                    },
                    "recruiter": {
                        "email": recruiter_email,
                        "name": recruiter_name
                    }
                })
    print(f"[LOG] get_available_pairs done in {timeTest.time() - t4:.3f}s")
    # สร้างข้อความและตัวเลือกในรูปแบบ LINE Message
    message_text = f"กรุณาเลือก Manager-Recruiter ที่จะนัด\nเวลา {request.time_slot}\n"
    items = []
    
    for i, pair_detail in enumerate(available_pairs, start=1):
        pairs = pair_detail["pair"]
        message_text += f"   {i}.👥 {pair_detail['pair']}\n"
        
        # สร้างปุ่ม quick reply (สูงสุด 12 รายการเพื่อเหลือที่สำหรับปุ่มย้อนกลับ)
        if i < 13:
            items.append({
                "type": "action",
                "action": {
                    "type": "message",
                    "label": f"({i})",
                    "text": pairs
                }
            })
    
    # เพิ่มปุ่มย้อนกลับ
    items.append({
        "type": "action",
        "action": {
            "type": "message",
            "label": "ย้อนกลับ",
            "text": "ย้อนกลับ"
        }
    })
    
    line_message = {
        "type": "text",
        "text": message_text,
        "quickReply": {
            "items": items
        }
    }
    
   # สร้าง response ในรูปแบบของ LINE Payload
    response = {
        "line_payload": [line_message],
        "date": request.date,
        "time_slot": request.time_slot,
        "available_pairs": available_pairs
    }
    
    print(response)
    print(f"[LOG] API done in {timeTest.time() - start:.3f}s")
    return JSONResponse(
        content=response,
        headers={"Response-Type": "object"}
    )
#book calendar
@app.post("/events/create-bulk")
def create_bulk_events(event_request: BulkEventRequest):
    """สร้างการนัดหมายโดยใช้ name1 เป็น organizer และเพิ่ม name2 เป็นผู้เข้าร่วม"""
    start = timeTest.time()
    try:
        # แปลงเวลาให้เป็นรูปแบบ ISO
        try:
            start_time, end_time = convert_to_iso_format(event_request.date, event_request.time)
        except ValueError as e:
            return JSONResponse(
                content={
                    "message": "รูปแบบวันที่หรือเวลาไม่ถูกต้อง",
                    "error": str(e),
                    "line_payload": [{
                        "type": "text",
                        "text": f"รูปแบบวันที่หรือเวลาไม่ถูกต้อง: {str(e)}"
                    }]
                },
                headers={"Response-Type": "object"}
            )
        
        # ค้นหาอีเมลจากชื่อและพื้นที่
        email_info = find_emails_from_name_pair(event_request.name_pair, event_request.location)
        
        # เข้าถึงข้อมูลโดยตรงจาก dict
        name1_email = email_info["name1_email"]
        name1 = email_info["name1"]
        name2_email = email_info["name2_email"]
        name2 = email_info["name2"]
        
        # ตรวจสอบว่าผู้ใช้ทั้งสองคนได้ยืนยันตัวตนแล้วหรือไม่
        invalid_users = []
        if not is_token_valid(name1_email):
            invalid_users.append(name1_email)
        if not is_token_valid(name2_email):
            invalid_users.append(name2_email)
                
        if invalid_users:
            # สร้าง Line Response สำหรับกรณีที่มีผู้ใช้ยังไม่ได้ยืนยันตัวตน
            line_response = {
                "type": "text",
                "text": "ไม่สามารถสร้างการนัดหมายได้ เนื่องจากมีผู้ใช้บางคนยังไม่ได้ยืนยันตัวตน"
            }
            
            return JSONResponse(
                content={
                    "message": "ผู้ใช้บางคนยังไม่ได้ยืนยันตัวตน",
                    "invalid_users": invalid_users,
                    "line_payload": [line_response]
                },
                headers={"Response-Type": "object"}
            )
            
        # รับ credentials ของ name1
        token_entry1 = get_token(name1_email)
        creds1 = Credentials(
            token=token_entry1.access_token,
            refresh_token=token_entry1.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            scopes=SCOPES
        )
        
        # สร้าง service สำหรับ name1
        service1 = build('calendar', 'v3', credentials=creds1)
        
        # ตรวจสอบว่ามีกิจกรรมซ้ำซ้อนในช่วงเวลาเดียวกันหรือไม่
        time_min = start_time
        time_max = end_time
        
        # ตรวจสอบปฏิทินของ name1
        events_result1 = service1.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events1 = events_result1.get('items', [])
        
        # ตรวจสอบปฏิทินของ name2
        if is_token_valid(name2_email):
            token_entry2 = get_token(name2_email)
            creds2 = Credentials(
                token=token_entry2.access_token,
                refresh_token=token_entry2.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                scopes=SCOPES
            )
            service2 = build('calendar', 'v3', credentials=creds2)
            events_result2 = service2.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events2 = events_result2.get('items', [])
        else:
            events2 = []
        
        # ถ้ามีกิจกรรมในช่วงเวลาเดียวกัน ให้แจ้งเตือนและยกเลิกการสร้างนัดหมาย
        if events1 or events2:
            conflict_events = []
            
            # รวบรวมรายการกิจกรรมที่ซ้ำซ้อน
            for event in events1:
                conflict_events.append({
                    'title': event.get('summary', 'ไม่มีชื่อ'),
                    'start': event.get('start', {}).get('dateTime', ''),
                    'end': event.get('end', {}).get('dateTime', ''),
                    'calendar_owner': name1
                })
            
            for event in events2:
                conflict_events.append({
                    'title': event.get('summary', 'ไม่มีชื่อ'),
                    'start': event.get('start', {}).get('dateTime', ''),
                    'end': event.get('end', {}).get('dateTime', ''),
                    'calendar_owner': name2
                })
            
            # สร้าง Line Response สำหรับกรณีที่มีกิจกรรมซ้ำซ้อน
            line_response = {
                "type": "text",
                "text": f"ขออภัย ไม่สามารถทำการสร้างนัดได้เนื่องจากมีกิจกรรมอยู่แล้ว"
            }
            
            return JSONResponse(
                content={
                    "message": "มีกิจกรรมซ้ำซ้อนในช่วงเวลาเดียวกัน",
                    "conflict_events": conflict_events,
                    "line_payload": [line_response]
                },
                headers={"Response-Type": "object"}
            )
        
        # เตรียมรายชื่อผู้เข้าร่วมเพิ่มเติม
        additional_attendees = []
        if event_request.attendees:
            additional_attendees = [{'email': email} for email in event_request.attendees]
        
        # กำหนดชื่อหัวข้อตามรูปแบบที่ต้องการ
        event_summary = f"Onsite Interview : K. {name2} - {event_request.location}"
        
        # เตรียมข้อมูลกิจกรรม
        event_data = {
            'summary': event_summary,
            'location': event_request.event_location,
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
            'guestsCanSeeOtherGuests': True,  # ให้ผู้เข้าร่วมเห็นกันและกันได้
            'guestsCanModify': False,  # ให้ผู้เข้าร่วมสามารถแก้ไขรายละเอียดได้
            'sendUpdates': 'all'  # ส่งอีเมลแจ้งเตือนถึงผู้เข้าร่วมทุกคน
        }
        
        # ผลลัพธ์การดำเนินการ
        results = []
        
        # สร้างการนัดหมายเพียงครั้งเดียวโดยใช้ name1 เป็น organizer
        try:
            # เพิ่มทั้ง name1 และ name2 เป็นผู้เข้าร่วม (แม้ว่า name1 จะเป็น organizer)
            # ซึ่งจะช่วยให้แสดงรายชื่อในส่วนของผู้เข้าร่วมอย่างชัดเจน
            attendees = [
                {'email': name1_email, 'responseStatus': 'accepted', 'organizer': True},
                {'email': name2_email}
            ] + additional_attendees
            event_data['attendees'] = attendees
            
            # สร้างกิจกรรมในปฏิทินของ name1
            created_event = service1.events().insert(
                calendarId="primary",
                body=event_data
            ).execute()
            
            results.append({
                'email': name1_email,
                'success': True,
                'message': f'สร้างการนัดหมายสำเร็จ มี {name2} เป็นผู้เข้าร่วม',
                'event_id': created_event['id'],
                'html_link': created_event['htmlLink']
            })
            
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการสร้างการนัดหมาย: {str(e)}")
            results.append({
                'email': name1_email,
                'success': False,
                'message': f'เกิดข้อผิดพลาด: {str(e)}'
            })
            
            # สร้าง Line Response สำหรับกรณีเกิดข้อผิดพลาด
            line_response = {
                "type": "text",
                "text": f"เกิดข้อผิดพลาดในการสร้างการนัดหมาย: {str(e)}"
            }
            
            print(f"[DEBUG] API done at {timeTest.time() - start:.3f}s")
            return JSONResponse(
                content={
                    "message": "เกิดข้อผิดพลาดในการสร้างการนัดหมาย",
                    "error": str(e),
                    "line_payload": [line_response]
                },
                headers={"Response-Type": "object"}
            )
        
        # สร้าง Line Response แบบ text ธรรมดา
        line_response = {
            "type": "text",
            "text": f"นัดใน Google Calendar เรียบร้อยแล้ว สำหรับ {name1} และ {name2} ในหัวข้อ \"{event_summary}\" วันที่ {event_request.date} เวลา {event_request.time}"
        }
        
        # คืนค่าข้อมูลพร้อมกับ Line Response Object
        print(f"[DEBUG] API done at {timeTest.time() - start:.3f}s")
        return JSONResponse(
            content={
                "message": f"ดำเนินการสร้างการนัดหมายสำหรับ {name1_email} และ {name2_email}",
                "results": results,
                "line_payload": [line_response]
            },
            headers={"Response-Type": "object"}
        )
            
    except Exception as e:
        # สร้าง Line Response สำหรับกรณีเกิดข้อผิดพลาด
        line_response = {
            "type": "text",
            "text": f"เกิดข้อผิดพลาดในการสร้างการนัดหมาย: {str(e)}"
        }
        
        print(f"[DEBUG] API done at {timeTest.time() - start:.3f}s")
        return JSONResponse(
            content={
                "message": "เกิดข้อผิดพลาดในการสร้างการนัดหมาย",
                "error": str(e),
                "line_payload": [line_response]
            },
            headers={"Response-Type": "object"}
        )
#login
@app.get("/events/{user_email}")
def get_user_events(
    user_email: str, 
    calendar_id: str = "primary",
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None
):
    """ดึงข้อมูลกิจกรรมของผู้ใช้คนเดียว และยืนยันตัวตนหากจำเป็น"""
    # ดึงข้อมูลและยืนยันตัวตนถ้าจำเป็น
    creds_result = get_credentials(user_email)
    
    # ตรวจสอบว่าต้องการการยืนยันตัวตนหรือไม่
    if isinstance(creds_result, dict) and creds_result.get("requires_auth"):
        auth_url = creds_result["auth_url"]
        
        # เข้ารหัส auth_url และ email เพื่อส่งเป็นพารามิเตอร์
        encoded_auth_url = quote_plus(auth_url)
        encoded_email = quote_plus(user_email)
        
        # สร้าง URL ไปยังหน้า redirect ของเรา
        redirect_page_url = f"{base_url}/auth-redirect?auth_url={encoded_auth_url}&email={encoded_email}"
        
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
                                    "align": "center",       # จัดกลาง
                                    "gravity": "center",     # จัดให้อยู่ตรงกลางแนวตั้ง
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


        
        # สร้าง response object พร้อม header ที่ระบุว่าเป็น JSON
        response_data = {
            "email": user_email,
            "is_authenticated": False,
            "auth_required": True,
            "auth_url": auth_url,
            "redirect_url": redirect_page_url,
            "line_payload": [line_flex_message]
        }
        
        return JSONResponse(
            content=response_data,
            headers={"Response-Type": "object"}
        )
    
    # ถ้ามี credentials แล้ว ส่งข้อความว่าผู้ใช้เข้าสู่ระบบแล้ว
    try:
        # สร้าง LINE Flex Message แจ้งว่าได้เข้าสู่ระบบแล้ว
        already_login_message = {
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
        
        response_data = {
            'email': user_email,
            'is_authenticated': True,
            'message': "คุณได้ทำการเข้าสู่ระบบแล้ว✅",
            'line_payload': [already_login_message]
        }
        
        return JSONResponse(
            content=response_data,
            headers={"Response-Type": "object"}
        )
    except Exception as e:
        print(f"เกิดข้อผิดพลาดสำหรับ {user_email}: {str(e)}")
        
        # สร้าง LINE Flex Message สำหรับแสดงข้อผิดพลาด
        error_flex_message = {
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
        
        error_response = {
            'email': user_email,
            'error': str(e),
            'is_authenticated': False,
            'line_payload': [error_flex_message]
        }
        print(error_response)
        return JSONResponse(
            content=error_response,
            headers={"Response-Type": "object"}
        )

# =========================================================================================================



# ======================== ส่วนที่เกี่ยวกับ DB ========================================
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

# =============================================================================================
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



