import os
import sys
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any
from dotenv import load_dotenv
from pydantic import BaseModel
from urllib.parse import quote
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    FlexSendMessage, QuickReply, QuickReplyButton, MessageAction,
    PostbackEvent
)
import requests
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from test import send_post, get_available_users

# LINE API configuration
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# Session storage (in production, use a database)
user_sessions = {}

# Mockup data for user schedules (busy times)
user_schedules = {
    "panupongpr3841@gmail.com": {
        "2025-04-21": [
            ["09:00", "10:00"],
            ["12:30", "13:30"],
            ["18:00", "19:00"]
        ],
        "2025-04-24": [
            ["00:00", "23:59"]  # All day busy
        ]
    },
    "panupongnu4@gmail.com": {
        "2025-04-21": [
            ["10:15", "11:15"],
            ["14:00", "15:00"],
            ["17:00", "18:00"]
        ]
    }
}

# Model for meeting creation result
class MeetingResult(BaseModel):
    user_emails: List[str]
    summary: str
    description: str = ""
    location: str = ""
    start_time: str
    end_time: str
    attendees: List[Any] = []


# def add_user_email(email):
#     """Add a new user email to the available users list."""
#     # For production, this should update a database
#     if email not in available_users:
#         available_users.append(email)
#         return True
#     return False

def validate_email(email):
    """Simple email validation."""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None
def parse_time_range(time_range: str) -> tuple:
    """Parse time range string (e.g., '13:00 - 14:00') into start and end times."""
    try:
        start_time, end_time = time_range.split("-")
        return start_time.strip(), end_time.strip()
    except:
        try:
            start_time, end_time = time_range.split("to")
            return start_time.strip(), end_time.strip()
        except:
            raise ValueError("Invalid time range format. Please use format like '13:00 - 14:00'")

def is_time_available(date: str, start_time: str, end_time: str, users: List[str]) -> bool:
    """Check if all users are available at the given date and time."""
    for user in users:
        if user not in user_schedules:
            continue  # User has no schedule, so they're available
        
        if date in user_schedules[user]:
            for busy_period in user_schedules[user][date]:
                busy_start, busy_end = busy_period
                
                # Check for overlap
                if (start_time <= busy_end and end_time >= busy_start):
                    return False
    
    return True

def find_available_slots(date_range: List[str], time_range: str, users: List[str]) -> List[Dict]:
    """Find available meeting slots within the given date range and time."""
    start_time, end_time = parse_time_range(time_range)
    available_slots = []
    
    for date in date_range:
        if is_time_available(date, start_time, end_time, users):
            available_slots.append({
                "date": date,
                "start_time": start_time,
                "end_time": end_time
            })
    
    return available_slots

def generate_date_range(start_date: str, end_date: str) -> List[str]:
    """Generate a list of dates between start_date and end_date (inclusive)."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    
    date_range = []
    current = start
    
    while current <= end:
        date_range.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    
    return date_range

def create_login_message():
    """Create the main menu message."""
    return TextSendMessage(
        text="สวัสดี 👋 ยินดีต้อนรับสู่ระบบนัดประชุมอัตโนมัติ\nกรุณาเข้าสู่ระบบก่อนเข้าใช้งานนัดประชุมของเรา",
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="📋 เข้าสู่ระบบ", text="login")),
            QuickReplyButton(action=MessageAction(label="❓ วิธีใช้งาน", text="วิธีใช้งาน"))
        ])
    )

def create_main_menu_message():
    """Create the main menu message."""
    return TextSendMessage(
        text="สวัสดีครับ 👋 ยินดีต้อนรับสู่ระบบนัดประชุมอัตโนมัติ\nคุณต้องการทำอะไรครับ?",
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="🗓️ สร้างนัดประชุม", text="สร้างนัดประชุม")),
            QuickReplyButton(action=MessageAction(label="📋 ดูนัดประชุมที่มี", text="ดูนัดประชุมที่มี")),
            QuickReplyButton(action=MessageAction(label="📧 เพิ่มอีเมลผู้ใช้", text="เพิ่มอีเมล")),
            QuickReplyButton(action=MessageAction(label="❓ วิธีใช้งาน", text="วิธีใช้งาน"))
        ])
    )

def create_calendar_flex_message(user_id):
    """Create a calendar date picker flex message."""
    # This is a simplified version, you would need to create a proper calendar UI in production
    
    # Get today's date and the next 7 days for the example
    today = datetime.now()
    
    # Create a date picker for both start and end dates
    return FlexSendMessage(
        alt_text="เลือกวันที่ประชุม",
        contents={
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "เลือกวันที่ประชุม",
                        "weight": "bold",
                        "size": "lg"
                    },
                    {
                        "type": "text",
                        "text": "กรุณาเลือกวันที่เริ่มต้น",
                        "margin": "md"
                    },
                    {
                        "type": "button",
                        "action": {
                            "type": "datetimepicker",
                            "label": "เลือกวันที่เริ่มต้น",
                            "data": f"start_date_{user_id}",
                            "mode": "date"
                        },
                        "style": "primary",
                        "margin": "md"
                    },
                    {
                        "type": "text",
                        "text": "กรุณาเลือกวันที่สิ้นสุด (เลือกวันเดียวกับเริ่มต้นได้)",
                        "margin": "md"
                    },
                    {
                        "type": "button",
                        "action": {
                            "type": "datetimepicker",
                            "label": "เลือกวันที่สิ้นสุด",
                            "data": f"end_date_{user_id}",
                            "mode": "date"
                        },
                        "style": "primary",
                        "margin": "md"
                    }
                ]
            }
        }
    )

def create_user_selection_flex_message(user_id):
    """Create a user selection flex message."""
    # available_users = ['0827703801p@gmail.com', 'khunnapatt65@gmail.com', 'pemadee2546@gmail.com']
    available_users = get_available_users()
    items = []
    
    for i, email in enumerate(available_users):

        items.append({
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "image",
                            "url": "https://img.icons8.com/ios-filled/100/000000/user-male-circle.png",  # ใช้แทน icon รูปคน
                            "size": "xs",
                            "aspectMode": "cover",
                            "aspectRatio": "1:1",
                            "gravity": "center"
                        },
                        {
                            "type": "text",
                            "text": email,
                            "wrap": True,
                            "size": "sm",
                            "color": "#333333",
                            "margin": "md"
                        }
                    ],
                    "spacing": "md",
                    "alignItems": "center"
                },
                {
                    "type": "button",
                    "action": {
                        "type": "postback",
                        "label": "เลือก",
                        "data": f"select_user_{user_id}_{email}"
                    },
                    "style": "primary",
                    "height": "sm",
                    "margin": "md",
                    "color": "#00C16A"  # เขียวดูโปร ไม่แสบตา
                }
            ],
            "paddingAll": "12px",
            "backgroundColor": "#FFFFFF",
            "cornerRadius": "12px",
            "margin": "sm",
            "spacing": "sm",
            "borderColor": "#DDDDDD",
            "borderWidth": "1px"
        })

    
    return FlexSendMessage(
        alt_text="เลือกผู้เข้าร่วมประชุม",
        contents={
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "เลือกผู้เข้าร่วมประชุม",
                        "weight": "bold",
                        "size": "lg"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": items,
                        "margin": "md"
                    },
                    {
                        "type": "button",
                        "action": {
                            "type": "postback",
                            "label": "ยืนยันผู้เข้าร่วม",
                            "data": f"confirm_users_{user_id}"
                        },
                        "style": "secondary",
                        "margin": "md"
                    }
                ]
            }
        }
    )

def create_meeting_summary_flex_message(user_id, meeting_data):
    """Create a meeting summary flex message."""

    return FlexSendMessage(
        alt_text="สรุปข้อมูลการนัดหมาย",
        contents={
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "📝 สรุปข้อมูลการนัดหมาย",
                        "weight": "bold",
                        "size": "lg"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "📌 ชื่อ: ",
                                        "weight": "bold",
                                        "margin": "sm",
                                        "flex": 0
                                    },
                                    {
                                        "type": "text",
                                        "text": meeting_data["name"],
                                        "wrap": True,
                                        "flex": 5
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "📆 วันที่: ",
                                        "weight": "bold",
                                        "margin": "sm",
                                        "flex": 0
                                    },
                                    {
                                        "type": "text",
                                        "text": meeting_data["date"],
                                        "wrap": True
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "⏰ เวลา: ",
                                        "weight": "bold",
                                        "margin": "sm",
                                        "flex": 0
                                    },
                                    {
                                        "type": "text",
                                        "text": f"{meeting_data['start_time']} - {meeting_data['end_time']}",
                                        "wrap": True
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "vertical",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "👥 ผู้เข้าร่วม:",
                                        "weight": "bold",
                                        "margin": "sm",
                                        "flex": 0
                                    },
                                    *[
                                        {
                                            "type": "text",
                                            "text": f"- {attendee}",
                                            "wrap": True,
                                            "margin": "sm"
                                        }
                                        for attendee in meeting_data["attendees"]
                                    ]
                                ]
                            }
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "button",
                                "action": {
                                    "type": "postback",
                                    "label": "✅ ยืนยัน",
                                    "data": f"confirm_meeting_{user_id}"
                                },
                                "style": "primary"
                            },
                            {
                                "type": "button",
                                "action": {
                                    "type": "postback",
                                    "label": "🔄 แก้ไข",
                                    "data": f"edit_meeting_{user_id}"
                                },
                                "style": "secondary"
                            },
                            {
                                "type": "button",
                                "action": {
                                    "type": "postback",
                                    "label": "❌ ยกเลิก",
                                    "data": f"cancel_meeting_{user_id}"
                                },
                                "style": "secondary"
                            }
                        ]
                    }
                ]
            }
        }
    )


def create_available_slots_flex_message(user_id, available_slots):
    """Create a flex message with available meeting slots."""
    items = []
    
    for i, slot in enumerate(available_slots):
        date_format = datetime.strptime(slot["date"], "%Y-%m-%d").strftime("%d/%m")
        items.append({
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": f"{i+1}️⃣ {date_format} เวลา {slot['start_time']} - {slot['end_time']}",
                    "wrap": True,
                    "size": "sm",
                    "weight": "regular"
                },
                {
                    "type": "button",
                    "action": {
                        "type": "postback",
                        "label": f"เลือกอันที่ {i+1}",
                        "data": f"select_slot_{user_id}_{i}"
                    },
                    "style": "primary",
                    "height": "sm",
                    "margin": "sm"
                }
            ],
            "spacing": "sm",
            "margin": "md"
        })
    
    return FlexSendMessage(
        alt_text="เลือกช่วงเวลาที่ว่าง",
        contents={
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "✅ พบช่วงเวลาว่างที่ตรงกัน:",
                        "weight": "bold",
                        "size": "lg",
                        "wrap": True
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": items,
                        "margin": "md"
                    }
                ]
            }
        }
    )
    
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_id = event.source.user_id
    text = event.message.text

    
    # Initialize user session if not exists
    if user_id not in user_sessions:
        user_sessions[user_id] = {"step": "main_menu"}
        
        
    if text.lower() == "เพิ่มอีเมล":
        user_sessions[user_id] = {
            "step": "enter_email",
        }
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="กรุณากรอกอีเมลที่ต้องการเพิ่มเข้าระบบ:")
        )
    
    # Main menu or trigger command
    if text.lower() == "นัดประชุม" or text.lower() == "สร้างนัดประชุม":
        user_sessions[user_id] = {
            "step": "enter_meeting_name",
            "meeting_data": {}
        }
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="กรุณากรอกชื่อการประชุม:")
        )
    
     # Add this new condition for handling email input
    elif user_sessions[user_id]["step"] == "enter_email":
        # Save email and proceed to confirmation
        email = text.strip()
        # Validate email format
        if not validate_email(email):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="รูปแบบอีเมลไม่ถูกต้อง กรุณากรอกอีเมลใหม่")
            )
            return
        user_sessions[user_id]["email"] = email
        user_sessions[user_id]["step"] = "confirm_email"
        
        
        # Display confirmation message with buttons
        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(
                alt_text="ยืนยันการเพิ่มอีเมล",
                contents={
                    "type": "bubble",
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "ยืนยันการเพิ่มอีเมล",
                                "weight": "bold",
                                "size": "lg"
                            },
                            {
                                "type": "text",
                                "text": f"อีเมล: {email}",
                                "margin": "md",
                                "wrap": True
                            },
                            {
                                "type": "text",
                                "text": "คุณต้องการเพิ่มอีเมลนี้เข้าระบบใช่หรือไม่?",
                                "margin": "md"
                            }
                        ]
                    },
                    "footer": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "button",
                                "action": {
                                    "type": "postback",
                                    "label": "✅ ยืนยัน",
                                    "data": f"confirm_add_email_{user_id}"
                                },
                                "style": "primary"
                            },
                            {
                                "type": "button",
                                "action": {
                                    "type": "postback",
                                    "label": "🔄 แก้ไขอีเมล",
                                    "data": f"edit_email_{user_id}"
                                },
                                "style": "secondary",
                                "margin": "md"
                            },
                            {
                                "type": "button",
                                "action": {
                                    "type": "postback",
                                    "label": "❌ ยกเลิก",
                                    "data": f"cancel_add_email_{user_id}"
                                },
                                "style": "secondary",
                                "margin": "md"
                            }
                        ]
                    }
                }
            )
        )
        add_user_email(email)
    
    # Handle user input based on current step
    elif user_sessions[user_id]["step"] == "enter_meeting_name":
        # Save meeting name and proceed to date selection
        user_sessions[user_id]["meeting_data"]["name"] = text
        user_sessions[user_id]["step"] = "select_date"
        
        # Display confirmation and calendar
        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text=f"ชื่อการประชุม: {text}"),
                create_calendar_flex_message(user_id)
            ]
        )
    
    elif user_sessions[user_id]["step"] == "enter_time":
        try:
            # Parse time range
            start_time, end_time = parse_time_range(text)
            
            # Save time range
            user_sessions[user_id]["meeting_data"]["start_time"] = start_time
            user_sessions[user_id]["meeting_data"]["end_time"] = end_time
            user_sessions[user_id]["step"] = "select_attendees"
            
            # Display confirmation and attendee selection
            line_bot_api.reply_message(
                event.reply_token,
                [
                    TextSendMessage(text=f"ช่วงเวลาที่ต้องการ: {start_time} - {end_time}"),
                    create_user_selection_flex_message(user_id)
                ]
            )
        except ValueError as e:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"ขออภัย: {str(e)}\nกรุณากรอกข้อมูลในรูปแบบ '13:00 - 14:00'")
            )
    
    elif user_sessions[user_id]["step"] == "main_menu":
        # Handle main menu options
        if text == "ดูนัดประชุมที่มี":
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="คุณยังไม่มีนัดประชุมที่กำลังจะมาถึง")
            )
        elif text == "วิธีใช้งาน":
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="พิมพ์ 'นัดประชุม' เพื่อเริ่มสร้างนัดประชุมใหม่\nคุณสามารถเลือกวันที่ เวลา และผู้เข้าร่วมได้")
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                create_main_menu_message()
            )
    
    else:
        # Default response
        line_bot_api.reply_message(
            event.reply_token,
            create_main_menu_message()
        )

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    
    # Initialize user session if not exists
    if user_id not in user_sessions:
        user_sessions[user_id] = {"step": "main_menu"}
    
        # Handle email confirmation
    if data.startswith("confirm_add_email_"):
        email = user_sessions[user_id].get("email", "")
        if not email:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="ไม่พบอีเมลที่ต้องการเพิ่ม กรุณาลองใหม่อีกครั้ง")
            )
            return
        encoded_email = quote(email)
        # Create Google API URL (FastAPI endpoint)
        api_url = f"https://083e-49-228-96-87.ngrok-free.app/events/{encoded_email}"
        
        print(api_url)
        # Tell user they'll be redirected
        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(
                alt_text="เพิ่มอีเมลสำเร็จ",
                contents={
                    "type": "bubble",
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"อีเมล {email} ถูกเพิ่มแล้ว",
                                "weight": "bold",
                                "size": "lg",
                                "wrap": True
                            },
                            {
                                "type": "text",
                                "text": "กรุณากดปุ่มด้านล่างเพื่อยืนยันการเข้าถึง Google Calendar",
                                "margin": "md",
                                "wrap": True
                            }
                        ]
                    },
                    "footer": {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "action": {
                                    "type": "uri",
                                    "label": "🔗 ยืนยันผ่าน Google",
                                    "uri": api_url
                                }
                            }
                        ]
                    }
                }
            )
        )
        # Reset user session
        user_sessions[user_id] = {"step": "main_menu"}
        
    
    # Handle email edit request
    elif data.startswith("edit_email_"):
        user_sessions[user_id]["step"] = "enter_email"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="กรุณากรอกอีเมลใหม่อีกครั้ง:")
        )
    
    # Handle email cancellation
    elif data.startswith("cancel_add_email_"):
        # Reset user session
        user_sessions[user_id] = {"step": "main_menu"}
        
        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text="❌ ยกเลิกการเพิ่มอีเมลเรียบร้อยแล้ว"),
                create_main_menu_message()
            ]
        )
    
    # Handle date selection
    if data.startswith("start_date_"):
        # Save start date
        date = event.postback.params["date"]
        user_sessions[user_id]["meeting_data"]["start_date"] = date
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"วันที่เริ่มต้น: {date}")
        )
    
    elif data.startswith("end_date_"):
        # Save end date and proceed to time input
        date = event.postback.params["date"]
        user_sessions[user_id]["meeting_data"]["end_date"] = date
        user_sessions[user_id]["step"] = "enter_time"
        
        # Format dates for display
        start_date = user_sessions[user_id]["meeting_data"].get("start_date", date)
        
        # Display confirmation
        start_display = datetime.strptime(start_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        end_display = datetime.strptime(date, "%Y-%m-%d").strftime("%d/%m/%Y")
        
        if start_date == date:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"วันที่ประชุม: {start_display}\n\nกรุณาระบุช่วงเวลาที่ต้องการจัดประชุม\n(เช่น 13:00 - 14:00)")
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"ช่วงวันที่ประชุม: {start_display} ถึง {end_display}\n\nกรุณาระบุช่วงเวลาที่ต้องการจัดประชุม\n(เช่น 13:00 - 14:00)")
            )
    
    # Handle user selection
    elif data.startswith("select_user_"):
        parts = data.split("_")
        email = parts[-1]
        
        if "selected_users" not in user_sessions[user_id]["meeting_data"]:
            user_sessions[user_id]["meeting_data"]["selected_users"] = []
        
        if email not in user_sessions[user_id]["meeting_data"]["selected_users"]:
            user_sessions[user_id]["meeting_data"]["selected_users"].append(email)
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"เลือก {email} เรียบร้อยแล้ว")
        )
    
    elif data.startswith("confirm_users_"):
        # Proceed to availability check
        if "selected_users" not in user_sessions[user_id]["meeting_data"] or not user_sessions[user_id]["meeting_data"]["selected_users"]:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณาเลือกผู้เข้าร่วมอย่างน้อย 1 คน")
            )
            return
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="กำลังตรวจสอบเวลาว่างของผู้เข้าร่วมประชุม...")
        )
        
        # Get meeting data
        meeting_data = user_sessions[user_id]["meeting_data"]
        start_date = meeting_data["start_date"]
        end_date = meeting_data["end_date"]
        start_time = meeting_data["start_time"]
        end_time = meeting_data["end_time"]
        selected_users = meeting_data["selected_users"]
        
        # Generate date range
        date_range = generate_date_range(start_date, end_date)
        time_range = f"{start_time} - {end_time}"
        
        # Find available slots
        available_slots = find_available_slots(date_range, time_range, selected_users)
        
        if not available_slots:
            # No available slots
            line_bot_api.push_message(
                user_id,
                TextSendMessage(
                    text="❌ ไม่สามารถนัดประชุมได้ในวันและเวลานี้\nกรุณาเลือกวันและเวลาใหม่อีกครั้ง",
                    quick_reply=QuickReply(items=[
                        QuickReplyButton(action=MessageAction(label="เลือกวันเวลาใหม่", text="สร้างนัดประชุม"))
                    ])
                )
            )
        elif len(available_slots) == 1:
            # Only one slot available, proceed to confirmation
            slot = available_slots[0]
            meeting_data["date"] = slot["date"]
            meeting_data["start_time"] = slot["start_time"]
            meeting_data["end_time"] = slot["end_time"]
            meeting_data["attendees"] = selected_users
            
            user_sessions[user_id]["step"] = "confirm_meeting"
            
            # Format date for display
            date_display = datetime.strptime(slot["date"], "%Y-%m-%d").strftime("%d/%m/%Y")
            meeting_data["date_display"] = date_display
            
            line_bot_api.push_message(
                user_id,
                create_meeting_summary_flex_message(user_id, meeting_data)
            )
        else:
            # Multiple slots available, let user choose
            user_sessions[user_id]["available_slots"] = available_slots
            user_sessions[user_id]["step"] = "select_slot"
            
            line_bot_api.push_message(
                user_id,
                create_available_slots_flex_message(user_id, available_slots)
            )
    
    # Handle slot selection
    elif data.startswith("select_slot_"):
        parts = data.split("_")
        slot_index = int(parts[-1])
        
        available_slots = user_sessions[user_id]["available_slots"]
        if slot_index < 0 or slot_index >= len(available_slots):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="ขออภัย เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง")
            )
            return
        
        # Get selected slot
        slot = available_slots[slot_index]
        meeting_data = user_sessions[user_id]["meeting_data"]
        
        # Update meeting data
        meeting_data["date"] = slot["date"]
        meeting_data["start_time"] = slot["start_time"]
        meeting_data["end_time"] = slot["end_time"]
        meeting_data["attendees"] = meeting_data["selected_users"]
        
        user_sessions[user_id]["step"] = "confirm_meeting"
        
        # Format date for display
        date_display = datetime.strptime(slot["date"], "%Y-%m-%d").strftime("%d/%m/%Y")
        meeting_data["date_display"] = date_display
        
        line_bot_api.reply_message(
            event.reply_token,
            create_meeting_summary_flex_message(user_id, meeting_data)
        )
    
    # Handle meeting confirmation
    elif data.startswith("confirm_meeting_"):
        # Create meeting
        meeting_data = user_sessions[user_id]["meeting_data"]
        
        # Format date and time for API
        date = meeting_data["date"]  # Already in YYYY-MM-DD format
        start_time = meeting_data["start_time"]  # In HH:MM format
        end_time = meeting_data["end_time"]  # In HH:MM format
        
        # Create ISO format datetime
        start_datetime = f"{date}T{start_time}:00+07:00"
        end_datetime = f"{date}T{end_time}:00+07:00"
        
        # Create meeting result
        meeting_result = MeetingResult(
            user_emails=meeting_data["attendees"],
            summary=meeting_data["name"],
            description="",
            location="",
            start_time=start_datetime,
            end_time=end_datetime,
            attendees=[]
        )
        # ส่ง POST ไปยัง FastAPI server

        
        # Reset user session
        user_sessions[user_id] = {"step": "main_menu"}
        
        # Send confirmation
        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text="✅ การนัดหมายถูกสร้างเรียบร้อยแล้ว! ขอบคุณที่ใช้ระบบนัดประชุมอัตโนมัติของเรา 🙏"),

            ]
        )
        threading.Thread(target=send_post, args=(meeting_result,)).start() #send to fastapi
    
    # Handle meeting edit
    elif data.startswith("edit_meeting_"):
        # Reset to start of meeting creation
        user_sessions[user_id] = {
            "step": "enter_meeting_name",
            "meeting_data": {}
        }
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="เริ่มสร้างนัดประชุมใหม่\nกรุณากรอกชื่อการประชุม:")
        )
    
    # Handle meeting cancellation
    elif data.startswith("cancel_meeting_"):
        # Reset user session
        user_sessions[user_id] = {"step": "main_menu"}
        
        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text="❌ ยกเลิกการนัดหมายเรียบร้อยแล้ว"),
                create_main_menu_message()
            ]
        )