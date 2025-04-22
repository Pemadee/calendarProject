# Standard library
import json
import os
import shutil
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
# Third-party libraries
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pandas as pd
from pydantic import BaseModel
import uvicorn

# Local application
from lineChatbot import *

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
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid'
]
#file เก็บข้อมูล client secret ของ OAuth
CLIENT_SECRET_FILE = os.getenv("CLIENT_SECRET_FILE")
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

# โมเดลสำหรับรับข้อมูลผู้ใช้หลายคน จากข้อมูลใน excel
class ManagerRecruiter(BaseModel):
    file_path: Optional[str] = None
    location: str
    english_min: float
    exp_kind: str
    age_key: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None

# โมเดลสำหรับรับข้อมูล Manger Recruiter
class getManagerRecruiter(BaseModel):
    location: str 
    english_min: int
    exp_kind: str
    age_key: str
    
# โมเดลสำหรับรับข้อมูล Manger Recruiter แบบกลุ่ม
class combMangerRecruiter(BaseModel):
    users: List[getManagerRecruiter] #List ของ UserCalendar
   



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
                    creds.refresh(GoogleRequest())
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
            creds.refresh(GoogleRequest())
        else:
            # สร้าง flow แบบ web application
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            
            # กำหนด redirect_uri อย่างชัดเจน
            base_url = os.environ.get('BASE_URL')
            flow.redirect_uri = f"{base_url}/oauth2callback"
            
            # สร้าง authorization URL พร้อมกำหนด state ให้เก็บ email
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                prompt='consent',
                include_granted_scopes='true',
                state=user_email  # เก็บ email ใน state เพื่อใช้อ้างอิงตอน callback
            )
            
            # ส่งกลับ URL และสถานะที่ต้องการการยืนยันตัวตน
            return {
                "requires_auth": True,
                "auth_url": auth_url,
                "redirect_uri": flow.redirect_uri
            }
        
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

def add_location_column(df):
    """
    เติมคอลัมน์ Location ให้กับตาราง (df)
    โดยอาศัยแถวตัวคั่นที่ช่อง Email เป็น NaN
    """
    curr_loc = None          # เก็บ location ปัจจุบัน
    loc_list = []            # จะกลายเป็นคอลัมน์ใหม่

    for _, row in df.iterrows():
        if pd.isna(row['Email']):        # แถวตัวคั่น (ไม่มีอีเมล)
            curr_loc = row['Name']       # อัปเดต location
        loc_list.append(curr_loc)        # เติม loc ของแถวนั้น

    df['Location'] = loc_list
    return df

def get_people(file_path,
               location=None,
               english_min=None,
               exp_kind=None,
               age_key=None):
    """
    อ่านไฟล์ Excel แล้วกรองข้อมูลตามเงื่อนไข
    พร้อมคืนชื่อ‑อีเมล‑สถานที่ ของชีต M และ R
    """

    # ---------- 1) โหลดทุกชีต ----------
    sheets = pd.read_excel(file_path, sheet_name=None)
    df_M = sheets['M'].copy()
    df_R = sheets['R'].copy()

    # ---------- 2) เปลี่ยนชื่อคอลัมน์แรกเป็น Name ----------
    df_M.rename(columns={df_M.columns[0]: 'Name'}, inplace=True)
    df_R.rename(columns={df_R.columns[0]: 'Name'}, inplace=True)

    # ---------- 3) เติมคอลัมน์ Location ----------
    df_M = add_location_column(df_M)
    df_R = add_location_column(df_R)

    # ---------- 4) ตัดแถวตัวคั่น (Email เป็น NaN) ----------
    df_M = df_M[df_M['Email'].notna()].reset_index(drop=True)
    df_R = df_R[df_R['Email'].notna()].reset_index(drop=True)

    # ---------- 5) กรองตาม Location ----------
    if location:
        df_M = df_M[df_M['Location'].str.contains(location, case=False, na=False)]
        df_R = df_R[df_R['Location'].str.contains(location, case=False, na=False)]

    # ---------- 6) กรอง English ----------
    if english_min is not None and 'English' in df_M.columns:
        df_M['Eng_num'] = pd.to_numeric(df_M['English'], errors='coerce')
        df_M = df_M[df_M['Eng_num'] >= english_min]

    # ---------- 7) กรอง Experience ----------
    if exp_kind and 'Experience' in df_M.columns:
        exp_low = df_M['Experience'].str.lower()
        if exp_kind.lower() == 'strong':
            cond = exp_low.str.contains('strong', na=False) & \
                   ~exp_low.str.contains('non', na=False)
            df_M = df_M[cond]
        else:
            df_M = df_M[exp_low.str.contains(exp_kind.lower(), na=False)]

    # ---------- 8) กรอง Age ----------
    if age_key and 'Age' in df_M.columns:
        df_M = df_M[df_M['Age'].str.contains(age_key, case=False, na=False)]

    # ---------- 9) เตรียมผลลัพธ์ (dict → list ของ dict) ----------
    list_M = (
        df_M[['Name', 'Email', 'Location']]
        .to_dict(orient='records')
    )
    list_R = (
        df_R[['Name', 'Email', 'Location']]
        .to_dict(orient='records')
    )

    return {'M': list_M, 'R': list_R}

def get_email(file_path,
               location=None,
               english_min=None,
               exp_kind=None,
               age_key=None):
    """
    อ่านไฟล์ Excel แล้วกรองข้อมูลตามเงื่อนไข
    คืนข้อมูลในรูปแบบ list ของ dict ที่มีแค่ email
    """

    # ---------- 1) โหลดทุกชีต ----------
    sheets = pd.read_excel(file_path, sheet_name=None)
    df_M = sheets['M'].copy()
    df_R = sheets['R'].copy()

    # ---------- 2) เปลี่ยนชื่อคอลัมน์แรกเป็น Name ----------
    df_M.rename(columns={df_M.columns[0]: 'Name'}, inplace=True)
    df_R.rename(columns={df_R.columns[0]: 'Name'}, inplace=True)

    # ---------- 3) เติมคอลัมน์ Location ----------
    df_M = add_location_column(df_M)
    df_R = add_location_column(df_R)

    # ---------- 4) ตัดแถวตัวคั่น (Email เป็น NaN) ----------
    df_M = df_M[df_M['Email'].notna()].reset_index(drop=True)
    df_R = df_R[df_R['Email'].notna()].reset_index(drop=True)

    # ---------- 5) กรองตาม Location ----------
    if location:
        df_M = df_M[df_M['Location'].str.contains(location, case=False, na=False)]
        df_R = df_R[df_R['Location'].str.contains(location, case=False, na=False)]

    # ---------- 6) กรอง English ----------
    if english_min is not None and 'English' in df_M.columns:
        df_M['Eng_num'] = pd.to_numeric(df_M['English'], errors='coerce')
        df_M = df_M[df_M['Eng_num'] >= english_min]

    # ---------- 7) กรอง Experience ----------
    if exp_kind and 'Experience' in df_M.columns:
        exp_low = df_M['Experience'].str.lower()
        if exp_kind.lower() == 'strong':
            cond = exp_low.str.contains('strong', na=False) & \
                   ~exp_low.str.contains('non', na=False)
            df_M = df_M[cond]
        else:
            df_M = df_M[exp_low.str.contains(exp_kind.lower(), na=False)]

    # ---------- 8) กรอง Age ----------
    if age_key and 'Age' in df_M.columns:
        df_M = df_M[df_M['Age'].str.contains(age_key, case=False, na=False)]

    # ---------- 9) สร้าง list ของ dict ในรูปแบบที่ต้องการ ----------
    result = []
    
    # เพิ่มอีเมลจาก M list
    for _, row in df_M.iterrows():
        result.append({"email": row['Email']})
    
    # เพิ่มอีเมลจาก R list
    for _, row in df_R.iterrows():
        result.append({"email": row['Email']})
    
    return result


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
    """ดึงข้อมูลกิจกรรมของผู้ใช้หลายคน (เฉพาะผู้ใช้ที่ยืนยันตัวตนแล้ว)"""
    results = []
    users_without_auth = []
    
    # ใช้ฟังก์ชัน get_email เพื่อรับรายชื่ออีเมลผู้ใช้
    users_list = get_email(
        file_path='TESTt.xlsx',
        location=request.location,
        english_min=request.english_min,
        exp_kind=request.exp_kind,
        age_key=request.age_key
    )
    
    # ตรวจสอบผู้ใช้แต่ละคนว่าได้ยืนยันตัวตนแล้วหรือไม่
    for user_info in users_list:
        email = user_info["email"]
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
                
                print(f"กำลังดึงข้อมูลสำหรับ {email} จาก {time_min} ถึง {time_max}")
                
                # ดึงข้อมูลกิจกรรม
                events_result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                print(f"พบ {len(events)} กิจกรรมสำหรับ {email}")
                
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
                    'email': email,
                    'calendar_id': calendar_id,
                    'events': formatted_events,
                    'is_authenticated': True
                })
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ {email}: {str(e)}")
                results.append({
                    'email': email,
                    'calendar_id': calendar_id,
                    'events': [],
                    'error': str(e),
                    'is_authenticated': True
                })
        else:
            # ถ้ายังไม่มี token ที่ใช้งานได้
            users_without_auth.append(email)
            results.append({
                'email': email,
                'calendar_id': calendar_id,
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
            #     emails.append(email)
        
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

@app.post("/getManagerRecruiter")
def get_multiple_users_events(body: getManagerRecruiter):
    try:
        people = get_people(
            file_path='TESTt.xlsx',          
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





if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"เริ่มต้น FastAPI บน port {port}...")
    print(f"เข้าถึง API documentation ได้ที่: http://localhost:{port}/docs")
    print(f"กำหนด redirect URI สำหรับ OAuth2: {REDIRECT_URI} (port: {AUTH_PORT})")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)