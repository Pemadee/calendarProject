# main.py
import asyncio
from typing import Any, Dict, List
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import datetime
import pytz
import os.path
import json
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os
import urllib.parse
import uvicorn

app = FastAPI()

# กำหนด scope ให้ครอบคลุมทั้งการเข้าถึงปฏิทินและข้อมูลอีเมล
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'openid',
    'https://www.googleapis.com/auth/userinfo.email'
]
CLIENT_SECRETS_FILE = "credentials.json"
TOKEN_DIR = "tokens"
REDIRECT_URI = "http://localhost:8000/oauth2callback"

# for CORS (optional)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class CalendarRequest(BaseModel):
    email: str
    date: str

class MultiCalendarRequest(BaseModel):
    emails: List[str]
    date: str  # รูปแบบ: "2025-04-23"

# ส่วนที่เพิ่มมาจาก data_service.py
# Database for meetings (in-memory for now)
meetings = []

# Ensure tokens directory exists
os.makedirs(TOKEN_DIR, exist_ok=True)

def sanitize_email(email: str) -> str:
    return email.replace('@', '_at_').replace('.', '_dot_')

def get_token_path(email: str) -> str:
    return os.path.join(TOKEN_DIR, f"{sanitize_email(email)}.json")
   
def save_credentials(creds: Credentials, email: str):
    with open(get_token_path(email), 'w') as token:
        token.write(creds.to_json())

def get_calendar_service(email: str):
    token_path = get_token_path(email)
    if not os.path.exists(token_path):
        raise Exception(f"No token found for {email}. Please authorize first.")
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    return build('calendar', 'v3', credentials=creds)

def get_email_from_userinfo(creds: Credentials):
    """ดึงอีเมลจาก userinfo API ของ Google"""
    try:
        userinfo_service = build('oauth2', 'v2', credentials=creds)
        user_info = userinfo_service.userinfo().get().execute()
        return user_info.get('email')
    except Exception as e:
        raise Exception(f"Failed to get email: {str(e)}")

# ฟังก์ชั่นสำหรับแปลงรูปแบบวันที่
def convert_thai_to_iso_date(thai_date):
    """แปลงวันที่จากรูปแบบไทย (วว/ดด/25XX) เป็นรูปแบบสากล (YYYY-MM-DD)"""
    day, month, year = thai_date.split('/')
    year_ce = int(year) - 543  # แปลงจาก พ.ศ. เป็น ค.ศ.
    return f"{year_ce}-{month.zfill(2)}-{day.zfill(2)}"

def convert_iso_to_thai_date(iso_date):
    """แปลงวันที่จากรูปแบบสากล (YYYY-MM-DD) เป็นรูปแบบไทย (วว/ดด/25XX)"""
    date_obj = datetime.datetime.strptime(iso_date, "%Y-%m-%d")
    year_be = date_obj.year + 543  # แปลงจาก ค.ศ. เป็น พ.ศ.
    return f"{date_obj.day}/{date_obj.month}/{year_be}"

@app.get("/")
def read_root():
    return {"message": "Hello, try /authorize to begin or /line-bot-api for chatbot services."}

@app.get("/authorize")
def authorize():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    # สำคัญ: ต้องใช้ access_type='offline' เพื่อรับ refresh token
    # และเพิ่ม prompt='consent' เพื่อให้ Google ถามผู้ใช้ทุกครั้งและส่ง refresh token มาทุกครั้ง
    authorization_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'  # บังคับให้ Google ส่ง refresh token ทุกครั้ง
    )
    return RedirectResponse(authorization_url)

@app.get("/oauth2callback")
def oauth2callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return HTMLResponse("<h1>Error: No code provided</h1>", status_code=400)

    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        # ตั้งค่าให้ flow ยอมรับ scope ที่เปลี่ยนแปลงได้
        flow.oauth2session._client.scope_change_allowance = True
        
        # แลกเปลี่ยน code เป็น token
        flow.fetch_token(code=code)
        
        # ตรวจสอบว่ามี refresh_token หรือไม่
        if not hasattr(flow.credentials, 'refresh_token') or not flow.credentials.refresh_token:
            return HTMLResponse("<h1>Error: No refresh token received. Please try again and ensure you consent to the application.</h1>", status_code=400)
        
        # ดึงอีเมลจาก userinfo API
        email = get_email_from_userinfo(flow.credentials)
        
        # บันทึก credentials ที่ได้รับ
        save_credentials(flow.credentials, email)
        
        return HTMLResponse(f"<h1>Authorized {email}. You can close this window now.</h1>")
    except Exception as e:
        return HTMLResponse(f"<h1>Error: {str(e)}</h1>", status_code=500)

@app.post("/get-calendar")
async def get_calendar_events(req: CalendarRequest):
    try:
        date = datetime.datetime.strptime(req.date, "%Y-%m-%d")
        start_of_day = date.replace(hour=0, minute=0, second=0, tzinfo=pytz.UTC)
        end_of_day = date.replace(hour=23, minute=59, second=59, tzinfo=pytz.UTC)

        service = get_calendar_service(req.email)

        events_result = service.events().list(
            calendarId=req.email,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        result = []
        for event in events:
            result.append({
                "summary": event.get('summary'),
                "start": event['start'].get('dateTime', event['start'].get('date')),
                "end": event['end'].get('dateTime', event['end'].get('date'))
            })

        return {"events": result}

    except Exception as e:
        return {"error": str(e)}
    
@app.post("/get-multi-calendar")
async def get_multi_calendar_events(req: MultiCalendarRequest):
    try:
        date = datetime.datetime.strptime(req.date, "%Y-%m-%d")
        start_of_day = date.replace(hour=0, minute=0, second=0, tzinfo=pytz.UTC)
        end_of_day = date.replace(hour=23, minute=59, second=59, tzinfo=pytz.UTC)

        # สร้างฟังก์ชันย่อยเพื่อดึงข้อมูลปฏิทินของแต่ละอีเมล
        async def fetch_calendar_data(email):
            try:
                # สร้าง event loop เพื่อให้สามารถรันฟังก์ชันที่ไม่ใช่ async ในบริบทของ async
                loop = asyncio.get_event_loop()
                # ใช้ run_in_executor เพื่อเรียกใช้ฟังก์ชันที่ blocking ในแบบ non-blocking
                service = await loop.run_in_executor(None, get_calendar_service, email)
                
                # เรียกใช้ API แบบ non-blocking
                events_result = await loop.run_in_executor(
                    None,
                    lambda: service.events().list(
                        calendarId=email,
                        timeMin=start_of_day.isoformat(),
                        timeMax=end_of_day.isoformat(),
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()
                )

                events = events_result.get('items', [])
                time_slots = []

                for event in events:
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    end = event['end'].get('dateTime', event['end'].get('date'))

                    if 'T' in start and 'T' in end:
                        start_time = start.split('T')[1][:5]
                        end_time = end.split('T')[1][:5]
                        time_slots.append(f"{start_time}-{end_time}")

                return email, {
                    "busy_slots": {
                        "date": date.strftime("%d/%m/%Y"),
                        "time_slots": time_slots
                    }
                }
            except Exception as e:
                return email, {"error": str(e)}

        # สร้าง tasks สำหรับการดึงข้อมูลแต่ละอีเมลพร้อมกัน
        tasks = [fetch_calendar_data(email) for email in req.emails]
        
        # รอให้ทุก task ทำงานเสร็จ
        results = await asyncio.gather(*tasks)
        
        # รวมผลลัพธ์เข้าด้วยกัน
        users = {email: data for email, data in results}

        return {"users": users}

    except Exception as e:
        return {"error": str(e)}



@app.post("/calculate_available_slots")
async def calculate_available_slots(data: Dict[str, Any] = Body(...)):
    """Calculate available time slots for meetings with improved performance"""
    date_thai = data.get("date")
    if not date_thai:
        raise HTTPException(status_code=400, detail="Date parameter is required")
    
    # แปลงวันที่จากรูปแบบไทย (วว/ดด/25XX) เป็นรูปแบบสากล (YYYY-MM-DD)
    date_iso = convert_thai_to_iso_date(date_thai)
    
    # รายการอีเมลที่ต้องการตรวจสอบ (อาจรับจาก config หรือฐานข้อมูล)
    emails = ["nonlaneeud@gmail.com", "panupongpr3841@gmail.com"]  # ปรับตามอีเมลที่คุณต้องการใช้งาน
    
    try:
        # เรียกใช้ function ที่ปรับปรุงแล้วเพื่อดึงข้อมูลปฏิทิน
        req = MultiCalendarRequest(emails=emails, date=date_iso)
        calendar_response = await get_multi_calendar_events(req)
        
        # ตรวจสอบว่ามี error หรือไม่
        if "error" in calendar_response:
            raise HTTPException(status_code=500, detail=f"Calendar API error: {calendar_response['error']}")
        
        calendar_data = calendar_response
        
        # สร้างช่วงเวลาทำงานตั้งแต่ 9:00 ถึง 18:00 ทุก 30 นาที
        working_hours = []
        for hour in range(9, 18):
            working_hours.append(f"{hour:02d}:00-{hour:02d}:30")
            working_hours.append(f"{hour:02d}:30-{hour+1:02d}:00")
        
        # เตรียมข้อมูลเวลาไม่ว่างของแต่ละอีเมลในรูปแบบที่ง่ายต่อการตรวจสอบ
        # เก็บเฉพาะอีเมลที่ไม่มี error
        valid_participants = []
        email_busy_times = {}
        
        for email, user_data in calendar_data.get("users", {}).items():
            if "error" in user_data:
                print(f"Error for {email}: {user_data['error']}")
                continue
                
            valid_participants.append(email)
            busy_slots = user_data.get("busy_slots", {})
            busy_time_slots = busy_slots.get("time_slots", [])
            
            # แปลงช่วงเวลาไม่ว่างให้เป็นรูปแบบที่ง่ายต่อการค้นหา
            email_busy_times[email] = set()
            for busy_slot in busy_time_slots:
                busy_start, busy_end = busy_slot.split('-')
                email_busy_times[email].add((busy_start, busy_end))
        
        # ฟังก์ชันเพื่อตรวจสอบว่าช่วงเวลาใดว่างสำหรับทุกคน
        async def check_slot_availability(time_slot):
            slot_start, slot_end = time_slot.split('-')
            
            # ตรวจสอบทุกอีเมลพร้อมกัน
            for email in valid_participants:
                # ตรวจสอบการทับซ้อนกับช่วงเวลาที่ไม่ว่าง
                for busy_start, busy_end in email_busy_times[email]:
                    # ตรวจสอบการทับซ้อน
                    if slot_start < busy_end and slot_end > busy_start:
                        return None  # ช่วงเวลานี้ไม่ว่าง
            
            # ถ้าผ่านการตรวจสอบทั้งหมด แสดงว่าช่วงเวลานี้ว่างสำหรับทุกคน
            return {
                "date": date_thai,
                "time": time_slot,
                "participants": valid_participants
            }
        
        # สร้าง tasks เพื่อตรวจสอบทุกช่วงเวลาพร้อมกัน
        tasks = [check_slot_availability(slot) for slot in working_hours]
        results = await asyncio.gather(*tasks)
        
        # กรองเฉพาะผลลัพธ์ที่ไม่เป็น None (ช่วงเวลาที่ว่าง)
        available_slots = [slot for slot in results if slot is not None]
        
        return {"available_slots": available_slots}
    
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

@app.post("/receive_manager_info")
async def receive_manager_info(payload: Dict[str, Any]):
    print("📦 รับข้อมูล Manager:", payload)
    return {"status": "received"}

@app.post("/create_meeting")
async def create_meeting(meeting_data: Dict[str, Any] = Body(...)):
    """Create a new meeting"""
    required_fields = ["date", "time", "participants"]
    for field in required_fields:
        if field not in meeting_data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
    
    # Add additional meeting info
    meeting_info = {
        "date": meeting_data["date"],
        "time": meeting_data["time"],
        "duration": "30 นาที",  # Default to 30 minutes
        "participants": meeting_data["participants"],
        "created_at": datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "created_by": meeting_data.get("created_by", "system")
    }
    
    # Add meeting to database
    meetings.append(meeting_info)
    
    return {"status": "success", "meeting": meeting_info}


if __name__ == "__main__":
    uvicorn.run("data_service:app", host="localhost", port=8000, reload=True)