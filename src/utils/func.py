# 1. Standard Library Imports
import os
import smtplib
import sys
import threading
import time as timeTest
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, time, timedelta
from datetime import datetime, timezone, time, timedelta

# 2. Third-Party Library Imports
import pandas as pd
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import get_as_dataframe

# 3. Local Application Imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from config import CLIENT_ID, CLIENT_SECRET, SCOPES
from src.api.endpoints import *
from src.config import *
from utils.token_db import *

base_url = os.environ.get('BASE_URL')
# EMAIL_SENDER = os.getenv("EMAIL_to_SEND_MESSAGE")
# EMAIL_PASSWORD = os.getenv("PASSWORD_EMAIL")
email_locks = defaultdict(threading.Lock) # สร้าง lock แยกตามอีเมล

spreadsheet_id = os.environ.get('SPREADSHEET_ID')
credentialsGsheet = os.environ.get('CREDENTIALS_GOOGLE_SHEET')
scopeGsheet = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
credentialsGsheet = ServiceAccountCredentials.from_json_keyfile_name(credentialsGsheet, scopeGsheet)
client = gspread.authorize(credentialsGsheet)




def is_token_valid(user_email: str) -> bool:
    """ตรวจสอบว่า token ของผู้ใช้ยังใช้งานได้หรือไม่ (เช็คจาก DB)"""
    t1 = timeTest.time()
    token_entry = get_token(user_email)
    if not token_entry:
        print(f"❌ ไม่พบ token ในระบบสำหรับ {user_email} (ใช้เวลา {timeTest.time() - t1} s)")
        return False

    creds = Credentials(
        token=token_entry.access_token,
        refresh_token=token_entry.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES
    )

    if creds.valid:
        print(f"✅ Token ยังใช้งานได้สำหรับ {user_email}(ใช้เวลา {timeTest.time() - t1} s)")
        return True

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleRequest())
            update_token(
                email=user_email,
                access_token=creds.token,
                refresh_token=creds.refresh_token,
                expiry=creds.expiry
            )
            print(f"🔄 รีเฟรช token สำเร็จสำหรับ {user_email}")
            return True
        except Exception as e:
            print(f"❌ รีเฟรช token ไม่สำเร็จ: {str(e)}")
            return False

    print(f"❌ Token หมดอายุและไม่มี refresh_token สำหรับ {user_email}")
    return False

def get_credentials(user_email: str):
    """รับ credentials สำหรับการเข้าถึง Google Calendar API"""
    creds = None
    
    # ดึงข้อมูล token จาก DB
    token_entry = get_token(user_email)
    
    if token_entry:
        try:
            creds = Credentials(
                token=token_entry.access_token,
                refresh_token=token_entry.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                scopes=SCOPES
            )
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการโหลด token: {str(e)}")

    # ถ้าไม่มี token หรือไม่ valid → ต้องพิจารณา refresh หรือ auth ใหม่

    # ถ้าไม่มี token หรือไม่ valid → ต้องพิจารณา refresh หรือ auth ใหม่
    if not creds or not creds.valid:
        if creds:
            print(f"😐 Token expired: {creds.expired}, Has refresh_token: {bool(creds.refresh_token)}")
        if creds and creds.expired and creds.refresh_token:
            try:
                with email_locks[user_email]:
                    print(f"🔄 พยายามรีเฟรช token สำหรับ {user_email}")
                    creds.refresh(GoogleRequest())
                if creds.refresh_token:
                    # บันทึก token ที่รีเฟรชแล้วลง DB
                    update_token(
                        email=user_email,
                        access_token=creds.token,
                        refresh_token=creds.refresh_token,
                        expiry=creds.expiry
                    )
                    print(f"✅ รีเฟรช token สำเร็จสำหรับ {user_email}")
                else:
                    print("⚠️ ไม่มี refresh_token หลัง refresh — อาจหมดสิทธิ์")
            except Exception as e:
                if 'invalid_grant' in str(e):
                    print("💥 invalid_grant — เวลาระบบคลาด หรือ token ใช้ไม่ได้")
                return _get_auth_redirect(user_email)
        else:
            print("❌ Token ใช้ไม่ได้ และไม่มี refresh_token เลย")
            return _get_auth_redirect(user_email)
            
    return creds

def _get_auth_redirect(user_email: str):
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    flow.redirect_uri = f"{base_url}/oauth2callback"
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        prompt='consent',
        include_granted_scopes='true',
        state=user_email
    )
    return {
        "requires_auth": True,
        "auth_url": auth_url,
        "redirect_uri": flow.redirect_uri
    }

def get_calendar_events(user_email: str, calendar_id: str, start_date: str, end_date: str):
    """ดึงข้อมูลกิจกรรมจาก Google Calendar"""
    try:
        # รับ credentials
        creds = refresh_token_safe(user_email)
        if not creds:
            if not creds:
                return {
                    "email": user_email,
                    "calendar_id": calendar_id,
                    "events": [],
                    "auth_status": "expired"
                }
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

# def get_people(location=None,
#                      english_min=None,
#                      exp_kind=None,
#                      age_key=None):
#     """
#     อ่านข้อมูลจาก Google Sheet แล้วกรองข้อมูลตามเงื่อนไข
#     พร้อมคืนชื่อ‑อีเมล‑สถานที่ ของชีต M และ R
#     """
    
    
    
#     # ---------- 1) เชื่อมต่อกับ Google Sheets API ----------
#     # เปิดสเปรดชีตจาก ID
#     sheet = client.open_by_key(spreadsheet_id)
    
#     # ---------- 2) โหลดทุกชีต ----------
#     worksheet_M = sheet.worksheet('M')
#     worksheet_R = sheet.worksheet('R')
    
#     # แปลงข้อมูลเป็น DataFrame
#     df_M = get_as_dataframe(worksheet_M, evaluate_formulas=True, skiprows=0)
#     df_R = get_as_dataframe(worksheet_R, evaluate_formulas=True, skiprows=0)
    
#     # กำจัดแถวที่เป็น NaN ทั้งหมด (แถวว่างท้ายตาราง)
#     df_M = df_M.dropna(how='all').reset_index(drop=True)
#     df_R = df_R.dropna(how='all').reset_index(drop=True)

#     # ---------- 3) เปลี่ยนชื่อคอลัมน์แรกเป็น Name ----------
#     df_M.rename(columns={df_M.columns[0]: 'Name'}, inplace=True)
#     df_R.rename(columns={df_R.columns[0]: 'Name'}, inplace=True)

#     # ---------- 4) เติมคอลัมน์ Location ----------
#     df_M = add_location_column(df_M)
#     df_R = add_location_column(df_R)

#     # ---------- 5) ตัดแถวตัวคั่น (Email เป็น NaN) ----------
#     df_M = df_M[df_M['Email'].notna()].reset_index(drop=True)
#     df_R = df_R[df_R['Email'].notna()].reset_index(drop=True)

#     # ---------- 6) กรองตาม Location ----------
#     if location:
#         df_M = df_M[df_M['Location'].str.contains(location, case=False, na=False)]
#         df_R = df_R[df_R['Location'].str.contains(location, case=False, na=False)]

#     # ---------- 7) กรอง English ----------
#     if english_min is not None and 'English' in df_M.columns:
#         df_M['Eng_num'] = pd.to_numeric(df_M['English'], errors='coerce')
#         df_M = df_M[df_M['Eng_num'] >= english_min]

#     # ---------- 8) กรอง Experience ----------
#     if exp_kind and 'Experience' in df_M.columns:
#         exp_low = df_M['Experience'].str.lower()
#         if exp_kind.lower() == 'strong':
#             cond = exp_low.str.contains('strong', na=False) & \
#                    ~exp_low.str.contains('non', na=False)
#             df_M = df_M[cond]
#         else:
#             df_M = df_M[exp_low.str.contains(exp_kind.lower(), na=False)]
#     # ---------- 8) กรอง Age ----------
#     if age_key and 'Age' in df_M.columns:
#         try:
#             age_value = int(age_key)

#             age_series = df_M['Age'].astype(str).str.lower()

#             # กรอง Age == 'all'
#             all_mask = age_series == 'all'

#             # กรอง Age == 'up ot 35' ถ้า age_key < 35
#             up_ot_mask = (age_series == 'up ot 35') & (age_value < 35)

#             # รวมทั้งสองเงื่อนไข
#             final_mask = all_mask | up_ot_mask

#             df_M = df_M[final_mask]

#         except (ValueError, TypeError):
#             print(f"Warning: age_key '{age_key}' is not a valid number")


    
    
#     # ---------- 10) เตรียมผลลัพธ์ (dict → list ของ dict) ----------
#     list_M = (
#         df_M[['Name', 'Email', 'Location']]
#         .to_dict(orient='records')
#     )
#     list_R = (
#         df_R[['Name', 'Email', 'Location']]
#         .to_dict(orient='records')
#     )
    
#     return {'M': list_M, 'R': list_R}

def get_people(location=None):
    """
    อ่านข้อมูลจาก Google Sheet แล้วกรองข้อมูลตามเงื่อนไข
    พร้อมคืนชื่อ‑อีเมล‑สถานที่ ของชีต M และ R
    """
 
    # ---------- 1) เชื่อมต่อกับ Google Sheets API ----------
    # เปิดสเปรดชีตจาก ID
    sheet = client.open_by_key(spreadsheet_id)
    
    # ---------- 2) โหลดทุกชีต ----------
    worksheet_R = sheet.worksheet('R')
    
    # แปลงข้อมูลเป็น DataFrame
    df_R = get_as_dataframe(worksheet_R, evaluate_formulas=True, skiprows=0)
    
    # กำจัดแถวที่เป็น NaN ทั้งหมด (แถวว่างท้ายตาราง)
    df_R = df_R.dropna(how='all').reset_index(drop=True)

    # ---------- 3) เปลี่ยนชื่อคอลัมน์แรกเป็น Name ----------
    df_R.rename(columns={df_R.columns[0]: 'Name'}, inplace=True)

    # ---------- 4) เติมคอลัมน์ Location ----------
    df_R = add_location_column(df_R)

    # ---------- 5) ตัดแถวตัวคั่น (Email เป็น NaN) ----------
    df_R = df_R[df_R['Email'].notna()].reset_index(drop=True)

    # ---------- 6) กรองตาม Location ----------
    if location:
        df_R = df_R[df_R['Location'].str.contains(location, case=False, na=False)]


    # ---------- 10) เตรียมผลลัพธ์ (dict → list ของ dict) ----------
    list_R = (
        df_R[['Name', 'Email', 'Location']]
        .to_dict(orient='records')
    )
    
    return {'R': list_R}

def parse_event_time(time_str):
    """
    แปลงเวลาจาก string เป็น datetime object
    """
    if 'T' in time_str:
        # กรณีมีข้อมูลเวลา (dateTime)
        if time_str.endswith('Z'):
            return datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        else:
            return datetime.fromisoformat(time_str)
    else:
        # กรณีมีแต่วันที่ (date)
        dt = datetime.strptime(time_str, '%Y-%m-%d')
        return dt.replace(tzinfo=timezone.utc)

def get_day_suffix(day):
    if 11 <= day <= 13:
        return 'th'
    last_digit = day % 10
    if last_digit == 1:
        return 'st'
    elif last_digit == 2:
        return 'nd'
    elif last_digit == 3:
        return 'rd'
    else:
        return 'th'

def refresh_token_safe(user_email: str):
    token_entry = get_token(user_email)
    if not token_entry:
        print(f"❌ ไม่พบ token ในระบบสำหรับ {user_email}")
        return None

    creds = Credentials(
        token=token_entry.access_token,
        refresh_token=token_entry.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES
    )

    # ตรวจสอบว่า expiry มีค่าหรือไม่ก่อนเปรียบเทียบ
    need_refresh = False
    if not creds.expiry:
        need_refresh = True
        print(f"⚠️ Token ของ {user_email} ไม่มีค่า expiry → ต้องรีเฟรช")
    elif creds.expired:
        need_refresh = True
        print(f"⚠️ Token ของ {user_email} หมดอายุแล้ว → ต้องรีเฟรช")
    elif (creds.expiry - datetime.utcnow()).total_seconds() < 300:
        need_refresh = True
        seconds_left = (creds.expiry - datetime.utcnow()).total_seconds()
        print(f"⚠️ Token ของ {user_email} จะหมดใน {int(seconds_left)} วินาที → ต้องรีเฟรช")
    
    if need_refresh:
        try:
            creds.refresh(GoogleRequest())
            update_token(
                email=user_email,
                access_token=creds.token,
                refresh_token=creds.refresh_token,
                expiry=creds.expiry
            )
            print(f"✅ รีเฟรช token สำเร็จสำหรับ {user_email}")
        except Exception as e:
            print(f"❌ รีเฟรชล้มเหลว: {str(e)}")
            return None
    else:
        print(f"✅ Token ของ {user_email} ยังใช้ได้")

    return creds

def find_emails_from_name_pair(name_pair, location):
    """
    รับชื่อในรูปแบบ "name1-name2" และ location เพื่อค้นหาอีเมลจาก Excel
    
    Args:
        name_pair (str): ชื่อในรูปแบบ "name1-name2"
        location (str): สถานที่ เช่น "Silom", "Asoke" เป็นต้น
        
    Returns:
        dict: ข้อมูลอีเมลที่ค้นพบ ประกอบด้วย name1_email, name2_email, name1, name2
    """
    # อ่านไฟล์ Excel
    try:
        # ปรับ path ตามที่เก็บไฟล์จริง
        
        sheet = client.open_by_key(spreadsheet_id)
        worksheet_M = sheet.worksheet('M')
        worksheet_R = sheet.worksheet('R')

        

        
        # แยกชื่อ
        try:
            name1, name2 = name_pair.split('-')
        except ValueError:
            raise ValueError(f"รูปแบบชื่อไม่ถูกต้อง: {name_pair} (ต้องเป็น 'name1-name2')")
        

        df_m = get_as_dataframe(worksheet_M, evaluate_formulas=True, skiprows=0)
        df_r = get_as_dataframe(worksheet_R, evaluate_formulas=True, skiprows=0)
        
        # ค้นหาในชีต M
        email1 = None
        for i in range(len(df_m)):
            # ตรวจสอบว่าเป็นหัวข้อ location ที่ต้องการหรือไม่
            if df_m.iloc[i, 0] == location:
                # ค้นหาในแถวถัดๆ ไปจนกว่าจะเจอ location ถัดไป
                j = i + 1
                while j < len(df_m) and not pd.isna(df_m.iloc[j, 0]) and not df_m.iloc[j, 0] in ["Silom", "Asoke", "Phuket", "Pattaya", "Samui", "Huahin", "Chiangmai"]:
                    if df_m.iloc[j, 0] == name1:
                        # พบชื่อที่ต้องการ ค้นหาอีเมลในคอลัมน์ Email
                        if 'Email' in df_m.columns:
                            email_col_idx = df_m.columns.get_loc('Email')
                            email1 = df_m.iloc[j, email_col_idx]
                            if pd.isna(email1):
                                raise ValueError(f"พบชื่อ {name1} แล้ว แต่ไม่มีข้อมูลอีเมล")
                            break
                    j += 1
                break
        
        if email1 is None:
            raise ValueError(f"ไม่พบอีเมลสำหรับชื่อ {name1} ในพื้นที่ {location} ในชีต M")
        
        # ค้นหาในชีต R
        email2 = None
        for i in range(len(df_r)):
            # ตรวจสอบว่าเป็นหัวข้อ location ที่ต้องการหรือไม่
            if df_r.iloc[i, 0] == location:
                # ค้นหาในแถวถัดๆ ไปจนกว่าจะเจอ location ถัดไป
                j = i + 1
                while j < len(df_r) and not pd.isna(df_r.iloc[j, 0]) and not df_r.iloc[j, 0] in ["Silom", "Asoke", "Phuket", "Pattaya", "Samui", "Huahin", "Chiangmai"]:
                    if df_r.iloc[j, 0] == name2:
                        # พบชื่อที่ต้องการ ค้นหาอีเมลในคอลัมน์ Email
                        if 'Email' in df_r.columns:
                            email_col_idx = df_r.columns.get_loc('Email')
                            email2 = df_r.iloc[j, email_col_idx]
                            if pd.isna(email2):
                                raise ValueError(f"พบชื่อ {name2} แล้ว แต่ไม่มีข้อมูลอีเมล")
                            break
                    j += 1
                break
        
        if email2 is None:
            raise ValueError(f"ไม่พบอีเมลสำหรับชื่อ {name2} ในพื้นที่ {location} ในชีต R")
        
        # คืนค่าเป็น dict ที่มีข้อมูลที่ต้องการทั้งหมด
        return {
            "name1_email": email1,
            "name2_email": email2,
            "name1": name1,  # เพิ่มชื่อโดยตรง ไม่ใช่อยู่ใน list
            "name2": name2   # เพิ่มชื่อโดยตรง ไม่ใช่อยู่ใน list
        }
        
    except Exception as e:
        raise Exception(f"เกิดข้อผิดพลาดในการอ่านข้อมูลจาก Excel: {str(e)}")

def convert_to_iso_format(date, time):
    """
    แปลงข้อมูลวันที่และเวลาจากรูปแบบง่ายๆ เป็นรูปแบบ ISO
    
    Args:
        date (str): วันที่ในรูปแบบ "YYYY-MM-DD"
        time (str): เวลาในรูปแบบ "HH:MM-HH:MM"
        
    Returns:
        tuple: (start_time, end_time) ในรูปแบบ ISO format
    """
    try:
        # แยกเวลาเริ่มต้นและสิ้นสุด
        start_time, end_time = time.split('-')
        
        # สร้าง datetime objects
        start_datetime = f"{date}T{start_time}:00+07:00"
        end_datetime = f"{date}T{end_time}:00+07:00"
        
        return start_datetime, end_datetime
    except Exception as e:
        raise ValueError(f"รูปแบบวันที่หรือเวลาไม่ถูกต้อง: {str(e)}")




def find_email_from_name(name, location):
    """
    รับชื่อของ name2 และ location เพื่อค้นหาอีเมลจาก Google Sheet
    
    Args:
        name (str): ชื่อของ name2
        location (str): สถานที่ เช่น "Silom", "Asoke" เป็นต้น
        
    Returns:
        dict: ข้อมูลอีเมลและชื่อที่ค้นพบ ประกอบด้วย email, name
    """
    try:
        # เชื่อมต่อกับ Google Sheet
        sheet = client.open_by_key(spreadsheet_id)
        worksheet_R = sheet.worksheet('R')  # ค้นหาในชีต R เท่านั้น
        
        df_r = get_as_dataframe(worksheet_R, evaluate_formulas=True, skiprows=0)
        
        # ค้นหาในชีต R
        email = None
        for i in range(len(df_r)):
            # ตรวจสอบว่าเป็นหัวข้อ location ที่ต้องการหรือไม่
            if df_r.iloc[i, 0] == location:
                # ค้นหาในแถวถัดๆ ไปจนกว่าจะเจอ location ถัดไป
                j = i + 1
                while j < len(df_r) and not pd.isna(df_r.iloc[j, 0]) and not df_r.iloc[j, 0] in ["Silom", "Asoke", "Phuket", "Pattaya", "Samui", "Huahin", "Chiangmai"]:
                    if df_r.iloc[j, 0] == name:
                        # พบชื่อที่ต้องการ ค้นหาอีเมลในคอลัมน์ Email
                        if 'Email' in df_r.columns:
                            email_col_idx = df_r.columns.get_loc('Email')
                            email = df_r.iloc[j, email_col_idx]
                            if pd.isna(email):
                                raise ValueError(f"พบชื่อ {name} แล้ว แต่ไม่มีข้อมูลอีเมล")
                            break
                    j += 1
                break
        
        if email is None:
            raise ValueError(f"ไม่พบอีเมลสำหรับชื่อ {name} ในพื้นที่ {location} ในชีต R")
        
        # คืนค่าเป็น dict ที่มีข้อมูลที่ต้องการ
        return {
            "email": email,
            "name": name
        }
        
    except Exception as e:
        raise Exception(f"เกิดข้อผิดพลาดในการอ่านข้อมูลจาก Google Sheet: {str(e)}")

#========================================== fot API date, timeslot, pairs ======================================
import asyncio
def check_recruiter_availability(user_info, date, time_min, time_max):
    """
    เช็ค token และความว่างของ recruiter ในวันที่กำหนด
    """
    email = user_info["Email"]
    name = user_info["Name"]
    calendar_id = email
    
    # เช็ค token validity
    if not is_token_valid(email):
        print(f"ผู้ใช้ {email} ยังไม่ได้ยืนยันตัวตน")
        return None
    
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
        
        # เช็คว่ามีช่วงเวลาว่างหรือไม่ (เช็คเบื้องต้นในช่วง 9-18 น.)
        has_available_slots = False
        for hour in range(9, 18):
            for minute in [0, 30]:
                slot_start = datetime.combine(date, time(hour, minute)).astimezone(timezone.utc)
                slot_end = (slot_start + timedelta(minutes=30)).astimezone(timezone.utc)
                
                if is_available(events, slot_start, slot_end):
                    has_available_slots = True
                    break
            if has_available_slots:
                break
        
        # ถ้าว่าง ให้ return ข้อมูล recruiter
        if has_available_slots:
            return {
                'email': email,
                'name': name
            }
        else:
            return None
            
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ R: {email}: {str(e)}")
        return None
# เพิ่มฟังก์ชันสำหรับ concurrent token checking
def check_token_and_fetch_events(user_info, time_min, time_max):
    """
    เช็ค token และดึง events ในฟังก์ชันเดียว
    """
    email = user_info["Email"]
    name = user_info["Name"]
    calendar_id = email
    
    # เช็ค token validity
    if not is_token_valid(email):
        print(f"ผู้ใช้ {email} ยังไม่ได้ยืนยันตัวตน")
        return None
    
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
        
        service = build('calendar', 'v3', credentials=creds)
        
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        return {
            'email': email,
            'name': name,
            'events': events
        }
        
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูลสำหรับ R: {email}: {str(e)}")
        return None

def is_available(events, start_time, end_time):
    """
    ตรวจสอบว่าช่วงเวลาที่ระบุว่างหรือไม่
    Args:
        events: รายการกิจกรรมของผู้ใช้
        start_time: เวลาเริ่มต้นของช่วงเวลาที่ต้องการตรวจสอบ
        end_time: เวลาสิ้นสุดของช่วงเวลาที่ต้องการตรวจสอบ
    Returns:
        bool: True หากว่าง, False หากไม่ว่าง
    """
    for event in events:
        # ข้ามกิจกรรมที่ถูกยกเลิก
        if event.get('status') == 'cancelled':
            continue
        
        # ดึงเวลาเริ่มต้นและสิ้นสุดของกิจกรรม
        event_start_str = event.get('start', {}).get('dateTime')
        event_end_str = event.get('end', {}).get('dateTime')
        
        # ตรวจสอบว่าเป็นกิจกรรมที่มีช่วงเวลาหรือไม่
        if not event_start_str or not event_end_str:
            continue
        
        # แปลงเป็น datetime object
        event_start = datetime.fromisoformat(event_start_str.replace('Z', '+00:00'))
        event_end = datetime.fromisoformat(event_end_str.replace('Z', '+00:00'))
        
        # ตรวจสอบว่ามีการซ้อนทับกันหรือไม่
        # กรณี 1: ช่วงเวลาที่ต้องการตรวจสอบอยู่ระหว่างกิจกรรม
        # กรณี 2: กิจกรรมอยู่ระหว่างช่วงเวลาที่ต้องการตรวจสอบ
        # กรณี 3: กิจกรรมเริ่มก่อนแต่สิ้นสุดหลังช่วงเวลาที่ต้องการตรวจสอบ
        # กรณี 4: กิจกรรมเริ่มระหว่างแต่สิ้นสุดหลังช่วงเวลาที่ต้องการตรวจสอบ
        if (start_time < event_end and end_time > event_start):
            return False
    
    # หากไม่มีกิจกรรมที่ซ้อนทับกัน แสดงว่าว่าง
    return True

def create_thai_date_label(date_str):
    """
    สร้างป้ายชื่อวันที่ในรูปแบบไทย
    Args:
        date_str: วันที่ในรูปแบบ "YYYY-MM-DD"
    Returns:
        str: วันที่ในรูปแบบ "DD/MM/YYYY พ.ศ."
    """
    try:
        date_obj = datetime.fromisoformat(date_str)
        thai_year = date_obj.year + 543  # แปลงปี ค.ศ. เป็น พ.ศ.
        return f"{date_obj.day}/{date_obj.month}/{thai_year}"
    except ValueError:
        return date_str

def create_timeslot_range(date, start_hour=9, end_hour=18, interval_minutes=30):
    """
    สร้างช่วงเวลาทั้งหมดในวันที่กำหนด
    Args:
        date: วันที่ที่ต้องการสร้างช่วงเวลา (datetime.date)
        start_hour: ชั่วโมงเริ่มต้น (default: 9)
        end_hour: ชั่วโมงสิ้นสุด (ไม่รวม) (default: 18)
        interval_minutes: ช่วงห่างเป็นนาที (default: 30)
    Returns:
        list: รายการ tuple ของ (slot_start, slot_end)
    """
    slots = []
    for hour in range(start_hour, end_hour):
        for minute in range(0, 60, interval_minutes):
            slot_start = datetime.combine(date, time(hour, minute)).astimezone(timezone.utc)
            slot_end = (slot_start + timedelta(minutes=interval_minutes)).astimezone(timezone.utc)
            slots.append((slot_start, slot_end))
    return slots

def create_facebook_quick_replies(items_data, max_items=13, add_back_button=True):
    """
    สร้างปุ่ม quick reply สำหรับ Facebook Messenger
    Args:
        items_data: รายการข้อมูลที่จะแสดงเป็นปุ่ม [(label, text), ...]
        max_items: จำนวนปุ่มสูงสุด (default: 13, Facebook limit is 13)
        add_back_button: เพิ่มปุ่มย้อนกลับหรือไม่ (default: True)
    Returns:
        list: รายการออบเจ็กต์ปุ่ม quick reply สำหรับ Facebook
    """
    quick_replies = []
    
    # จำกัดจำนวนปุ่ม
    data_items = items_data[:max_items-1 if add_back_button else max_items]
    
    # เพิ่มปุ่มตามข้อมูล
    for label, text in data_items:
        quick_replies.append({
            "content_type": "text",
            "title": label,      # แสดงข้อความบนปุ่ม (max 20 characters)
            "payload": text      # ข้อมูลที่จะส่งกลับ
        })
    
    # เพิ่มปุ่มย้อนกลับ
    if add_back_button:
        quick_replies.append({
            "content_type": "text",
            "title": "ย้อนกลับ",
            "payload": "ย้อนกลับ"
        })
    
    return quick_replies

def create_facebook_button_template(title, buttons, subtitle=None):
    """
    สร้าง Button Template สำหรับ Facebook Messenger
    Args:
        title: หัวข้อข้อความ
        buttons: รายการปุ่ม
        subtitle: รายละเอียดเพิ่มเติม (optional)
    Returns:
        dict: Facebook Button Template
    """
    template = {
        "attachment": {
            "type": "template",
            "payload": {
                "template_type": "button",
                "text": title,
                "buttons": buttons
            }
        }
    }
    
    if subtitle:
        template["attachment"]["payload"]["text"] = f"{title}\n{subtitle}"
    
    return template

def create_line_quick_reply_items(items_data, max_items=12, add_back_button=True):
    """
    สร้างปุ่ม quick reply สำหรับ LINE
    Args:
        items_data: รายการข้อมูลที่จะแสดงเป็นปุ่ม [(label, text), ...]
        max_items: จำนวนปุ่มสูงสุด (default: 12)
        add_back_button: เพิ่มปุ่มย้อนกลับหรือไม่ (default: True)
    Returns:
        list: รายการออบเจ็กต์ปุ่ม quick reply
    """
    items = []
    
    # จำกัดจำนวนปุ่ม
    data_items = items_data[:max_items-1 if add_back_button else max_items]
    
    # เพิ่มปุ่มตามข้อมูล
    for label, text in data_items:
        items.append({
            "type": "action",
            "action": {
                "type": "message",
                "label": label,  # แสดงช่วงเวลาบนปุ่ม
                "text": text     # ส่งช่วงเวลาเป็น text
            }
        })
    
    # เพิ่มปุ่มย้อนกลับ
    if add_back_button:
        items.append({
            "type": "action",
            "action": {
                "type": "message",
                "label": "ย้อนกลับ",
                "text": "ย้อนกลับ"
            }
        })
    
    return items

# ฟังก์ชันสำหรับสร้าง Flex Message สำหรับการสร้างนัดสำเร็จ
def create_appointment_success_flex_message(event_summary, date, time, user_name, user_email):
    """สร้าง LINE Flex Message สำหรับแจ้งการสร้างนัดสำเร็จ"""
    return {
        "type": "flex",
        "altText": f"✅ สร้างนัดใน Calendar เรียบร้อย - K. {user_name}",
        "contents": {
            "type": "bubble",
            "hero": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "✅ การนัดหมายสำเร็จ",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#27AE60",
                        "align": "center"
                    }
                ],
                "backgroundColor": "#E8F8F5",
                "paddingAll": "20px",
                "spacing": "md"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "📋 รายละเอียดการนัดหมาย",
                                "weight": "bold",
                                "size": "lg",
                                "color": "#2C3E50",
                                "margin": "none"
                            }
                        ],
                        "spacing": "sm",
                        "margin": "lg"
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "🎯 หัวข้อ:",
                                        "size": "sm",
                                        "color": "#7F8C8D",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": event_summary,
                                        "size": "sm",
                                        "color": "#2C3E50",
                                        "flex": 5,
                                        "wrap": True,
                                        "weight": "bold"
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "📅 วันที่:",
                                        "size": "sm",
                                        "color": "#7F8C8D",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": date,
                                        "size": "sm",
                                        "color": "#2C3E50",
                                        "flex": 5,
                                        "weight": "bold"
                                    }
                                ],
                                "margin": "sm"
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "🕒 เวลา:",
                                        "size": "sm",
                                        "color": "#7F8C8D",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": f"{time} น.",
                                        "size": "sm",
                                        "color": "#2C3E50",
                                        "flex": 5,
                                        "weight": "bold"
                                    }
                                ],
                                "margin": "sm"
                            },
                            {
                                "type": "box",
                                "layout": "horizontal",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "👤 Recruiter:",
                                        "size": "sm",
                                        "color": "#7F8C8D",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": f"K. {user_name}",
                                        "size": "sm",
                                        "color": "#2C3E50",
                                        "flex": 5,
                                        "weight": "bold"
                                    }
                                ],
                                "margin": "sm"
                            }
                        ],
                        "spacing": "sm",
                        "margin": "lg"
                    }
                ],
                "spacing": "md"
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "🎉 การนัดหมายถูกเพิ่มในปฏิทินเรียบร้อยแล้ว",
                        "size": "xs",
                        "color": "#95A5A6",
                        "align": "center",
                        "wrap": True
                    }
                ],
                "margin": "sm"
            }
        }
    }

# ฟังก์ชันสำหรับสร้าง Facebook Message สำหรับการสร้างนัดสำเร็จ
def create_appointment_success_facebook_message(event_summary, date, time, user_name, user_email):
    """สร้าง Facebook Message สำหรับแจ้งการสร้างนัดสำเร็จ"""
    return {
        "text": f"✅ สร้างนัดใน Calendar เรียบร้อย\n\n📋 รายละเอียดการนัดหมาย:\n🎯 หัวข้อ: {event_summary}\n📅 วันที่: {date}\n🕒 เวลา: {time} น.\n👤 Recruiter: K. {user_name}\n\n🎉 การนัดหมายถูกเพิ่มในปฏิทินเรียบร้อยแล้ว"
    }