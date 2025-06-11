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

spreadsheet_id = os.environ.get('SPREADSHEET_ID')
credentialsGsheet = os.environ.get('CREDENTIALS_GOOGLE_SHEET')
scopeGsheet = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
credentialsGsheet = ServiceAccountCredentials.from_json_keyfile_name(credentialsGsheet, scopeGsheet)
client = gspread.authorize(credentialsGsheet)



#ฟังก์ชันตรวจสอบ token จากฐานข้อมูล
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

#เช็ค token จากอีเมล
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

#ฟังก์ชัน Redirect ไปหน้าเว็บเข้าสู่ระบบ
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


#ฟังก์ชันดึงข้อมูลจาก Google Sheet
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

#แปลงวันที่ - เวลา เป็นรูปแบบ ISO
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


#========================================== fot API date, timeslot, pairs ======================================
import asyncio

#เช็ค token ของ recruiter ว่าใช้เข้าถึง google calendar ได้ไหม และเช็คช่วงเวลาของ recruiter ว่าว่างไหม
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

#ตรวจสอบว่าช่วงเวลาที่ระบุว่าว่างหรือไม่ 
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

#สร้างวันที่รูปแบบไทย (Ex 10/6/2568)
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

#ฟังก์ชันสร้างช่วงเวลา
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

#สร้างปุ่ม quick reply สำหรับ Facebook
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

#สร้าง button template สำหรับ facebook (ใช้กับตัว API login)
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

#สร้าง quick reply สำหรับ LINE
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