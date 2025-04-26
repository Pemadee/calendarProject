# Standard library
import json
import os
from datetime import datetime, time, timedelta, timezone
import ssl
import sys
# Third-party libraries
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from linebot.exceptions import InvalidSignatureError
from typing import Optional
import logging
# Local application
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.line_bot import *
from src.config import *
from src.utils.func import *
from src.models.schemas import *
# ###################
import logging

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


@app.get("/")
def read_root():
    return {"message": "ยินดีต้อนรับสู่ Google Calendar API"}

@app.post("/webhook")
async def webhook(request: Request):
    # Get X-Line-Signature header and request body
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_decode = body.decode("utf-8")
    
    try:
        # Handle webhook body
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
        base_url = os.environ.get('BASE_URL')
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
        token_path = os.path.join(TOKEN_DIR, f'token_{actual_email}.json')
        with open(token_path, 'w') as token_file:
            token_file.write(credentials.to_json())
        
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
                with open(os.path.join(TOKEN_DIR, f'token_{user.email}.json'), 'r') as token_file:
                    token_data = json.load(token_file)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                
                service = build('calendar', 'v3', credentials=creds)
                
                # กำหนดช่วงเวลาในการดึงข้อมูล
                time_min = request.start_date + "T00:00:00Z" if request.start_date else datetime.utcnow().isoformat() + "Z"
                time_max = request.end_date + "T23:59:59Z" if request.end_date else (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"
                
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
                with open(os.path.join(TOKEN_DIR, f'token_{email}.json'), 'r') as token_file:
                    token_data = json.load(token_file)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                
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
                with open(os.path.join(TOKEN_DIR, f'token_{email}.json'), 'r') as token_file:
                    token_data = json.load(token_file)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                
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

@app.get("/auth/status/{user_email}")
def check_auth_status(user_email: str):
    """ตรวจสอบสถานะการยืนยันตัวตนของผู้ใช้"""
    is_authenticated = is_token_valid(user_email)
    
    # ตรวจสอบข้อมูล token
    token_info = {}
    token_path = os.path.join(TOKEN_DIR, f'token_{user_email}.json')
    
    if os.path.exists(token_path):
        try:
            with open(token_path, 'r') as token_file:
                token_data = json.load(token_file)
                token_info["has_token_file"] = True
                token_info["token_keys"] = list(token_data.keys())
                token_info["has_refresh_token"] = 'refresh_token' in token_data
        except Exception as e:
            token_info["has_token_file"] = True
            token_info["error_reading"] = str(e)
    else:
        token_info["has_token_file"] = False
    
    return {
        "email": user_email,
        "authenticated": is_authenticated,
        "token_info": token_info,
        "message": "ผู้ใช้ได้ยืนยันตัวตนแล้ว" if is_authenticated else "ผู้ใช้ยังไม่ได้ยืนยันตัวตน ใช้ /events/<email> เพื่อยืนยันตัวตน"
    }

@app.delete("/auth/revoke/{user_email}")
def revoke_auth(user_email: str):
    """ยกเลิกการยืนยันตัวตนของผู้ใช้โดยลบไฟล์ token"""
    token_path = os.path.join(TOKEN_DIR, f'token_{user_email}.json')
    
    if os.path.exists(token_path):
        try:
            os.remove(token_path)
            return {
                "email": user_email,
                "success": True,
                "message": f"ยกเลิกการยืนยันตัวตนสำหรับ {user_email} สำเร็จ"
            }
        except Exception as e:
            return {
                "email": user_email,
                "success": False,
                "message": f"เกิดข้อผิดพลาดในการยกเลิกการยืนยันตัวตน: {str(e)}"
            }
    else:
        return {
            "email": user_email,
            "success": False,
            "message": f"ไม่พบข้อมูลการยืนยันตัวตนสำหรับ {user_email}"
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
                
            # รับ credentials
            with open(os.path.join(TOKEN_DIR, f'token_{user_email}.json'), 'r') as token_file:
                token_data = json.load(token_file)
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            
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

@app.get("/users/list")
def list_registered_users():
    """ดึงรายการอีเมลผู้ใช้ทั้งหมดที่ได้ลงทะเบียนในระบบ"""
    try:
        # ตรวจสอบไฟลเดอร์ TOKEN_DIR ว่ามีหรือไม่
        if not os.path.exists(TOKEN_DIR):
            return {"users": [], "message": "ยังไม่มีผู้ใช้ลงทะเบียนในระบบ"}
        
        # หาไฟล์ token ทั้งหมด
        token_files = []
        for filename in os.listdir(TOKEN_DIR):
            # เลือกเฉพาะไฟล์ที่เริ่มต้นด้วย token_ และลงท้ายด้วย .json
            if filename.startswith('token_') and filename.endswith('.json'):
                token_files.append(filename)
        
        # ดึงอีเมลจากชื่อไฟล์
        emails = []
        for file in token_files:
            # ตัด "token_" ออกจากด้านหน้า
            email_with_extension = file[6:]  # ตัด "token_" ออก
            # ตัด ".json" ออกจากด้านหลัง
            email = email_with_extension[:-5]  # ตัด ".json" ออก
            
            # # ตรวจสอบว่า token ยังใช้งานได้
            # if is_token_valid(email): 
            emails.append(email)
        
        # เรียงลำดับอีเมลตามตัวอักษร
        emails.sort()
        
        return {
            "users": emails,
        }
        
    except Exception as e:
        return {
            "total_users": 0,
            "users": [],
            "error": str(e),
            "message": "เกิดข้อผิดพลาดในการดึงรายการผู้ใช้"
        }


# @app.get("/users/list")
# def list_registered_users():
#     logging.info("Received request for /users/list")
#     users = ["a@gmail.com", "b@gmail.com", "c@gmail.com", "d@gmail.com"]
#     logging.info(f"Returning users: {users}")
#     return {"users": users}

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
    
    # กำหนดเวลาเริ่มต้น
    if request.start_date:
        start_datetime = datetime.fromisoformat(request.start_date).replace(hour=0, minute=0, second=0, microsecond=0)
        time_min = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        start_datetime = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        time_min = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # กำหนดช่วงเวลาในการดึงข้อมูล โดยใช้ time_period แทน end_date
    # ถ้ามี time_period ให้ใช้ค่านั้น ถ้าไม่มีและมี end_date ให้ใช้ end_date
    if request.time_period:
    # ค้นหาเป็นระยะเวลา 30 วัน หรือมากกว่าจำนวนวันที่ต้องการ 3 เท่า
        days_to_check = max(30, int(request.time_period) * 3)
        end_datetime = start_datetime + timedelta(days=days_to_check)
    elif request.end_date:
        end_datetime = datetime.fromisoformat(request.end_date).replace(hour=23, minute=59, second=59)
    else:
        days_to_check = 7
        end_datetime = start_datetime + timedelta(days=days_to_check)

    time_max = end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # สร้างรายการวันที่จะตรวจสอบ
    date_list = []
    current_date = start_datetime.date()
    while current_date <= end_datetime.date():
        date_list.append(current_date)
        current_date += timedelta(days=1)
    
    # ดึงข้อมูลกิจกรรมสำหรับ Manager
    managers_events = {}
    for user_info in users_dict['M']:
        email = user_info["Email"]
        name = user_info["Name"]
        calendar_id = email
        
        if is_token_valid(email):
            try:
                with open(os.path.join(TOKEN_DIR, f'token_{email}.json'), 'r') as token_file:
                    token_data = json.load(token_file)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                
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
                with open(os.path.join(TOKEN_DIR, f'token_{email}.json'), 'r') as token_file:
                    token_data = json.load(token_file)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                
                service = build('calendar', 'v3', credentials=creds)
                
                print(f"กำลังดึงข้อมูลสำหรับ R: {email} ({name}) จาก {time_min} ถึง {time_max}")
                
                events_result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
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
    
    # เก็บช่วงเวลาว่างตามวันที่
    # โครงสร้าง: time_based_results[date][time_slot] = [{คู่ที่ว่าง}]
    time_based_results = {}
    
    # ตรวจสอบเวลาว่างสำหรับทุกวัน
    for date in date_list:
        time_based_results[date] = {}
        
        # สร้างช่วงเวลาทุกๆ 30 นาที
        time_slots = []
        for hour in range(9, 18):
            for minute in [0, 30]:
                slot_start = datetime.combine(date, time(hour, minute)).astimezone(timezone.utc)
                slot_end = (slot_start + timedelta(minutes=30)).astimezone(timezone.utc)
                time_slots.append((slot_start, slot_end))
        
        # ตรวจสอบแต่ละช่วงเวลา
        for slot_start, slot_end in time_slots:
            # แปลงเป็นเวลาท้องถิ่นเพื่อแสดงผล
            local_start = slot_start.astimezone().strftime("%H:%M")
            local_end = slot_end.astimezone().strftime("%H:%M")
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
    
    # เตรียมข้อมูลสำหรับแสดงผล
    line_friendly_results = []
    days_found = 0  # ตัวแปรนับจำนวนวันที่มีเวลาว่าง
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
        selected_dates = available_dates[:required_days]
        
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


    # เรียงผลลัพธ์ตามวันที่
    line_friendly_results.sort(key=lambda x: x["date"])
    
    # สร้างข้อความสรุปสำหรับ LINE
    line_summary = []
    
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



@app.post("/getmeeting")
async def receive_meeting(request: Request):
    data = await request.json()
    print("📥 ได้รับข้อมูลจาก LINE BOT:", data)

    subject = f"นัดปลาชุมกันนน [ชื่อ : {data['summary']}]"
    body = f"""📝 ข้อมูลการประชุม:

            📌 ชื่อ: {data['summary']}
            📆 วันที่: {data['start_time'].split('T')[0]}
            🕒 เวลา: {data['start_time'].split('T')[1][:5]} - {data['end_time'].split('T')[1][:5]}

            👥 ผู้เข้าร่วม:
            """ + "\n".join(f"- {email}" for email in data["user_emails"])

    context = ssl._create_unverified_context()

    for to_email in data["user_emails"]:
        message = EmailMessage()
        message["From"] = os.getenv("EMAIL_to_SEND_MESSAGE")
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        try:
            await aiosmtplib.send(
                message,
                hostname="smtp.gmail.com",
                port=587,
                start_tls=True,
                username=os.getenv("EMAIL_to_SEND_MESSAGE"),
                password=os.getenv("PASSWORD_EMAIL"),
                tls_context=context  # ใช้ context นี้แทน
            )
        except Exception as e:
            print(f"❌ ส่งอีเมลไปยัง {to_email} ไม่สำเร็จ: {e}")

    return JSONResponse(content={"status": "received", "detail": "ได้รับข้อมูลและส่งอีเมลแล้ว"})

@app.get("/test")
async def receive_meeting(request: Request):
    pass