import os
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
from datetime import datetime, time
import time as t 
from typing import Dict, List, Any

app = FastAPI()

load_dotenv()

line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

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
DATA_API_URL = "http://localhost:8000"  # Data service URL

@app.get("/")
def read_root():
    return {"message": "Hello, Line!"}

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get('X-Line-Signature', '')
    body = await request.body()
    
    try:
        handler.handle(body.decode('utf-8'), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    return Response(content="OK", media_type="text/plain")

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
    if session["state"] == "initial" or text not in ["กรอกข้อมูล Manager", "วิธีการใช้"] and session["state"] not in ["profile_age", "profile_exp", "profile_eng_level", "profile_location", "profile_confirm", "select_date", "select_time_slot", "confirm"]:
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
            # Save profile data (you might want to save it to a database here)
            session["profile_completed"] = True
            session["state"] = "select_date"
                # 📦 สร้าง JSON ที่จะส่ง
            profile_json = {
                "location": session.get("location"),
                "english_min": 5 if session.get("eng_level") == "ระดับ 5" else 4,
                "exp_kind": "strong" if session.get("exp") == "Strong exp" else "non",
                "age_key": str(session.get("age")),
                "start_date": datetime.now().strftime("%Y-%m-%d"),
                "time_period": "7"
            }

            try:
                #TODO: พี่เปา
                response = requests.post(f"{DATA_API_URL}/receive_manager_info", json=profile_json)
                print("✅ ส่งข้อมูล Manager ไปยัง API แล้ว:", response.status_code)
            except Exception as e:
                print("❌ ส่งข้อมูลล้มเหลว:", e)
            # Now proceed to meeting scheduling flow
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="บันทึกข้อมูลเรียบร้อยแล้ว ต่อไปเป็นการนัดประชุม")
            )
            
            # Send date selection after profile completion
            send_date_selection(user_id)
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
    # Date selection
    elif session["state"] == "select_date":
        if text in available_dates:
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text="กำลังประมวลผลหาช่วงเวลาที่ว่าง...")
            )          
            session["selected_date"] = text
            session["state"] = "select_time_slot"
            
            # แปลงวันที่จากรูปแบบไทย (วว/ดด/25XX) เป็นรูปแบบสากล (YYYY-MM-DD)
            day, month, year = text.split('/')
            year_ce = int(year) - 543  # แปลงจาก พ.ศ. เป็น ค.ศ.
            date_iso = f"{year_ce}-{month.zfill(2)}-{day.zfill(2)}"
            start_time = t.time()
            # Call data API to get available slots
            response = requests.post(
                #TODO: ไม่ไหวแล้ว
                f"{DATA_API_URL}/calculate_available_slots",
                json={"date": session["selected_date"], "date_iso": date_iso},
                # TODO:json = {
                # TODO:      "date": "01/05/2567",
                # TODO:     "date_iso": "2024-05-01"
                # TODO:    }
                timeout=3
                #TODO: ส่ง json ด้วย method POST ไป /calculate_available_slots
                
            )
            elapsed_time = t.time() - start_time
            print(f"Request took {elapsed_time:.3f} seconds")
                #TODO: ตัวอย่าง json ที่ได้รับ
                #TODO:             {
                #TODO: "available_slots": [
                #TODO:     {
                #TODO:     "date": "01/05/2567",
                #TODO:     "time": "10:00-10:30",
                #TODO:     "participants": ["nonlaneeud@gmail.com", "panupongpr3841@gmail.com"]
                # TODO:    },
                # TODO:    ...
                #TODO: ]
                #TODO: }

            if response.status_code == 200:
                available_slots = response.json().get("available_slots", [])
                session["available_slots"] = available_slots
                send_time_slots(event.reply_token, available_slots)
                #TODO:เอาไปประมวลผลต่อ send_time_slots ให้กรองสวยๆ และส่งให้ผู้ใช้
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="เกิดข้อผิดพลาดในการดึงข้อมูลช่วงเวลาที่ว่าง")
                )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณาเลือกวันที่จากตัวเลือกที่กำหนดให้")
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
            # Create meeting by calling data API
            meeting_data = {
                "date": session["selected_date"],
                "time": session["selected_slot"]["time"],
                "participants": session["selected_slot"]["participants"],
                "created_by": user_id,
                # Add user profile data if available
                "user_profile": {
                    "age": session.get("age"),
                    "exp": session.get("exp"),
                    "eng_level": session.get("eng_level"),
                    "location": session.get("location")
                }
            }
            start_time = t.time()
            #ลุงเอ
            response = requests.post(
                f"{DATA_API_URL}/create_meeting",
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
    confirmation += f"📅 วันที่ : {meeting_info['date']}\n"
    confirmation += f"⏰ เวลา : {meeting_info['time']}\n"
    confirmation += f"⏱️ ระยะเวลา : {meeting_info['duration']}\n"
    confirmation += "👥 ผู้เข้าร่วม :\n"
    
    for participant in meeting_info['participants']:
        confirmation += f"    - {participant}\n"
    
    confirmation += f"\n📝 สร้างเมื่อ : {meeting_info['created_at']}\n\n"
    confirmation += "จองบน google calendar และส่งอีเมลเรียบร้อยแล้ว"
    return confirmation

if __name__ == "__main__":
    uvicorn.run("line_bot:app", host="localhost", port=8001, reload=True)