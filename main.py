# main.py
import os
import json
import shutil
from datetime import datetime, timedelta
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from pydantic import BaseModel
from dotenv import load_dotenv

# โหลดตัวแปรสภาพแวดล้อม
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

# กำหนด scope การเข้าถึง Google Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']
#file เก็บข้อมูล client secret ของ OAuth
CLIENT_SECRET_FILE = 'client_secret_452392817293-omce8fua8307hkuvlngpvpebvnot3qh1.apps.googleusercontent.com.json'
TOKEN_DIR = 'tokens' # โฟลเดอร์เก็บไฟล์ token
REDIRECT_URI = 'http://localhost:8080/'  # กำหนด redirect URI 
AUTH_PORT = 8080  # พอร์ต redirect

# ลบและสร้างโฟลเดอร์ tokens ใหม่เพื่อหลีกเลี่ยงปัญหา
try:
    if os.path.exists(TOKEN_DIR):
        # shutil.rmtree(TOKEN_DIR)
        # print(f"ลบโฟลเดอร์ {TOKEN_DIR} เดิมแล้ว")
        pass 
    else :
        os.makedirs(TOKEN_DIR)
        print(f"สร้างโฟลเดอร์ {TOKEN_DIR} ใหม่แล้ว")
except Exception as e:
    print(f"เกิดข้อผิดพลาดในการจัดการโฟลเดอร์ {TOKEN_DIR}: {str(e)}")

# โมเดลสำหรับรับข้อมูลผู้ใช้
class UserCalendar(BaseModel):
    email: str #required
    calendar_id: Optional[str] = "primary" # Optional

# โมเดลสำหรับรับข้อมูลผู้ใช้หลายคน
class UsersRequest(BaseModel):
    users: List[UserCalendar] #List ของ UserCalendar
    start_date: Optional[str] = None
    end_date: Optional[str] = None

# โมเดลสำหรับการนัดหมายพร้อมกันหลายคน
class BulkEventRequest(BaseModel):
    user_emails: List[str]  # รายชื่ออีเมลของผู้ที่จะสร้างปฏิทิน
    summary: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_time: str  # รูปแบบ ISO format เช่น "2025-04-20T09:00:00+07:00"
    end_time: str    # รูปแบบ ISO format เช่น "2025-04-20T10:00:00+07:00"
    attendees: Optional[List[str]] = None  # รายชื่ออีเมลของผู้เข้าร่วมเพิ่มเติม (จะถูกเพิ่มในทุกปฏิทิน)

def is_token_valid(user_email: str) -> bool:
    """ตรวจสอบว่า token ของผู้ใช้ยังใช้งานได้หรือไม่"""
    token_path = os.path.join(TOKEN_DIR, f'token_{user_email}.json')
    
    if not os.path.exists(token_path):
        print(f"ไม่พบไฟล์ token สำหรับ {user_email}")
        return False
    
    try:
        with open(token_path, 'r') as token_file:
            token_data = json.load(token_file)
            
            if not token_data:
                print(f"ข้อมูล token ว่างเปล่าสำหรับ {user_email}")
                return False
                
            # ตรวจสอบว่า refresh_token มีอยู่ในข้อมูล
            if 'refresh_token' not in token_data:
                print(f"ไม่พบ refresh_token สำหรับ {user_email} ในข้อมูล token")
                return False
                
            # สร้าง credentials จาก token
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            
            # ตรวจสอบว่า token ยังใช้งานได้
            if creds.valid:
                print(f"Token ยังใช้งานได้สำหรับ {user_email}")
                return True
                
            # ถ้า token หมดอายุแต่มี refresh_token
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    # บันทึก token ที่รีเฟรชแล้ว
                    with open(token_path, 'w') as token:
                        token.write(creds.to_json())
                    print(f"รีเฟรช token สำเร็จสำหรับ {user_email}")
                    return True
                except Exception as e:
                    print(f"ไม่สามารถรีเฟรช token ได้สำหรับ {user_email}: {str(e)}")
                    return False
            
            return False
            
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการตรวจสอบ token สำหรับ {user_email}: {str(e)}")
        return False

# def get_credentials(user_email: str):
#     """รับ credentials สำหรับการเข้าถึง Google Calendar API"""
#     token_path = os.path.join(TOKEN_DIR, f'token_{user_email}.json')
#     creds = None
    
#     # ตรวจสอบว่ามีไฟล์ token อยู่แล้วหรือไม่และยังใช้งานได้หรือไม่
#     if os.path.exists(token_path):
#         try:
#             with open(token_path, 'r') as token_file:
#                 token_data = json.load(token_file)
#                 creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                
#                 # ถ้า token ยังใช้งานได้ ก็ใช้ได้เลย
#                 if creds.valid:
#                     print(f"ใช้ token ที่มีอยู่แล้วสำหรับ {user_email}")
#                     return creds
                    
#                 # ถ้า token หมดอายุแต่มี refresh_token ให้รีเฟรช
#                 if creds.expired and creds.refresh_token:
#                     try:
#                         creds.refresh(Request())
#                         with open(token_path, 'w') as token:
#                             token.write(creds.to_json())
#                         print(f"รีเฟรช token สำเร็จสำหรับ {user_email}")
#                         return creds
#                     except Exception as e:
#                         print(f"ไม่สามารถรีเฟรช token ได้: {str(e)}")
#                         creds = None
#                 else:
#                     # ถ้าไม่มี refresh_token ต้องสร้าง flow ใหม่
#                     creds = None
#         except Exception as e:
#             print(f"เกิดข้อผิดพลาดในการโหลด token: {str(e)}")
#             creds = None
    
#     # ถ้าไม่มี token หรือ token ใช้ไม่ได้ ต้องสร้าง flow ใหม่
#     if not creds:
#         try:
#             # เตรียมสภาพแวดล้อม
#             os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
            
#             # สร้าง flow เพื่อยืนยันตัวตน
#             flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
#             flow.redirect_uri = REDIRECT_URI
            
#             print(f"กำลังสร้างการเชื่อมต่อ OAuth2 สำหรับ {user_email} ด้วย redirect URI: {REDIRECT_URI}")
            
#             # เปิดเบราว์เซอร์เพื่อยืนยันตัวตนและขอ refresh_token
#             creds = flow.run_local_server(
#                 port=AUTH_PORT,
#                 access_type='offline',
#                 prompt='consent'
#             )
            
#             # บันทึก token
#             with open(token_path, 'w') as token_file:
#                 token_file.write(creds.to_json())
                
#             print(f"การยืนยันตัวตนสำเร็จสำหรับ {user_email}! บันทึก token ที่: {token_path}")
            
#             # ตรวจสอบว่ามี refresh_token หรือไม่
#             token_data = json.loads(creds.to_json())
#             if 'refresh_token' in token_data:
#                 print(f"ได้รับ refresh_token สำหรับ {user_email} แล้ว")
#             else:
#                 print(f"ไม่ได้รับ refresh_token สำหรับ {user_email} โปรดลองล้าง cookies ของเบราว์เซอร์")
                
#         except Exception as e:
#             print(f"เกิดข้อผิดพลาดในการยืนยันตัวตน: {str(e)}")
#             raise HTTPException(
#                 status_code=500, 
#                 detail=f"เกิดข้อผิดพลาดในการยืนยันตัวตนสำหรับ {user_email}: {str(e)}"
#             )
    
#     return creds


def get_credentials(user_email: str):
    """รับ credentials สำหรับการเข้าถึง Google Calendar API"""
    token_path = os.path.join(TOKEN_DIR, f'token_{user_email}.json')
    creds = None
    
    # ถ้ามีไฟล์ token อยู่แล้ว ให้ลองโหลด
    if os.path.exists(token_path):
        try:
            with open(token_path, 'r') as token_file:
                creds = Credentials.from_authorized_user_info(json.load(token_file), SCOPES)
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการโหลด token: {str(e)}")
    
    # ถ้าไม่มี token หรือไม่สามารถใช้งานได้ ให้สร้างใหม่
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # สร้าง flow ใหม่
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            flow.redirect_uri = REDIRECT_URI
            creds = flow.run_local_server(port=AUTH_PORT, access_type='offline', prompt='consent')
        
        # บันทึก token ใหม่
        with open(token_path, 'w') as token_file:
            token_file.write(creds.to_json())
            
    return creds

def get_calendar_events(user_email: str, calendar_id: str, start_date: str, end_date: str):
    """ดึงข้อมูลกิจกรรมจาก Google Calendar"""
    try:
        # รับ credentials
        creds = get_credentials(user_email)
        
        # สร้าง service สำหรับเรียกใช้ Calendar API
        service = build('calendar', 'v3', credentials=creds)
        
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
            'auth_status': 'authenticated'
        }
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ {user_email}: {str(e)}")
        return {
            'email': user_email,
            'calendar_id': calendar_id,
            'events': [],
            'error': str(e),
            'auth_status': 'error'
        }

@app.get("/")
def read_root():
    return {"message": "ยินดีต้อนรับสู่ Google Calendar API"}

@app.get("/events/{user_email}")
def get_user_events(
    user_email: str, 
    calendar_id: str = "primary",
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None
):
    """ดึงข้อมูลกิจกรรมของผู้ใช้คนเดียว และยืนยันตัวตนหากจำเป็น"""
    # ดึงข้อมูลและยืนยันตัวตนถ้าจำเป็น
    result = get_calendar_events(user_email, calendar_id, start_date, end_date)
    
    # ตรวจสอบว่ามี token และใช้งานได้หรือไม่
    is_authenticated = is_token_valid(user_email)
    result['is_authenticated'] = is_authenticated
    
    return JSONResponse(content=result)

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

@app.post("/events/bulk")
def get_bulk_events(
    emails: List[str] = Query(..., description="รายการอีเมลของผู้ใช้"),
    calendar_id: str = "primary",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """ดึงข้อมูลกิจกรรมของผู้ใช้หลายคนโดยใช้ query parameters (เฉพาะผู้ใช้ที่ยืนยันตัวตนแล้ว)"""
    # สร้าง UsersRequest เพื่อใช้ฟังก์ชันที่มีอยู่แล้ว
    request = UsersRequest(
        users=[UserCalendar(email=email, calendar_id=calendar_id) for email in emails],
        start_date=start_date,
        end_date=end_date
    )
    
    # ใช้ฟังก์ชัน get_multiple_users_events
    return get_multiple_users_events(request)

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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"เริ่มต้น FastAPI บน port {port}...")
    print(f"เข้าถึง API documentation ได้ที่: http://localhost:{port}/docs")
    print(f"กำหนด redirect URI สำหรับ OAuth2: {REDIRECT_URI} (port: {AUTH_PORT})")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)