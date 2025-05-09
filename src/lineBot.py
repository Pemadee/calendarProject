import os
import re
import threading
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    QuickReply, QuickReplyButton, MessageAction
)
import urllib
import uvicorn
import requests
from datetime import datetime, time, timedelta
import time as t 
from typing import Dict, List, Any
from apscheduler.schedulers.background import BackgroundScheduler
from api.endpoints import *
from models.schemas import BulkEventRequest
from linebot.models import TemplateSendMessage, ButtonsTemplate, URIAction
from linebot.models import FlexSendMessage


app = FastAPI()

load_dotenv()
scheduler = BackgroundScheduler()
scheduler.start()

# User session data
user_sessions = {}

# Configuration for data API service
base_url = os.getenv("BASE_URL")


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

    # ✅ แก้ตรงนี้: เปลี่ยนจาก if → elif และแยกให้ชัดเจน
    elif text not in ["กรอกข้อมูล Manager", "วิธีการใช้", "login(สำหรับ Manager & Recruiter)"] and session["state"] not in [
        "profile_age", "profile_exp", "profile_eng_level", "profile_location",
        "profile_confirm", "select_date", "select_time_slot", "select_pair",
        "confirm", "meeting_name", "meeting_description", "meeting_summary", "login_email"
    ]:
        session["state"] = "initial"
        send_initial_options(event.reply_token)
        return

    # แก้ส่วนนี้จากประมาณบรรทัด 87
    elif session["state"] == "initial":  # เปลี่ยนจาก waiting_initial_choice เป็น initial
        if text == "กรอกข้อมูล Manager":
            session["state"] = "profile_age"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณาระบุอายุ")
            )
        elif text == "วิธีการใช้":
            usage_text = "นี่คือบริการหาช่วงเวลานัดประชุมอัจฉริยะ หากอยากใช้ให้เลือกหรือพิมพ์ \"กรอกข้อมูล Manager\" หากอยากยกเลิกการทำงานในขั้นตอนใดขั้นตอนนึงสามารถพิมพ์ \"ยกเลิก\""
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=usage_text)
            )
            session.clear()
            session["state"] = "initial"
            send_menu_only(user_id)

            return
        elif text == "login(สำหรับ Manager & Recruiter)":          
            session["state"] = "login_email"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณากรอกอีเมลของคุณ (example@company.com)")
            )
        else:
            # ถ้าผู้ใช้พิมพ์อย่างอื่นที่ไม่ใช่ตัวเลือก ให้แสดงเมนูใหม่
            send_initial_options(event.reply_token)

    elif session["state"] == "login_email":  
        def background_login_and_push(user_id, user_email):
            """ดึง events ใน background แล้ว push กลับหาผู้ใช้"""
            try:
                resp = requests.get(
                    f"{base_url}/events/{user_email}",
                    allow_redirects=False,
                    timeout=30
                )

                # ===== Auth required =====
                if resp.status_code in (302, 307) and "location" in resp.headers:
                    original_auth_url = resp.headers["location"]
    
                    # เพิ่มพารามิเตอร์ mobile=true
                    if "?" in original_auth_url:
                        auth_url = original_auth_url + "&mobile=true"
                    else:
                        auth_url = original_auth_url + "?mobile=true"
                    
                    message_text = (
                        "กรุณาคลิกที่ลิงก์ด้านล่างเพื่อยืนยันสิทธิ์การเข้าถึง Google Calendar\n\n"
                        "📱 หากใช้มือถือและเกิดข้อผิดพลาด 403:\n"
                        "กดลิงก์ค้างไว้แล้วเลือก 'เปิดในเบราว์เซอร์ภายนอก'\n\n"
                        f"{auth_url}"
                    )
                    
                    line_bot_api.push_message(
                        user_id,
                        TextSendMessage(text=message_text)
                    )
                                            # reset session
                    session.clear()
                    session["state"] = "initial"
                    send_menu_only(user_id)
                    return

                # ===== Got events =====
                if resp.status_code == 200:
                    line_bot_api.push_message(user_id, TextSendMessage(text=f"✅ Login สำเร็จ"))
                                            # reset session
                    session.clear()
                    session["state"] = "initial"
                    send_menu_only(user_id)
                else:
                    line_bot_api.push_message(
                        user_id,
                        TextSendMessage(text=f"เกิดข้อผิดพลาด (status {resp.status_code}) กรุณาลองใหม่ภายหลัง")
                    )
                                            # reset session
                    session.clear()
                    session["state"] = "initial"
                    send_menu_only(user_id)

            except Exception as e:
                print("❌ login error:", e)
                line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text=f"เกิดข้อผิดพลาดในการดึงปฏิทิน: {e}")
                )
                                        # reset session
                session.clear()
                session["state"] = "initial"
                send_menu_only(user_id)

        def background_login_and_push(user_id, user_email):
                        """ดึง events ใน background แล้ว push กลับหาผู้ใช้"""
                        try:
                            resp = requests.get(
                                f"{base_url}/events/{user_email}",
                                allow_redirects=False,
                                timeout=30                # ยืด timeout ให้เยอะขึ้น
                            )

                            # ===== Auth required =====
                            if resp.status_code in (302, 307) and "location" in resp.headers:
                                auth_url = resp.headers["location"]
                                line_bot_api.push_message(
                                    user_id,
                                    TextSendMessage(text=f"กรุณาคลิกยืนยันสิทธิ์ที่ลิงก์นี้\n{auth_url}")
                                )
                                return
                            # ===== Got events =====
                            if resp.status_code == 200:
                                data = resp.json()
                                events = data.get("events", [])
                                if events:
                                    lines = [f"📅 ปฏิทินของ {user_email} (7 วันถัดไป)"]
                                    for ev in events[:10]:
                                        lines.append(f"• {ev['start']} ▶ {ev['summary']}")
                                    reply_text = "\n".join(lines)
                                    
                                else:
                                    reply_text = f"ไม่พบกิจกรรม 7 วันถัดไปของ {user_email}"
                                    # reset session
                                    session.clear()
                                    session["state"] = "initial"
                                    send_menu_only(user_id)
                                line_bot_api.push_message(user_id, TextSendMessage(text=f"✅ Login สำเร็จ\n\n{reply_text}"))
                                # reset session
                                session.clear()
                                session["state"] = "initial"
                                send_menu_only(user_id)
                            else:
                                line_bot_api.push_message(
                                    user_id,
                                    TextSendMessage(text=f"เกิดข้อผิดพลาด (status {resp.status_code}) กรุณาลองใหม่ภายหลัง")
                                )
                                                # reset session
                                session.clear()
                                session["state"] = "initial"
                                send_menu_only(user_id)

                        except Exception as e:
                            print("❌ login error:", e)
                            line_bot_api.push_message(
                                user_id,
                                TextSendMessage(text=f"เกิดข้อผิดพลาดในการดึงปฏิทิน: {e}")
                            )
                            session.clear()
                            session["state"] = "initial"
                            send_menu_only(user_id)

        email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w{2,}$"
        if re.match(email_pattern, text):
            user_email = text.strip()

            # ตอบกลับทันที
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กำลังตรวจสอบสิทธิ์และดึงข้อมูลปฏิทิน โปรดรอสักครู่...")
            )

            # เรียกทำงานฉากหลัง
            scheduler.add_job(
                func=background_login_and_push,
                args=[user_id, user_email],
                trigger="date",
                run_date=datetime.now() + timedelta(seconds=1)
            )

            # reset session
            # session.clear()
            # session["state"] = "initial"
            # send_menu_only(user_id)
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="รูปแบบอีเมลไม่ถูกต้อง กรุณาลองใหม่")
            )
            
            # reset session
            session.clear()
            session["state"] = "initial"
            send_menu_only(user_id)
                         
            email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w{2,}$"
            if re.match(email_pattern, text):
                user_email = text.strip()

                # ตอบกลับทันที
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="กำลังตรวจสอบสิทธิ์และดึงข้อมูลปฏิทิน โปรดรอสักครู่...")
                )

                # เรียกทำงานฉากหลัง
                scheduler.add_job(
                    func=background_login_and_push,
                    args=[user_id, user_email],
                    trigger="date",
                    run_date=datetime.now() + timedelta(seconds=1)
                )


            else:
                
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="รูปแบบอีเมลไม่ถูกต้อง กรุณาลองใหม่")
                )
                session.clear()
                session["state"] = "initial"
                send_menu_only(user_id)

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
            
    # ================= MEETING FLOW =================
    # Profile confirmation
    elif session["state"] == "profile_confirm":
        if text == "ยืนยัน":
            if "selected_pair" in session:
                del session["selected_pair"]
            if "emails" in session:
                del session["emails"]
            if "start_time" in session:
                del session["start_time"]
            if "end_time" in session:
                del session["end_time"]
                       
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กำลังค้นหาวันเวลาว่าง โปรดรอสักครู่..."))
           
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
    
    # ในส่วนของ select_date
    elif session["state"] == "select_date":
        # ตรวจสอบรูปแบบวันที่ที่ผู้ใช้เลือก (เช่น "8/5/2568")
        selected_date_iso = None
        available_dates = []  # สร้างรายการวันที่ให้เลือก
        
        # จัดรูปแบบวันที่ให้แสดงเป็นรูปแบบไทย (วว/ดด/25XX)
        for time_slot_data in session.get("available_time_slots", []):
            date_str = time_slot_data.get("date", "")
            if date_str:
                # แปลงรูปแบบวันที่จาก "2025-05-08" เป็น "8/5/2568"
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    thai_year = date_obj.year + 543  # แปลงปี ค.ศ. เป็น พ.ศ.
                    thai_date = f"{date_obj.day}/{date_obj.month}/{thai_year}"
                    available_dates.append(thai_date)  # เพิ่มวันที่ในรูปแบบไทยเข้าไปในรายการ
                    
                    # ตรวจสอบว่าผู้ใช้เลือกวันที่นี้หรือไม่
                    if text == thai_date:
                        selected_date_iso = date_str
                        selected_date_thai = thai_date
                        break
                except ValueError:
                    pass
        
        if selected_date_iso:
            # พิมพ์ข้อความเพื่อดีบัก
            print(f"✅ เลือกวันที่: {selected_date_thai}")
            
            session["state"] = "select_time_slot"  # ตั้งค่าสถานะก่อนพิมพ์ข้อความ
            session["selected_date_iso"] = selected_date_iso
            session["selected_date"] = selected_date_thai
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"คุณเลือกวันที่ {selected_date_thai} กำลังค้นหาช่วงเวลาที่ว่าง...")
            )
            
            # เรียก API เพื่อดึงข้อมูลช่วงเวลาที่ว่าง
            def get_available_timeslots_later():
                try:
                    # สร้าง payload สำหรับ API
                    date_request = {
                        "date": selected_date_iso,
                        "location": session.get("location", ""),
                        "english_min": 5 if session.get("eng_level") == "ระดับ 5" else 4,
                        "exp_kind": "strong" if session.get("exp") == "Strong exp" else "non",
                        "age_key": str(session.get("age", ""))
                    }
                    
                    print(f"🚀 เรียก API ช่วงเวลาว่าง: {date_request}")
                    
                    # เรียก API
                    response = requests.post(
                        f"{base_url}/events/available-timeslots",
                        json=date_request,
                        timeout=30
                    )
                    
                    print(f"📡 API Response (status): {response.status_code}")
                    
                    if response.status_code == 200:
                        api_response = response.json()
                        print(f"📦 API Response (available_timeslots): {api_response}")
                        
                        # เก็บข้อมูลช่วงเวลาที่ว่างลงใน session - ปรับให้เข้ากับข้อมูลเดิม
                        if "available_timeslots" in api_response:
                            time_slots = []
                            for slot in api_response["available_timeslots"]:
                                # แปลงข้อมูลให้เข้ากับรูปแบบเดิม
                                pairs = []
                                pair_details = []
                                
                                # สร้าง pair และ pair_details จาก available_pairs
                                for pair_info in slot.get("available_pairs", []):
                                    pair_name = pair_info.get("pair", "")
                                    pairs.append(pair_name)
                                    pair_details.append(pair_info)
                                
                                time_slots.append({
                                    "time": slot.get("time_slot", ""),
                                    "available_pairs": pairs,
                                    "pair_details": pair_details
                                })
                                
                            session["time_slots"] = time_slots
                        
                        # ส่ง line_payload จาก API โดยตรง
                        line_payload = api_response.get("line_payload", [])
                        if line_payload:
                            send_line_payload(user_id, line_payload)
                        else:
                            # กรณีไม่พบข้อมูลช่วงเวลา
                            line_bot_api.push_message(
                                user_id,
                                TextSendMessage(text="❗ ไม่พบช่วงเวลาว่างในวันที่เลือก กรุณาเลือกวันที่อื่น")
                            )
                            # กลับไปยังหน้าเลือกวันที่
                            session["state"] = "select_date"
                            if "selected_date" in session:
                                del session["selected_date"]
                            if "selected_date_iso" in session:
                                del session["selected_date_iso"]
                    else:
                        line_bot_api.push_message(
                            user_id,
                            TextSendMessage(text=f"❗ เกิดข้อผิดพลาดในการค้นหาช่วงเวลา ({response.status_code}) กรุณาลองใหม่ภายหลัง")
                        )
                except Exception as e:
                    print(f"❌ เกิดข้อผิดพลาดในการดึงช่วงเวลา: {e}")
                    line_bot_api.push_message(
                        user_id,
                        TextSendMessage(text=f"เกิดข้อผิดพลาดในการเชื่อมต่อกับระบบ: {str(e)} กรุณาลองใหม่ภายหลัง")
                    )
            # ตั้งเวลาเรียกฟังก์ชันหลังจากส่งข้อความยืนยัน
            scheduler.add_job(
                func=get_available_timeslots_later,
                trigger="date",
                run_date=datetime.now() + timedelta(seconds=1)
            )
        else:
            # ถ้าผู้ใช้ไม่ได้เลือกวันที่จากรายการ ให้แสดงรายการอีกครั้ง
            # ตรวจสอบก่อนว่า available_dates มีข้อมูลหรือไม่
            if available_dates:
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
            # else:
            #     # ถ้าไม่มีวันที่ในรายการ (กรณีที่ session อาจถูกล้าง) ให้เรียก API ใหม่
            #     line_bot_api.reply_message(
            #         event.reply_token,
            #         TextSendMessage(text="กำลังค้นหาวันที่ว่าง โปรดรอสักครู่...")
            #     )
            #     # เรียก API เพื่อดึงข้อมูลวันที่ใหม่
                
            #     # ตั้งเวลาเรียกฟังก์ชันหลังจากส่งข้อความยืนยัน
            #     scheduler.add_job(
            #         func=get_available_dates_again,
            #         trigger="date",
            #         run_date=datetime.now() + timedelta(seconds=1)
            #     )
    # Time slot selection
    elif session["state"] == "select_time_slot":
        if text == "ย้อนกลับ":  # จัดการปุ่มย้อนกลับ
            # กลับไปเลือกวันที่
            session["state"] = "select_date"
            # ล้างข้อมูลเลือกเวลาที่เลือกไว้
            if "selected_date" in session:
                del session["selected_date"]
            if "selected_date_iso" in session:
                del session["selected_date_iso"]
            
            # ใช้ข้อมูลวันที่ที่เก็บไว้แล้วในตัวแปร available_time_slots
            if "available_time_slots" in session and session["available_time_slots"]:
                # เรียกใช้ฟังก์ชันแสดงรายการวันที่
                display_date_selection(event.reply_token, session["available_time_slots"])
            else:
                # กรณีที่ไม่มีข้อมูล available_time_slots จึงต้องเรียก API ใหม่
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="กำลังค้นหาวันที่ว่าง โปรดรอสักครู่...")
                )
                # เรียก API เพื่อดึงข้อมูลวันที่ใหม่
                def get_available_dates_again():
                    try:
                        profile_json = {
                            "location": session.get("location"),
                            "english_min": 5 if session.get("eng_level") == "ระดับ 5" else 4,
                            "exp_kind": "strong" if session.get("exp") == "Strong exp" else "non",
                            "age_key": str(session.get("age")),
                            "start_date": datetime.now().strftime("%Y-%m-%d"),
                            "include_holidays": True
                        }

                        response = requests.post(
                            f"{base_url}/events/available-dates",
                            json=profile_json,
                            timeout=30
                        )
                        
                        if response.status_code == 200:
                            api_response = response.json()
                            
                            # เก็บข้อมูลวันที่ว่างสำหรับให้โค้ดส่วนอื่นใช้
                            if "available_dates" in api_response:
                                # สร้าง available_time_slots ในรูปแบบเดิม
                                available_time_slots = []
                                for date_str in api_response["available_dates"]:
                                    available_time_slots.append({"date": date_str})
                                session["available_time_slots"] = available_time_slots
                            
                            # ส่ง line_payload จาก API โดยตรง
                            line_payload = api_response.get("line_payload", [])
                            if line_payload:
                                send_line_payload(user_id, line_payload)
                        else:
                            line_bot_api.push_message(
                                user_id,
                                TextSendMessage(text="❗ เกิดข้อผิดพลาดในการค้นหาวันที่ว่าง กรุณาลองใหม่ภายหลัง")
                            )
                    except Exception as e:
                        print(f"❌ เกิดข้อผิดพลาดในการดึงวันที่: {e}")
                        line_bot_api.push_message(
                            user_id,
                            TextSendMessage(text="เกิดข้อผิดพลาดในการเชื่อมต่อกับระบบ กรุณาลองใหม่ภายหลัง")
                        )
                        
                # ตั้งเวลาเรียกฟังก์ชันหลังจากส่งข้อความยืนยัน
                scheduler.add_job(
                    func=get_available_dates_again,
                    trigger="date",
                    run_date=datetime.now() + timedelta(seconds=1)
                )
                
                return
            
        # ตรวจสอบการเลือกช่วงเวลา โดยรองรับทั้งรูปแบบ (1), (2) หรือเลขล้วนๆ
        slot_choice = text.strip()
        if slot_choice.startswith("(") and slot_choice.endswith(")"):
            slot_choice = slot_choice[1:-1]  # ตัด ( ) ออก
        
        try:
            slot_number = int(slot_choice)
            if 1 <= slot_number <= len(session.get("time_slots", [])):
                selected_time_slot = session["time_slots"][slot_number - 1]
                session["selected_time_slot"] = selected_time_slot
                session["selected_time"] = selected_time_slot.get("time", "")  # เก็บเวลาที่เลือกไว้
                
                # ส่งข้อความยืนยันการเลือกช่วงเวลา
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"คุณเลือกเวลา {session['selected_time']} กำลังค้นหาคู่ที่ว่าง...")
                )
                
                # เรียก API เพื่อดึงข้อมูลคู่ที่ว่าง
                def get_available_pairs_later():
                    try:
                        # สร้าง payload สำหรับ API
                        pair_request = {
                            "date": session["selected_date_iso"],
                            "time_slot": session["selected_time"],
                            "location": session.get("location", ""),
                            "english_min": 5 if session.get("eng_level") == "ระดับ 5" else 4,
                            "exp_kind": "strong" if session.get("exp") == "Strong exp" else "non",
                            "age_key": str(session.get("age", ""))
                        }
                        
                        print(f"🚀 Sending request to get available pairs: {pair_request}")
                        
                        # เรียก API
                        response = requests.post(
                            f"{base_url}/events/available-pairs",
                            json=pair_request,
                            timeout=30
                        )
                        
                        print(f"📡 API Response (status): {response.status_code}")
                        
                        if response.status_code == 200:
                            api_response = response.json()
                            print(f"📦 API Response (available_pairs): {api_response}")
                            
                            # เปลี่ยนสถานะเป็น select_pair
                            session["state"] = "select_pair"
                            
                            # เก็บข้อมูลคู่ที่ว่างลงใน session
                            if "available_pairs" in api_response:
                                # อัปเดต pair_details ใน selected_time_slot
                                session["selected_time_slot"]["pair_details"] = api_response["available_pairs"]
                            
                            # ส่ง line_payload จาก API โดยตรง
                            line_payload = api_response.get("line_payload", [])
                            if line_payload:
                                send_line_payload(user_id, line_payload)
                            else:
                                # หากไม่มี line_payload ให้ใช้ฟังก์ชันเดิม
                                send_pair_selection(user_id, session["selected_time_slot"])
                        else:
                            line_bot_api.push_message(
                                user_id,
                                TextSendMessage(text=f"❗ เกิดข้อผิดพลาดในการค้นหาคู่ที่ว่าง ({response.status_code}) กรุณาลองใหม่ภายหลัง")
                            )
                    except Exception as e:
                        print(f"❌ เกิดข้อผิดพลาดในการดึงข้อมูลคู่: {e}")
                        line_bot_api.push_message(
                            user_id,
                            TextSendMessage(text=f"เกิดข้อผิดพลาดในการเชื่อมต่อกับระบบ: {str(e)} กรุณาลองใหม่ภายหลัง")
                        )
                
                # ตั้งเวลาเรียกฟังก์ชันหลังจากส่งข้อความยืนยัน
                scheduler.add_job(
                    func=get_available_pairs_later,
                    trigger="date",
                    run_date=datetime.now() + timedelta(seconds=1)
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"กรุณาเลือกช่วงเวลาจากตัวเลือกที่กำหนดให้ (ตัวเลข 1-{len(session.get('time_slots', []))})")
                )
        except ValueError:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณาเลือกช่วงเวลาที่ถูกต้อง")
            )
            
    # ส่วนการเลือกคู่
    elif session["state"] == "select_pair":
        if text == "ย้อนกลับ":  # เพิ่มการจัดการปุ่มย้อนกลับ
            # กลับไปเลือกช่วงเวลา
            session["state"] = "select_time_slot"
            # ล้างข้อมูลคู่ที่เลือกไว้
            if "selected_pair" in session:
                del session["selected_pair"]
                
            # เรียก API เพื่อดึงข้อมูลช่วงเวลาที่ว่างใหม่
            def get_available_timeslots_again():
                try:
                    # สร้าง payload สำหรับ API
                    date_request = {
                        "date": session["selected_date_iso"],
                        "location": session.get("location", ""),
                        "english_min": 5 if session.get("eng_level") == "ระดับ 5" else 4,
                        "exp_kind": "strong" if session.get("exp") == "Strong exp" else "non",
                        "age_key": str(session.get("age", ""))
                    }
                    
                    # เรียก API
                    response = requests.post(
                        f"{base_url}/events/available-timeslots",
                        json=date_request,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        api_response = response.json()
                        
                        # เก็บข้อมูลช่วงเวลาที่ว่างลงใน session - ปรับให้เข้ากับข้อมูลเดิม
                        if "available_timeslots" in api_response:
                            time_slots = []
                            for slot in api_response["available_timeslots"]:
                                # แปลงข้อมูลให้เข้ากับรูปแบบเดิม
                                pairs = []
                                pair_details = []
                                
                                # สร้าง pair และ pair_details จาก available_pairs
                                for pair_info in slot.get("available_pairs", []):
                                    pair_name = pair_info.get("pair", "")
                                    pairs.append(pair_name)
                                    pair_details.append(pair_info)
                                
                                time_slots.append({
                                    "time": slot.get("time_slot", ""),
                                    "available_pairs": pairs,
                                    "pair_details": pair_details
                                })
                                
                            session["time_slots"] = time_slots
                        
                        # ส่ง line_payload จาก API โดยตรง
                        line_payload = api_response.get("line_payload", [])
                        if line_payload:
                            send_line_payload(user_id, line_payload)
                        else:
                            # หากไม่มี line_payload ให้ใช้ฟังก์ชันเดิม
                            send_time_slots(user_id, session["time_slots"], session["selected_date"])
                    else:
                        line_bot_api.push_message(
                            user_id,
                            TextSendMessage(text="❗ เกิดข้อผิดพลาดในการค้นหาช่วงเวลา กรุณาลองใหม่ภายหลัง")
                        )
                except Exception as e:
                    print(f"❌ เกิดข้อผิดพลาดในการดึงช่วงเวลา: {e}")
                    line_bot_api.push_message(
                        user_id,
                        TextSendMessage(text="เกิดข้อผิดพลาดในการเชื่อมต่อกับระบบ กรุณาลองใหม่ภายหลัง")
                    )
                    
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"กลับไปยังหน้าเลือกช่วงเวลา...")
            )
            
            # ตั้งเวลาเรียกฟังก์ชันหลังจากส่งข้อความยืนยัน
            scheduler.add_job(
                func=get_available_timeslots_again,
                trigger="date",
                run_date=datetime.now() + timedelta(seconds=1)
            )
            
            return
                
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
                
                # สร้างข้อมูล JSON สำหรับส่งออก
                session["booking_payload"] = {
                    "users": [
                        {"email": selected_pair["manager"]["email"]},
                        {"email": selected_pair["recruiter"]["email"]}
                    ],
                    "start_date": iso_date,
                    "end_date": iso_date,
                    "start_time": start_time.strip(),
                    "end_time": end_time.strip()
                }

                print("📦 Booking Payload JSON:", json.dumps(session["booking_payload"], indent=2))
                
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
        if text == "ย้อนกลับ":  # เพิ่มการจัดการปุ่มย้อนกลับ
            # กลับไปเลือกคู่ Manager-Recruiter
            session["state"] = "select_pair"
            # ล้างข้อมูลคู่ที่เลือกไว้
            if "selected_pair" in session:
                del session["selected_pair"]
            if "emails" in session:
                del session["emails"]
            if "start_time" in session:
                del session["start_time"]
            if "end_time" in session:
                del session["end_time"]
            # ส่งหน้าเลือกคู่ใหม่
            send_pair_selection(event.reply_token, session["selected_time_slot"])
            return
            
        if text == "สร้างนัด":
            # ตั้งค่าชื่อและรายละเอียดการประชุมแบบตายตัว แทนการไปยังสถานะ meeting_name
            session["meeting_name"] = "นัดประชุม"
            session["meeting_description"] = "นัดสัมภาษณ์งานหน่อยครับผม ครับพี่ ดีครับเพื่อน"
            
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
            
            # สร้างข้อความยืนยันการนัดหมาย
            meeting_confirmation = create_meeting_confirmation(meeting_info)
            
            # ส่งข้อความยืนยันการนัดหมาย
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=meeting_confirmation)
            )

            # ส่งข้อมูลให้ไป api
            scheduler.add_job(
                    func=send_book_meeting,
                    args=[meeting_result],
                    trigger="date",
                    run_date=datetime.now() + timedelta(seconds=10)
                )
            
            # รีเซ็ตสถานะและแสดงเมนูหลัก
            profile_data = {k: session[k] for k in ["age", "exp", "eng_level", "location", "available_time_slots"] if k in session}
            session.clear()
            session.update(profile_data)
            session["state"] = "initial"
            session["profile_completed"] = True
            
            # เพิ่มการแสดงเมนูหลักหลังการทำงานเสร็จสิ้น
            send_menu_only(user_id)
            # scheduler.add_job(
            #     func=send_menu_only,
            #     args=[user_id],
            #     trigger="date",
            #     run_date=datetime.now() + timedelta(seconds=12)
            # )
            
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
            send_menu_only(user_id)
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณาเลือกจากตัวเลือกที่กำหนดให้ (สร้างนัด, ยกเลิกนัด หรือ ย้อนกลับ)")
            )
       
def send_initial_options(reply_token_or_user_id):
    """ส่งข้อความแนะนำ + Quick Reply"""
    message = TextSendMessage(
        text="📌 นี่คือ LINE Chat นัดประชุมอัจฉริยะ\nกรุณาเลือกเมนูด้านล่างเพื่อเริ่มใช้งาน:",
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="กรอกข้อมูล Manager", text="กรอกข้อมูล Manager")),
            QuickReplyButton(action=MessageAction(label="วิธีการใช้", text="วิธีการใช้")),
            QuickReplyButton(action=MessageAction(label="login(M&R)", text="login(สำหรับ Manager & Recruiter)"))
        ])
    )

    if isinstance(reply_token_or_user_id, str) and reply_token_or_user_id.startswith("U"):
        line_bot_api.push_message(reply_token_or_user_id, message)
    else:
        line_bot_api.reply_message(reply_token_or_user_id, message)

# สร้างฟังก์ชันใหม่สำหรับแสดงเฉพาะเมนู (ไม่มีข้อความแนะนำ)
def send_menu_only(reply_token_or_user_id):
    """ส่ง Quick Reply เมนูแบบสั้นๆ"""
    message = TextSendMessage(
        text=":>",  # ✅ ต้องมี text อย่างน้อย 1 ตัวอักษร
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="กรอกข้อมูล Manager", text="กรอกข้อมูล Manager")),
            QuickReplyButton(action=MessageAction(label="วิธีการใช้", text="วิธีการใช้")),
            QuickReplyButton(action=MessageAction(label="login(M&R)", text="login(สำหรับ Manager & Recruiter)"))
        ])
    )

    if isinstance(reply_token_or_user_id, str) and reply_token_or_user_id.startswith("U"):
        line_bot_api.push_message(reply_token_or_user_id, message)
    else:
        line_bot_api.reply_message(reply_token_or_user_id, message)

def send_line_payload(user_id_or_reply_token, line_payload):
    """
    ส่ง LINE Payload ไปยัง LINE API โดยแปลงจาก dictionary เป็น LINE SDK objects
    รองรับทั้ง user_id และ reply_token
    """
    is_reply_token = not (isinstance(user_id_or_reply_token, str) and user_id_or_reply_token.startswith("U"))
    
    for message_dict in line_payload:
        # แปลง dictionary เป็น LINE SDK object
        if message_dict["type"] == "text":
            # TextSendMessage
            if "quickReply" in message_dict:
                # มี Quick Reply
                items = []
                for item in message_dict["quickReply"]["items"]:
                    if item["type"] == "action" and item["action"]["type"] == "message":
                        items.append(
                            QuickReplyButton(
                                action=MessageAction(
                                    label=item["action"]["label"],
                                    text=item["action"]["text"]
                                )
                            )
                        )
                
                quick_reply = QuickReply(items=items)
                message = TextSendMessage(
                    text=message_dict["text"],
                    quick_reply=quick_reply
                )
            else:
                # ไม่มี Quick Reply
                message = TextSendMessage(text=message_dict["text"])
            
            # ส่งข้อความ
            if is_reply_token:
                line_bot_api.reply_message(user_id_or_reply_token, message)
            else:
                line_bot_api.push_message(user_id_or_reply_token, message)
                
        # สามารถเพิ่มเงื่อนไขสำหรับประเภทข้อความอื่นๆ เช่น image, template, flex ได้ตามต้องการ
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

    # เปลี่ยนปุ่ม 'ยกเลิก' เป็น 'ย้อนกลับ'
    items.append(QuickReplyButton(action=MessageAction(label="ย้อนกลับ", text="ย้อนกลับ")))

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
    
    # แสดง quick reply สำหรับเลือกคู่ Manager-Recruiter (สูงสุด 12 รายการเพื่อเหลือที่สำหรับปุ่มย้อนกลับ)
    items = [
        QuickReplyButton(action=MessageAction(label=f"({i})", text=f"({i})"))
        for i in range(1, min(len(pairs) + 1, 13))
    ]
    
    # เพิ่มปุ่มย้อนกลับ
    items.append(QuickReplyButton(action=MessageAction(label="ย้อนกลับ", text="ย้อนกลับ")))
    
    quick_reply = QuickReply(items=items)
    
    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text=message_text, quick_reply=quick_reply)
    )
    
def send_meeting_confirmation(reply_token, meeting_summary):
    """Send meeting confirmation"""
    items = [
        QuickReplyButton(action=MessageAction(label="ยืนยันนัด", text="สร้างนัด")),
        QuickReplyButton(action=MessageAction(label="ยกเลิกนัด", text="ยกเลิกนัด")),
        QuickReplyButton(action=MessageAction(label="ย้อนกลับ", text="ย้อนกลับ"))  # เพิ่มปุ่มย้อนกลับ
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

###### use api #######
def send_book_meeting(meeting_result):
            try:
                print("🚀 POST ข้อมูล:", meeting_result.dict())
                print(base_url)
                response = requests.post(
                    f"{base_url}/events/create-bulk",
                    json=meeting_result.dict(),
                    headers={"Content-Type": "application/json"},
                    timeout=30 # ถ้า timeout น้อยจะขึ้น timeout แล้วก็จะไปบุ๊คใน calendar 2 ครั้ง
                )
                print("✅ POST สำเร็จ:", response.status_code)
            except Exception as e:
                print("❌ POST ล้มเหลว:", str(e))
def display_date_selection(reply_token_or_user_id, available_time_slots):
    """
    แสดงรายการวันที่ให้เลือกจากข้อมูล available_time_slots
    ใช้ข้อมูลที่มีอยู่แล้วโดยไม่ต้องเรียก API ใหม่
    """
    available_dates = []
    
    # แปลงข้อมูลวันที่จากรูปแบบ ISO เป็นรูปแบบไทย (วว/ดด/25XX)
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
    
    # ส่งข้อความ (รองรับทั้ง reply_token และ user_id)
    if isinstance(reply_token_or_user_id, str) and reply_token_or_user_id.startswith("U"):
        # It's a user_id
        line_bot_api.push_message(reply_token_or_user_id, message)
    else:
        # It's a reply_token
        line_bot_api.reply_message(reply_token_or_user_id, message)
        
def display_time_slot_selection(reply_token_or_user_id, time_slots, selected_date):
    """
    แสดงรายการช่วงเวลาให้เลือกจากข้อมูล time_slots
    ใช้ข้อมูลที่มีอยู่แล้วโดยไม่ต้องเรียก API ใหม่
    """
    slot_texts = []

    for i, slot in enumerate(time_slots[:12], start=1):  # จำกัดที่ 12 อัน
        pairs_text = "\n   " + "\n   ".join([f"👥{pair}" for pair in slot.get("available_pairs", [])])
        slot_text = f"{i}. เวลา {slot.get('time', '')}{pairs_text}"
        slot_texts.append(slot_text)

    if not slot_texts:
        # ถ้าไม่มีช่วงเวลา ให้แจ้งผู้ใช้
        message = TextSendMessage(
            text="ไม่พบช่วงเวลาว่างในวันที่เลือก กรุณาเลือกวันที่อื่น"
        )
    else:
        message_text = f"กรุณาเลือกช่วงเวลาที่ต้องการ:\nวันที่ : {selected_date}\n" + "\n".join(slot_texts)

        # สร้างปุ่ม quick reply สำหรับช่วงเวลา
        items = [
            QuickReplyButton(action=MessageAction(label=f"({i})", text=f"({i})"))
            for i in range(1, len(slot_texts) + 1)
        ]

        # เพิ่มปุ่มย้อนกลับ
        items.append(QuickReplyButton(action=MessageAction(label="ย้อนกลับ", text="ย้อนกลับ")))

        quick_reply = QuickReply(items=items)

        message = TextSendMessage(text=message_text, quick_reply=quick_reply)

    # ส่งข้อความ (รองรับทั้ง reply_token และ user_id)
    if isinstance(reply_token_or_user_id, str) and reply_token_or_user_id.startswith("U"):
        # It's a user_id
        line_bot_api.push_message(reply_token_or_user_id, message)
    else:
        # It's a reply_token
        line_bot_api.reply_message(reply_token_or_user_id, message)

def display_pair_selection(reply_token_or_user_id, time_slot):
    """
    แสดงรายการคู่ Manager-Recruiter ให้เลือกจากข้อมูล time_slot
    ใช้ข้อมูลที่มีอยู่แล้วโดยไม่ต้องเรียก API ใหม่
    """
    if not time_slot or "pair_details" not in time_slot:
        # ถ้าไม่มีข้อมูลคู่ ให้แจ้งผู้ใช้
        message = TextSendMessage(
            text="ไม่พบข้อมูลคู่ Manager-Recruiter ที่ว่าง กรุณาเลือกช่วงเวลาใหม่"
        )
    else:
        pairs = time_slot["pair_details"]
        
        if not pairs:
            message = TextSendMessage(
                text="ไม่พบคู่ Manager-Recruiter ที่ว่างในช่วงเวลานี้ กรุณาเลือกช่วงเวลาอื่น"
            )
        else:
            message_text = f"กรุณาเลือก Manager-Recruiter ที่จะนัด\nเวลา {time_slot.get('time', '')}\n"
            
            for i, pair_detail in enumerate(pairs, start=1):
                message_text += f"   {i}.👥 {pair_detail.get('pair', '')}\n"
            
            # สร้างปุ่ม quick reply สำหรับเลือกคู่ (สูงสุด 12 รายการ + ปุ่มย้อนกลับ)
            items = [
                QuickReplyButton(action=MessageAction(label=f"({i})", text=f"({i})"))
                for i in range(1, min(len(pairs) + 1, 13))
            ]
            
            # เพิ่มปุ่มย้อนกลับ
            items.append(QuickReplyButton(action=MessageAction(label="ย้อนกลับ", text="ย้อนกลับ")))
            
            quick_reply = QuickReply(items=items)
            
            message = TextSendMessage(text=message_text, quick_reply=quick_reply)
    
    # ส่งข้อความ (รองรับทั้ง reply_token และ user_id)
    if isinstance(reply_token_or_user_id, str) and reply_token_or_user_id.startswith("U"):
        # It's a user_id
        line_bot_api.push_message(reply_token_or_user_id, message)
    else:
        # It's a reply_token
        line_bot_api.reply_message(reply_token_or_user_id, message)

#API FUNCTION
def background_post_and_push(user_id, session_data):
                try:
                    profile_json = {
                        "location": session_data.get("location"),
                        "english_min": 5 if session_data.get("eng_level") == "ระดับ 5" else 4,
                        "exp_kind": "strong" if session_data.get("exp") == "Strong exp" else "non",
                        "age_key": str(session_data.get("age")),
                        "start_date": datetime.now().strftime("%Y-%m-%d"),
                        "include_holidays": True
                    }
                    # print("🚀 Background Started with data:", profile_json)

                    response = requests.post(
                        f"{base_url}/events/available-dates",
                        json=profile_json,
                        timeout=30
                    )
                    response.raise_for_status()
                    api_response = response.json()
                    print(api_response)
                    
                    if response.status_code == 200:
                        user_sessions[user_id]["state"] = "select_date"
                        
                        # เก็บข้อมูลวันที่สำหรับให้โค้ดส่วนอื่นใช้
                        if "available_dates" in api_response:
                            # สร้าง available_time_slots ในรูปแบบเดิม
                            available_time_slots = []
                            for date_str in api_response["available_dates"]:
                                available_time_slots.append({"date": date_str})
                            user_sessions[user_id]["available_time_slots"] = available_time_slots
                        
                        # แสดงข้อความยืนยันการบันทึกข้อมูล
                        line_bot_api.push_message(
                            user_id,
                            TextSendMessage(text="บันทึกข้อมูลเรียบร้อยแล้ว ต่อไปเป็นการนัดประชุม")
                        )
                        
                        # ส่ง line_payload ไปที่ LINE API
                        line_payload = api_response.get("line_payload", [])
                        print(line_payload)
                        if line_payload:
                            send_line_payload(user_id, line_payload)
                        
                    else:
                        line_bot_api.push_message(
                            user_id,
                            TextSendMessage(text="❗ เกิดข้อผิดพลาด กรุณาลองใหม่ภายหลัง")
                        )
                    
                    print("✅ ส่งข้อมูล Manager ไปยัง API แล้ว:", response.status_code)
                except Exception as e:
                    print("❌ ส่งข้อมูลล้มเหลว:", e)
                    line_bot_api.push_message(
                        user_id,
                        TextSendMessage(text="เกิดข้อผิดพลาดในการเชื่อมต่อกับระบบ กรุณาลองใหม่ภายหลัง")
                    )


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8001)