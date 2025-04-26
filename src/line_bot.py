import asyncio
import os
import sys
import threading
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request, Response, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    QuickReply, QuickReplyButton, MessageAction
)
from apscheduler.schedulers.background import BackgroundScheduler
import uvicorn
import requests
from datetime import datetime, time
import time as t 
from typing import Dict, List, Any

app = FastAPI()
from api.endpoints import *
load_dotenv()


scheduler = BackgroundScheduler()
scheduler.start()

user_sessions = {}
base_url = os.getenv("BASE_URL")



# Available dates for meeting scheduling
available_dates = ["23/4/2568", "24/4/2568", "25/4/2568", "26/4/2568", "27/4/2568", "28/4/2568", "29/4/2568"]

# Experience options
exp_options = ["Strong exp", "Non - strong exp"]

# English level options
eng_level_options = ["ระดับ 4", "ระดับ 5"]

# Location options
location_options = ["Silom", "Asoke", "Phuket", "Pattaya", "Samui", "Huahin", "Chiangmai"]

# User session data
user_sessions = {}

# Configuration for data API service
base_url = os.getenv("BASE_URL")# Data service URL


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
    if session["state"] == "initial" or text not in ["กรอกข้อมูล Manager", "วิธีการใช้"] and session["state"] not in ["profile_age", "profile_exp", "profile_eng_level", "profile_location", "profile_confirm", "select_date", "select_time_slot", "confirm","meeting_name","meeting_description","meeting_summary"]:
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
        if text in exp_options:
            session["exp"] = text
            session["state"] = "profile_eng_level"
            
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
        if text in eng_level_options:
            session["eng_level"] = text
            session["state"] = "profile_location"
            
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
        if text in location_options:
            session["location"] = text
            session["state"] = "profile_confirm"

            # ส่งสรุปข้อมูล Profile ให้ผู้ใช้
            profile_summary = create_profile_summary(session)

            items = [
                QuickReplyButton(action=MessageAction(label="ยืนยัน", text="ยืนยัน")),
                QuickReplyButton(action=MessageAction(label="ยกเลิก", text="ยกเลิก"))
            ]
            quick_reply = QuickReply(items=items)

            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(
                    text=f"กรุณาตรวจสอบข้อมูลของคุณ:\n{profile_summary}\n\nยืนยันข้อมูลหรือไม่?",
                    quick_reply=quick_reply
                )
            )

        else:
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








































    # ================= MEETING SCHEDULING FLOW =================
    # Date selection
    elif session.get("state") == "profile_confirm":
        print("🔥 Enter profile_confirm branch")
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
                    print("✅ POST สำเร็จ:", response.json())

                    line_bot_api.push_message(
                        user_id,
                        TextSendMessage(text="บันทึกข้อมูลเรียบร้อยแล้ว ต่อไปเป็นการนัดประชุม")
                    )
                    send_date_selection(user_id)

                except Exception as e:
                    print(f"❌ Background Error: {e}")
                    line_bot_api.push_message(
                        user_id,
                        TextSendMessage(text="❗ เกิดข้อผิดพลาด กรุณาลองใหม่ภายหลัง")
                    )

            scheduler.add_job(
                func=background_post_and_push,
                args=[user_id, session.copy()],
                trigger="date",
                run_date=datetime.now() + timedelta(seconds=2)
            )

        elif text == "ยกเลิก":
            session.clear()
            session["state"] = "initial"
            send_initial_options(event.reply_token)

        else:
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
      



    # Time slot selection
    elif session["state"] == "select_time_slot":
        try:
            slot_number = int(text.strip("()"))
            if 1 <= slot_number <= len(session["available_slots"]):
                selected_slot = session["available_slots"][slot_number - 1]
                session["selected_slot"] = selected_slot
                session["state"] = "confirm"
                
                
                # Summary of meeting
                summary = create_meeting_summary(
                    session["selected_date"],
                    selected_slot["time"],
                    selected_slot["participants"]
                )
                
                # Send confirmation message with quick reply
                send_meeting_confirmation(event.reply_token, summary)

                
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
        meeting_data = {
                    "name": session["meeting_name"],
                    "description": session["meeting_description"],
                    "date": session["selected_date"],
                    "time": session["selected_slot"]["time"],
                    "participants": session["selected_slot"]["participants"],
                    "created_by": user_id,
                }
        start_time = t.time()
            #ลุงเอ
        response = requests.post(
                f"{base_url}/create_meeting",
                json=meeting_data,
                timeout=3
            )
        elapsed_time = t.time() - start_time
        print(f"Request took {elapsed_time:.3f} seconds")
        if response.status_code == 200:
                meeting_info = response.json().get("meeting", {})
                #รูปแบบ json ที่ได้กลับมา
                # {
                #     "status": "success",
                #     "meeting": {
                #         "date": "01/05/2567",
                #         "time": "10:00",
                #         "duration": "30 นาที",
                #         "participants": [...],
                #         "created_at": "25/04/2025 23:08:31",
                #         "created_by": "Uxxxxxxxxxxxx"
                #     }
                #     }
                # Send confirmation message
                meeting_confirmation = create_meeting_confirmation(meeting_info)
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=meeting_confirmation)
                )
        else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="เกิดข้อผิดพลาดในการสร้างการนัดหมาย")
                )
            
                # Reset state but keep profile information
                profile_data = {k: session[k] for k in ["age", "exp", "eng_level", "location"] if k in session}
                session.clear()
                session.update(profile_data)
                session["state"] = "initial"
                session["profile_completed"] = True
                
                # Show initial options again after a delay
                user_sessions[user_id] = {"state": "initial"}
                

 

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

@handler.add(MessageEvent)
def catch_all_message(event):
    print("🛎 Event received:", event)

    # แล้วดูว่า event.message.type เป็นอะไร
    if hasattr(event, 'message') and hasattr(event.message, 'type'):
        print("🛎 Event message type:", event.message.type)

def send_date_selection(reply_token_or_user_id):
    """Send Quick Reply for date selection"""
    items = [
        QuickReplyButton(action=MessageAction(label=date, text=date))
        for date in available_dates[:7]  # Limit to 7 quick replies due to Line's limit
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

def send_time_slots(reply_token, available_slots):
    """Send available time slots"""
    # Create message with available time slots
    slot_texts = []

    for i, slot in enumerate(available_slots, start=1):
        participants_text = "\n   " + "\n   ".join(f"-{p}" for p in slot["participants"])
        slot_text = f"{i}. เวลา {slot['time']}{participants_text}"
        slot_texts.append(slot_text)

    message_text = f"กรุณาเลือกช่วงเวลาที่ต้องการ:\n\nวันที่ : {slot['date']}\n" + "\n".join(slot_texts)
    
    # Show quick reply for time slot selection (max 13 items due to Line's limit)
    items = [
        QuickReplyButton(action=MessageAction(label=f"({i})", text=f"({i})"))
        for i in range(1, min(len(available_slots) + 1, 14))
    ]
    
    # Add cancel option
    items.append(QuickReplyButton(action=MessageAction(label="ยกเลิก", text="ยกเลิก")))
    
    quick_reply = QuickReply(items=items)
    
    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text=message_text, quick_reply=quick_reply)
    )

def send_meeting_confirmation(reply_token, summary):
    """Send meeting confirmation with Quick Reply options"""
    
    items = [
        QuickReplyButton(action=MessageAction(label="สร้างนัด", text="สร้างนัด")),
        QuickReplyButton(action=MessageAction(label="ยกเลิกนัด", text="ยกเลิกนัด"))
    ]
    
    quick_reply = QuickReply(items=items)
    
    confirmation_message = f"สรุปรายละเอียดการนัดหมาย:\n{summary}\n\nต้องการยืนยันการนัดหมายหรือไม่?"
    
    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text=confirmation_message, quick_reply=quick_reply)
    )

def create_profile_summary(session):
    """Create profile summary message"""
    summary = f"อายุ: {session.get('age')}\n"
    summary += f"ประสบการณ์: {session.get('exp')}\n"
    summary += f"ระดับภาษาอังกฤษ: {session.get('eng_level')}\n"
    summary += f"สถานที่: {session.get('location')}"
    
    return summary

def create_meeting_summary(date, time_slot, participants):
    """Create meeting summary message"""
    summary = f"วันที่ : {date}\n"
    summary += f"เวลา : {time_slot}\n"
    summary += "ผู้เข้าร่วม :\n"
    
    for participant in participants:
        summary += f"-{participant}\n"
    
    return summary

def create_meeting_confirmation(meeting_info):
    """Create confirmation message when meeting is successfully created"""
    confirmation = f"✅ สร้างการนัดหมายเรียบร้อยแล้ว\n\n"
    confirmation += f"📍 ชื่อ : {meeting_info['name']}\n"
    confirmation += f"📅 วันที่ : {meeting_info['date']}\n"
    confirmation += f"⏰ เวลา : {meeting_info['time']}\n"
    confirmation += f"⏱️ ระยะเวลา : {meeting_info['duration']}\n"
    confirmation += f"📋 รายละเอียด : {meeting_info['description']}\n"
    confirmation += "👥 ผู้เข้าร่วม :\n"
    
    for participant in meeting_info['participants']:
        confirmation += f"    - {participant}\n"
    
    confirmation += f"\n📝 สร้างเมื่อ : {meeting_info['created_at']}\n\n"
    confirmation += "จองบน google calendar และส่งอีเมลเรียบร้อยแล้ว"
    return confirmation

# if __name__ == "__main__":
#     uvicorn.run("line_bot:app", host="localhost", port=8001, reload=True)