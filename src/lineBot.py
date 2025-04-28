import os
import threading
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    QuickReply, QuickReplyButton, MessageAction
)
import uvicorn
import requests
from datetime import datetime, time, timedelta
import time as t 
from typing import Dict, List, Any
from apscheduler.schedulers.background import BackgroundScheduler
from handler_line import send_book_meeting
from api.endpoints import *
from models.schemas import BulkEventRequest

app = FastAPI()

load_dotenv()
scheduler = BackgroundScheduler()
scheduler.start()

# User session data
user_sessions = {}

# Configuration for data API service
base_url = os.getenv("BASE_URL_NGROK")


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text
    
    # Create session for new users if not exist
    if user_id not in user_sessions:
        user_sessions[user_id] = {"state": "initial"}
    
    # Get current session
    session = user_sessions[user_id]
    
    # Universal cancel command
    if text == "ยกเลิก":
        session.clear()
        session["state"] = "initial"
        send_initial_options(event.reply_token)
        return
    
    # Initial state or any unknown message
    if session["state"] == "initial" or (text not in ["กรอกข้อมูล Manager", "วิธีการใช้"] and session["state"] not in ["waiting_initial_choice", "profile_age", "profile_exp", "profile_eng_level", "profile_location", "profile_confirm", "select_date", "select_time_slot", "select_pair", "confirm", "meeting_name", "meeting_description", "meeting_summary"]):
        session["state"] = "waiting_initial_choice"
        send_initial_options(event.reply_token)
        return
    
    # Handle quick reply selection for initial options
    elif session["state"] == "waiting_initial_choice":
        if text == "กรอกข้อมูล Manager":
            session["state"] = "profile_age"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณาระบุอายุ")
            )
        elif text == "วิธีการใช้":
            usage_text = "นี่คือบริการหาช่วงเวลานัดประชุมอัจฉริยะ หากอยากใช้ให้เลือกหรือพิมพ์ \"กรอกข้อมูล Manager\" หากอยากยกเลิกการทำงานในขั้นตอนใดขั้นตอนนึงสามารถพิมพ์ \"ยกเลิก\""
            
            # Send usage info with quick reply to start again
            items = [
                QuickReplyButton(action=MessageAction(label="กรอกข้อมูล Manager", text="กรอกข้อมูล Manager"))
            ]
            
            quick_reply = QuickReply(items=items)
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=usage_text, quick_reply=quick_reply)
            )
            
            # Keep state as waiting_initial_choice
            session["state"] = "waiting_initial_choice"
        else:
            # If user enters something else while waiting for choice
            send_initial_options(event.reply_token)
    
    # ================= PROFILE FLOW =================
    # Age input
    elif session["state"] == "profile_age":
        try:
            age = int(text)
            session["age"] = age
            session["state"] = "profile_exp"
            
            # Experience options
            exp_options = ["Strong exp", "Non - strong exp"]
            
            # Send experience options as quick reply
            items = [
                QuickReplyButton(action=MessageAction(label=option, text=option))
                for option in exp_options
            ]
            
            quick_reply = QuickReply(items=items)
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="กรุณาเลือกประสบการณ์",
                    quick_reply=quick_reply
                )
            )
        except ValueError:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณาระบุอายุเป็นตัวเลขเท่านั้น")
            )
    
    # Experience input
    elif session["state"] == "profile_exp":
        # Experience options
        exp_options = ["Strong exp", "Non - strong exp"]
        
        if text in exp_options:
            session["exp"] = text
            session["state"] = "profile_eng_level"
            
            # English level options
            eng_level_options = ["ระดับ 4", "ระดับ 5"]
            
            # Send English level options as quick reply
            items = [
                QuickReplyButton(action=MessageAction(label=option, text=option))
                for option in eng_level_options
            ]
            
            quick_reply = QuickReply(items=items)
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="กรุณาเลือกระดับภาษาอังกฤษ",
                    quick_reply=quick_reply
                )
            )
        else:
            # Send experience options as quick reply again
            items = [
                QuickReplyButton(action=MessageAction(label=option, text=option))
                for option in exp_options
            ]
            
            quick_reply = QuickReply(items=items)
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="กรุณาเลือกประสบการณ์จากตัวเลือกที่กำหนดให้เท่านั้น",
                    quick_reply=quick_reply
                )
            )
    
    # English level input
    elif session["state"] == "profile_eng_level":
        # English level options
        eng_level_options = ["ระดับ 4", "ระดับ 5"]
        
        if text in eng_level_options:
            session["eng_level"] = text
            session["state"] = "profile_location"
            
            # Location options
            location_options = ["Silom", "Asoke", "Phuket", "Pattaya", "Samui", "Huahin", "Chiangmai"]
            
            # Send location options as quick reply
            items = [
                QuickReplyButton(action=MessageAction(label=option, text=option))
                for option in location_options
            ]
            
            quick_reply = QuickReply(items=items)
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="กรุณาเลือกสถานที่",
                    quick_reply=quick_reply
                )
            )
        else:
            # Send English level options as quick reply again
            items = [
                QuickReplyButton(action=MessageAction(label=option, text=option))
                for option in eng_level_options
            ]
            
            quick_reply = QuickReply(items=items)
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="กรุณาเลือกระดับภาษาอังกฤษจากตัวเลือกที่กำหนดให้เท่านั้น",
                    quick_reply=quick_reply
                )
            )
    
    # Location input
    elif session["state"] == "profile_location":
        # Location options
        location_options = ["Silom", "Asoke", "Phuket", "Pattaya", "Samui", "Huahin", "Chiangmai"]
        
        if text in location_options:
            session["location"] = text
            session["state"] = "profile_confirm"
            
            # Create profile summary
            profile_summary = create_profile_summary(session)
            
            # Send confirmation with quick reply
            items = [
                QuickReplyButton(action=MessageAction(label="ยืนยัน", text="ยืนยัน")),
                QuickReplyButton(action=MessageAction(label="ยกเลิก", text="ยกเลิก"))
            ]
            
            quick_reply = QuickReply(items=items)
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"สรุปข้อมูล Manager :\n{profile_summary}\n\nต้องการยืนยันข้อมูลหรือไม่?",
                    quick_reply=quick_reply
                )
            )
        else:
            # Send location options as quick reply again
            items = [
                QuickReplyButton(action=MessageAction(label=option, text=option))
                for option in location_options
            ]
            
            quick_reply = QuickReply(items=items)
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="กรุณาเลือกสถานที่จากตัวเลือกที่กำหนดให้เท่านั้น",
                    quick_reply=quick_reply
                )
            )
    
    # Profile confirmation
    elif session["state"] == "profile_confirm":
        if text == "ยืนยัน":
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กำลังค้นหาเวลาว่าง โปรดรอสักครู่...")
            )
            def background_post_and_push(user_id, session_data):
                
                try:
                    profile_json = {
                        "location": session_data.get("location"),
                        "english_min": 5 if session_data.get("eng_level") == "ระดับ 5" else 4,
                        "exp_kind": "strong" if session_data.get("exp") == "Strong exp" else "non",
                        "age_key": str(session_data.get("age")),
                        "start_date": datetime.now().strftime("%Y-%m-%d"),
                        "time_period": "7"
                    }
                    # print("🚀 Background Started with data:", profile_json)

                    response = requests.post(
                        f"{base_url}/events/availableMR",
                        json=profile_json,
                        timeout=30
                    )
                    response.raise_for_status()
                    # print("✅ POST สำเร็จ:", response.json())
                    

                    if response.status_code == 200:
                        session["state"] = "select_date"
                        # เก็บข้อมูลที่ได้รับจาก API ลงใน session
                        user_sessions[user_id]["state"] = "select_date"  # ต้องแก้ไขเป็น user_sessions[user_id] แทน session
                        user_sessions[user_id]["available_time_slots"] = response.json().get("available_time_slots", [])
                        
                        # แสดงข้อความยืนยันการบันทึกข้อมูล
                        line_bot_api.push_message(
                            user_id,
                            TextSendMessage(text="บันทึกข้อมูลเรียบร้อยแล้ว ต่อไปเป็นการนัดประชุม")
                        )
                        
                        # ส่งหน้าเลือกวันที่ให้ผู้ใช้
                        send_date_selection(user_id, session["available_time_slots"])
                    else:
                        line_bot_api.push_message(
                            user_id,
                            TextSendMessage(text="❗ เกิดข้อผิดพลาด กรุณาลองใหม่ภายหลัง")
                        )
                    
                    print("✅ ส่งข้อมูล Manager ไปยัง API แล้ว:", response.status_code)
                except Exception as e:
                    print("❌ ส่งข้อมูลล้มเหลว:", e)
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text="เกิดข้อผิดพลาดในการเชื่อมต่อกับระบบ กรุณาลองใหม่ภายหลัง")
                    )
            scheduler.add_job(
                func=background_post_and_push,
                args=[user_id, session.copy()],
                trigger="date",
                run_date=datetime.now() + timedelta(seconds=2)
            )
   
              
        elif text == "ยกเลิก":
            # Reset session and go back to initial state
            session.clear()
            session["state"] = "initial"
            send_initial_options(event.reply_token)
        else:
            # Send confirmation options again
            items = [
                QuickReplyButton(action=MessageAction(label="ยืนยัน", text="ยืนยัน")),
                QuickReplyButton(action=MessageAction(label="ยกเลิก", text="ยกเลิก"))
            ]
            
            quick_reply = QuickReply(items=items)
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="กรุณาเลือกยืนยันหรือยกเลิกเท่านั้น",
                    quick_reply=quick_reply
                )
            )
    
    # ================= MEETING SCHEDULING FLOW =================
# ในฟังก์ชัน handle_message, ส่วนของ select_date (ประมาณบรรทัดที่ 389)
    elif session["state"] == "select_date":
        # ตรวจสอบรูปแบบวันที่ที่ผู้ใช้เลือก (เช่น "27/4/2568")
        selected_date = None
        available_dates = []
        
        # จัดรูปแบบวันที่ให้แสดงเป็นรูปแบบไทย (วว/ดด/25XX)
        for time_slot_data in session.get("available_time_slots", []):
            date_str = time_slot_data.get("date", "")
            if date_str:
                # แปลงรูปแบบวันที่จาก "2025-04-27" เป็น "27/4/2568"
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    thai_year = date_obj.year + 543  # แปลงปี ค.ศ. เป็น พ.ศ.
                    thai_date = f"{date_obj.day}/{date_obj.month}/{thai_year}"
                    available_dates.append(thai_date)
                    
                    # ตรวจสอบว่าผู้ใช้เลือกวันที่นี้หรือไม่
                    if text == thai_date:
                        selected_date = time_slot_data
                        session["selected_date_iso"] = date_str
                        session["selected_date"] = thai_date
                except ValueError:
                    pass
        
        if selected_date:
            # พิมพ์ข้อความเพื่อดีบัก
            print(f"✅ เลือกวันที่: {session['selected_date']}")
            
            session["state"] = "select_time_slot"  # ตั้งค่าสถานะก่อนพิมพ์ข้อความ
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"คุณเลือกวันที่ {session['selected_date']} กำลังค้นหาช่วงเวลาที่ว่าง...")
            )
            
            # นำข้อมูลช่วงเวลาที่ว่างในวันที่เลือกมาแสดง
            time_slots = selected_date.get("time_slots", [])
            session["time_slots"] = time_slots
            
            # ส่งข้อความเลือก time slots ด้วย push message หลังจาก reply message
            def send_time_slots_later():
                send_time_slots(user_id, time_slots, session["selected_date"])
                
            scheduler.add_job(
                func=send_time_slots_later,
                trigger="date",
                run_date=datetime.now() + timedelta(seconds=1)
            )
        else:
            # ถ้าผู้ใช้ไม่ได้เลือกวันที่จากรายการ ให้แสดงรายการอีกครั้ง
            items = [
                QuickReplyButton(action=MessageAction(label=date, text=date))
                for date in available_dates[:13]  # จำกัดที่ 13 รายการตามข้อจำกัดของ Line
            ]
            
            quick_reply = QuickReply(items=items)
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text="กรุณาเลือกวันที่ต้องการนัดประชุมจากตัวเลือกที่กำหนดให้",
                    quick_reply=quick_reply
                )
            )
    
    # Time slot selection
    elif session["state"] == "select_time_slot":
        try:
            slot_number = int(text.strip("()"))
            if 1 <= slot_number <= len(session["time_slots"]):
                selected_time_slot = session["time_slots"][slot_number - 1]
                session["selected_time_slot"] = selected_time_slot
                session["state"] = "select_pair"
                
                # แสดงรายการคู่ของ Manager และ Recruiter ที่ว่างในช่วงเวลานี้
                send_pair_selection(event.reply_token, selected_time_slot)
                
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="กรุณาเลือกช่วงเวลาจากตัวเลือกที่กำหนดให้")
                )
        except ValueError:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณาเลือกช่วงเวลาที่ถูกต้อง")
            )
    
    # Pair selection
# Pair selection
    elif session["state"] == "select_pair":
        try:
            pair_number = int(text.strip("()"))
            if 1 <= pair_number <= len(session["selected_time_slot"]["pair_details"]):
                selected_pair = session["selected_time_slot"]["pair_details"][pair_number - 1]
                session["selected_pair"] = selected_pair
                
                # เพิ่มการเก็บอีเมลทั้งสองคนเข้าไปในลิสต์
                session["emails"] = [
                    selected_pair["manager"]["email"],
                    selected_pair["recruiter"]["email"]
                ]
                print(f"✅ Collected emails: {session['emails']}")
                
                # จัดการวันที่และเวลาให้อยู่ในรูปแบบที่ต้องการ
                # แปลงวันที่จากรูปแบบ dd/mm/yyyy (Thai) เป็น yyyy-mm-dd (ISO)
                date_parts = session["selected_date"].split("/")
                if len(date_parts) == 3:
                    day, month, thai_year = date_parts
                    year = int(thai_year) - 543  # แปลงจาก พ.ศ. เป็น ค.ศ.
                    iso_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                else:
                    # ในกรณีที่ session["selected_date_iso"] มีอยู่แล้ว
                    iso_date = session.get("selected_date_iso", "")
                
                # แยกช่วงเวลาเริ่มต้นและสิ้นสุด
                time_range = session["selected_time_slot"]["time"]
                start_time, end_time = time_range.split("-")
                
                # สร้างรูปแบบ ISO datetime และเก็บใน session
                session["start_time"] = f"{iso_date}T{start_time}:00+07:00"
                session["end_time"] = f"{iso_date}T{end_time}:00+07:00"
                print(f"✅ Start time: {session['start_time']}, End time: {session['end_time']}")
                
                session["state"] = "confirm"
                
                # สรุปรายละเอียดการนัดหมาย
                summary = create_meeting_summary(
                    session["selected_date"],
                    session["selected_time_slot"]["time"],
                    [selected_pair["manager"]["name"], selected_pair["recruiter"]["name"]]
                )
                
                # ส่งข้อความยืนยันการนัดหมาย
                send_meeting_confirmation(event.reply_token, summary)
                
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="กรุณาเลือกคู่ Manager-Recruiter จากตัวเลือกที่กำหนดให้")
                )
        except ValueError:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณาเลือกคู่ Manager-Recruiter ที่ถูกต้อง")
            )
    
    # Meeting confirmation
    elif session["state"] == "confirm":
        if text == "สร้างนัด":
            session["state"] = "meeting_name"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณากรอกชื่อการประชุม : ")
            )
            
        elif text == "ยกเลิกนัด":
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="ยกเลิกการนัดหมายเรียบร้อยแล้ว")
            )
            # Reset state but keep profile information
            profile_data = {k: session[k] for k in ["age", "exp", "eng_level", "location"] if k in session}
            session.clear()
            session.update(profile_data)
            session["state"] = "initial"
            session["profile_completed"] = True
            
            # Show initial options again
            send_initial_options(user_id)
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณาเลือกจากตัวเลือกที่กำหนดให้ (สร้างนัด หรือ ยกเลิกนัด)")
            )
            
    elif session["state"] == "meeting_name":
        session["meeting_name"] = text
        session["state"] = "meeting_description"
        print(session["meeting_name"])
        line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณากรอกรายละเอียดการประชุม : ")
            )
    elif session["state"] == "meeting_description":
        session["meeting_description"] = text
        session["state"] = "meeting_summary"
        print(session["meeting_description"])
        
        # สร้างข้อมูลการนัดหมาย
        selected_pair = session["selected_pair"]
        participants = [selected_pair["manager"]["name"], selected_pair["recruiter"]["name"]]
        
        meeting_info = {
            "name": session["meeting_name"],
            "description": session["meeting_description"],
            "date": session["selected_date"],
            "time": session["selected_time_slot"]["time"],
            "duration": "30 นาที",
            "participants": participants,
            "created_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "created_by": user_id
        }
        meeting_result = BulkEventRequest(
                user_emails=session["emails"],
                summary=session["meeting_name"],
                description=session["meeting_description"],
                location= f"{session.get('location')}",
                start_time=session["start_time"],
                end_time=session["end_time"],
                attendees=[]
        )
        print(session.get('location'))  # เช็กค่า location ที่ได้จาก session
        print(session.get('start_time'))  # เช็ก start_time
        print(session.get('end_time'))    # เช็ก end_time
        
        # สร้างข้อความยืนยันการนัดหมาย
        meeting_confirmation = create_meeting_confirmation(meeting_info)
        
        # ส่งข้อความยืนยันการนัดหมาย
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=meeting_confirmation)
        )
        #ส่งข้อมูลให้ไป api ที่ทำการ book ใน google calendar ผู้ใช้ตาม meeting_result ที่ส่งไป และส่งอีเมลให้ manager recruiter
        threading.Thread(target=send_book_meeting, args=(meeting_result,)).start()
        # รีเซ็ตสถานะแต่เก็บข้อมูลโปรไฟล์
        profile_data = {k: session[k] for k in ["age", "exp", "eng_level", "location", "available_time_slots"] if k in session}
        session.clear()
        session.update(profile_data)
        session["state"] = "initial"
        session["profile_completed"] = True

@handler.add(MessageEvent)
def catch_all_message(event):
    print("🛎 Event received:", event)

    # แล้วดูว่า event.message.type เป็นอะไร
    if hasattr(event, 'message') and hasattr(event.message, 'type'):
        print("🛎 Event message type:", event.message.type)

def send_initial_options(reply_token_or_user_id):
    """Send initial options with Quick Reply"""
    items = [
        QuickReplyButton(action=MessageAction(label="กรอกข้อมูล Manager", text="กรอกข้อมูล Manager")),
        QuickReplyButton(action=MessageAction(label="วิธีการใช้", text="วิธีการใช้"))
    ]
    
    quick_reply = QuickReply(items=items)
    
    message = TextSendMessage(
        text="นี่คือ line chat นัดประชุมอัจฉริยะ หากต้องการใช้บริการกรุณาเลือกด้านล่าง",
        quick_reply=quick_reply
    )
    
    # Handle both reply_token and user_id
    if isinstance(reply_token_or_user_id, str) and reply_token_or_user_id.startswith("U"):
        # It's a user_id
        line_bot_api.push_message(reply_token_or_user_id, message)
        if reply_token_or_user_id in user_sessions:
            user_sessions[reply_token_or_user_id]["state"] = "waiting_initial_choice"
    else:
        # It's a reply_token
        line_bot_api.reply_message(reply_token_or_user_id, message)

def send_date_selection(reply_token_or_user_id, available_time_slots):
    """Send Quick Reply for date selection"""
    available_dates = []
    
    # แปลงวันที่จากรูปแบบ ISO เป็นรูปแบบไทย
    for time_slot_data in available_time_slots:
        date_str = time_slot_data.get("date", "")
        if date_str:
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                thai_year = date_obj.year + 543  # แปลงปี ค.ศ. เป็น พ.ศ.
                thai_date = f"{date_obj.day}/{date_obj.month}/{thai_year}"
                available_dates.append(thai_date)
            except ValueError:
                pass
    
    if not available_dates:
        # ถ้าไม่มีวันที่ใด ให้แจ้งผู้ใช้
        message = TextSendMessage(
            text="ไม่พบวันที่ว่างในระบบ กรุณาติดต่อผู้ดูแลระบบ"
        )
    else:
        # สร้าง Quick Reply สำหรับเลือกวันที่
        items = [
            QuickReplyButton(action=MessageAction(label=date, text=date))
            for date in available_dates[:13]  # จำกัดที่ 13 รายการตามข้อจำกัดของ Line
        ]
        
        quick_reply = QuickReply(items=items)
        
        message = TextSendMessage(
            text="กรุณาเลือกวันที่ต้องการนัดประชุม",
            quick_reply=quick_reply
        )
    
    # Handle both reply_token and user_id
    if isinstance(reply_token_or_user_id, str) and reply_token_or_user_id.startswith("U"):
        # It's a user_id
        line_bot_api.push_message(reply_token_or_user_id, message)
    else:
        # It's a reply_token
        line_bot_api.reply_message(reply_token_or_user_id, message)

def send_time_slots(reply_token_or_user_id, time_slots, selected_date):
    """Send available time slots"""
    # Create message with available time slots
    slot_texts = []

    for i, slot in enumerate(time_slots[:12], start=1):  # ตัดไว้ที่ 12 อันก่อนเลย
        pairs_text = "\n   " + "\n   ".join([f"👥{pair}" for pair in slot["available_pairs"]])
        slot_text = f"{i}. เวลา {slot['time']}{pairs_text}"
        slot_texts.append(slot_text)

    message_text = f"กรุณาเลือกช่วงเวลาที่ต้องการ:\nวันที่ : {selected_date}\n" + "\n".join(slot_texts)

    # สร้างปุ่ม quick reply สำหรับ 12 slots
    items = [
        QuickReplyButton(action=MessageAction(label=f"({i})", text=f"({i})"))
        for i in range(1, len(slot_texts) + 1)
    ]

    # เพิ่มปุ่ม 'ยกเลิก' เป็นปุ่มที่ 13
    items.append(QuickReplyButton(action=MessageAction(label="ยกเลิก", text="ยกเลิก")))

    quick_reply = QuickReply(items=items)

    message = TextSendMessage(text=message_text, quick_reply=quick_reply)

    # Handle both reply_token and user_id
    if isinstance(reply_token_or_user_id, str) and reply_token_or_user_id.startswith("U"):
        line_bot_api.push_message(reply_token_or_user_id, message)
    else:
        line_bot_api.reply_message(reply_token_or_user_id, message)

        
def send_pair_selection(reply_token, time_slot):
    """Send Manager-Recruiter pairs for selection"""
    # Create message with available pairs
    pairs = time_slot["pair_details"]
    
    message_text = f"กรุณาเลือก Manager-Recruiter ที่จะนัด\nเวลา {time_slot['time']}\n"
    
    for i, pair_detail in enumerate(pairs, start=1):
        message_text += f"   {i}.👥 {pair_detail['pair']}\n"
    
    # แสดง quick reply สำหรับเลือกคู่ Manager-Recruiter (สูงสุด 13 รายการตามข้อจำกัดของ Line)
    items = [
        QuickReplyButton(action=MessageAction(label=f"({i})", text=f"({i})"))
        for i in range(1, min(len(pairs) + 1, 14))
    ]
    
    # เพิ่มตัวเลือกยกเลิก
    items.append(QuickReplyButton(action=MessageAction(label="ยกเลิก", text="ยกเลิก")))
    
    quick_reply = QuickReply(items=items)
    
    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text=message_text, quick_reply=quick_reply)
    )

def send_meeting_confirmation(reply_token, meeting_summary):
    """Send meeting confirmation"""
    items = [
        QuickReplyButton(action=MessageAction(label="สร้างนัด", text="สร้างนัด")),
        QuickReplyButton(action=MessageAction(label="ยกเลิกนัด", text="ยกเลิกนัด"))
    ]
    
    quick_reply = QuickReply(items=items)
    
    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(
            text=f"สรุปรายละเอียดการนัดหมาย:\n{meeting_summary}\nต้องการยืนยันการนัดหมายหรือไม่?",
            quick_reply=quick_reply
        )
    )

def create_profile_summary(session):
    """Create a summary of the user's profile"""
    summary = f"อายุ: {session.get('age')}\n"
    summary += f"ประสบการณ์: {session.get('exp')}\n"
    summary += f"ระดับภาษาอังกฤษ: {session.get('eng_level')}\n"
    summary += f"สถานที่: {session.get('location')}"
    return summary

def create_meeting_summary(date, time, participants):
    """Create a summary of the meeting"""
    summary = f"วันที่ : {date}\n"
    summary += f"เวลา : {time}\n"
    summary += f"ผู้เข้าร่วม :\n"
    
    for participant in participants:
        summary += f"- {participant}\n"
    
    return summary

def create_meeting_confirmation(meeting_info):
    """Create a confirmation message for the meeting"""
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    confirmation = "✅ สร้างการนัดหมายเรียบร้อยแล้ว\n"
    confirmation += f"📍 ชื่อ : {meeting_info.get('name', 'ไม่มีชื่อ')}\n" 
    confirmation += f"📅 วันที่ : {meeting_info.get('date', 'ไม่ระบุ')}\n"
    confirmation += f"⏰ เวลา : {meeting_info.get('time', 'ไม่ระบุ')}\n"
    confirmation += f"⏱️ ระยะเวลา : {meeting_info.get('duration', '30 นาที')}\n"
    confirmation += f"📋 รายละเอียด : {meeting_info.get('description', 'ไม่มีรายละเอียด')}\n"
    confirmation += "👥 ผู้เข้าร่วม :\n"
    
    for participant in meeting_info.get('participants', []):
        confirmation += f"    - {participant}\n"
    
    confirmation += f"📝 สร้างเมื่อ : {meeting_info.get('created_at', now)}\n"
    confirmation += "จองบน google calendar และส่งอีเมลเรียบร้อยแล้ว"
    
    return confirmation

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8001)