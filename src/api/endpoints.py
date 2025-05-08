# Standard library
import asyncio
import json
import os
from datetime import datetime, time, timedelta, timezone
import ssl
import sys
import uuid
# Third-party libraries
import aiofiles
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, logger
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from linebot.exceptions import InvalidSignatureError
from typing import Optional
import logging
from linebot import LineBotApi, WebhookHandler
import time as timeTest
import holidays

# Local application
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.config import *
from src.utils.func import *
from src.models.schemas import *
import logging
from src.utils.token_db import *

logging.basicConfig(level=logging.INFO)


load_dotenv()

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


REDIRECT_URI = 'http://localhost:8080/'  # กำหนด redirect URI 
AUTH_PORT = 8080  # พอร์ต redirect
FILE_PATH = os.path.join(os.path.dirname(__file__), '..', '..', os.getenv("FILE_PATH"))
# ปอดการแจ้งเตือน INFO:googleapiclient.discovery_cache:file_cache is only supported with oauth2client<4.0.0
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
line_bot_api = LineBotApi(os.getenv("CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("CHANNEL_SECRET"))
base_url = os.environ.get('BASE_URL')
EMAIL_SENDER = os.getenv("EMAIL_to_SEND_MESSAGE")
EMAIL_PASSWORD = os.getenv("PASSWORD_EMAIL")
CLIENT_SECRET_FILE = os.getenv("CLIENT_SECRET_FILE")
logger = logging.getLogger(__name__)

@app.get("/")
def read_root():
    return {"message": "ยินดีต้อนรับสู่ Google Calendar API"}

@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_decode = body.decode("utf-8")

    try:
        handler.handle(body_decode, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    return JSONResponse(content={"status": "OK"})

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
        # return JSONResponse(content={
        #     "email": user_email,
        #     "is_authenticated": False,
        #     "auth_required": True,
        #     "auth_url": creds_result["auth_url"]
        # })
        return RedirectResponse(url=creds_result["auth_url"])
    
    # ถ้ามี credentials แล้ว ดึงข้อมูลปฏิทิน
    try:
        service = build('calendar', 'v3', credentials=creds_result)
        
        # กำหนดช่วงเวลาในการดึงข้อมูล
        time_min = start_date + "T00:00:00Z" if start_date else datetime.utcnow().isoformat() + "Z"
        time_max = end_date + "T23:59:59Z" if end_date else (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"
        
        print(f"กำลังดึงข้อมูลสำหรับ {user_email} จาก {time_min} ถึง {time_max}")
        
        # ดึงข้อมูลกิจกรรม
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        print(f"พบ {len(events)} กิจกรรมสำหรับ {user_email}")
        
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
        
        return {
            'email': user_email,
            'calendar_id': calendar_id,
            'events': formatted_events,
            'is_authenticated': True
        }
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ {user_email}: {str(e)}")
        return {
            'email': user_email,
            'calendar_id': calendar_id,
            'events': [],
            'error': str(e),
            'is_authenticated': False
        }

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

@app.delete("/auth/revoke/{user_email}")
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
    
@app.post("/events/create-bulk")
def create_bulk_events(event_request: BulkEventRequest):
    """สร้างการนัดหมายพร้อมกันสำหรับหลายผู้ใช้ โดยมีรายละเอียดเดียวกัน"""
    results = []
    
    for user_email in event_request.user_emails:
        try:
            # ตรวจสอบว่าผู้ใช้ได้ยืนยันตัวตนแล้วหรือไม่
            if not is_token_valid(user_email):
                results.append({
                    'email': user_email,
                    'success': False,
                    'message': 'ผู้ใช้ยังไม่ได้ยืนยันตัวตน กรุณาใช้ /events/{email} ก่อน'
                })
                continue
                
            # รับ credentials จาก DB
            token_entry = get_token(user_email)
            creds = Credentials(
                token=token_entry.access_token,
                refresh_token=token_entry.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                scopes=SCOPES
            )
            
            # สร้าง service
            service = build('calendar', 'v3', credentials=creds)
            
            # เตรียมข้อมูลกิจกรรม
            event_data = {
                'summary': event_request.summary,
                'location': event_request.location,
                'description': event_request.description,
                'start': {
                    'dateTime': event_request.start_time,
                    'timeZone': 'Asia/Bangkok',
                },
                'end': {
                    'dateTime': event_request.end_time,
                    'timeZone': 'Asia/Bangkok',
                },
            }
            
            # รวมรายชื่อผู้เข้าร่วม
            attendees = []
            # เพิ่มผู้ใช้อื่นๆ ในรายการเป็นผู้เข้าร่วม
            for other_email in event_request.user_emails:
                if other_email != user_email:  # ไม่รวมตัวเอง
                    attendees.append({'email': other_email})
            
            # เพิ่มผู้เข้าร่วมเพิ่มเติมถ้ามี
            if event_request.attendees:
                for attendee in event_request.attendees:
                    attendees.append({'email': attendee})
            
            if attendees:
                event_data['attendees'] = attendees
                # ส่งอีเมลแจ้งเตือนถึงผู้เข้าร่วม
                event_data['sendUpdates'] = 'all'
            
            # สร้างกิจกรรม
            created_event = service.events().insert(
                calendarId="primary",
                body=event_data
            ).execute()
            
            results.append({
                'email': user_email,
                'success': True,
                'message': 'สร้างการนัดหมายสำเร็จ',
                'event_id': created_event['id'],
                'html_link': created_event['htmlLink']
            })
            # เปลี่ยน format วัน/เวลา ค่อยทำ
            # start_time = datetime.fromisoformat(event_request.start_time)
            # end_time = datetime.fromisoformat(event_request.end_time)
            # day_suffix = get_day_suffix(event_request.start_time.day)
            # date_formatted = start_time.strftime(f"%A %B {start_time.day}{day_suffix}, %Y")
            # # Format เวลา
            # start_time_formatted = start_time.strftime("%-I:%M %p")  # %-I ใช้ไม่ใส่ 0 นำหน้า เช่น 9:00 AM
            # end_time_formatted = end_time.strftime("%-I:%M %p")


            # ➡️ เพิ่มส่งเมลแจ้งเตือนด้วย
            send_notification_email(
                receiver_email=user_email,
                subject="New Appointment Scheduled",
                body=f"""You have a new appointment scheduled.

            
            Subject: {event_request.summary}
            Details: {event_request.description}
            เวลาเริ่มต้น: {event_request.start_time}
            เวลาสิ้นสุด: {event_request.end_time}

            ดูรายละเอียดเพิ่มเติมได้ที่: {created_event['htmlLink']}

            ขอบคุณค่ะ
            """
            )
            
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการสร้างการนัดหมายสำหรับ {user_email}: {str(e)}")
            results.append({
                'email': user_email,
                'success': False,
                'message': f'เกิดข้อผิดพลาด: {str(e)}'
            })
    
    return {
        "message": f"ดำเนินการสร้างการนัดหมายสำหรับ {len(event_request.user_emails)} คน",
        "results": results
    }

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
                starttime = timeTest.time()
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
            
            print(f"Took {endtime - starttime:.4f} sec : {email}")
            
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

@app.get("/test/auto-refresh")
def trigger_auto_refresh():
    """เรียกใช้ auto_refresh_tokens เพื่อทดสอบทันที"""
    from src.utils.auto_refresh_jobs import auto_refresh_tokens
    
    try:
        # เรียกใช้ฟังก์ชันโดยตรง
        auto_refresh_tokens()
        return {"status": "success", "message": "Auto refresh tokens triggered successfully"}
    except Exception as e:
        return {"status": "error", "message": f"Error triggering auto refresh: {str(e)}"}

 