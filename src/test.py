import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Union, Any
from datetime import datetime
import threading
import requests
app = FastAPI()
load_dotenv()
base_url = os.getenv("BASE_URL")

class Creator(BaseModel):
    email: str
    self: bool


class Event(BaseModel):
    id: str
    summary: str
    start: str
    end: str
    creator: Creator
    attendees: List[Any]
    status: str
    location: str = ""
    description: str = ""


class CalendarResult(BaseModel):
    email: str
    calendar_id: str
    events: List[Event]
    is_authenticated: bool


class CalendarInput(BaseModel):
    results: List[CalendarResult]


@app.post("/calendar/parse")
async def parse_calendar(data: CalendarInput):
    calendar_data = {}

    for result in data.results:
        email = result.email
        if email not in calendar_data:
            calendar_data[email] = {}

        for event in result.events:
            start = event.start
            end = event.end

            if 'T' not in start:
                date = start
                time_start = "00:00"
                time_end = "23:59"
            else:
                start_dt = datetime.fromisoformat(start)
                end_dt = datetime.fromisoformat(end)
                date = start_dt.date().isoformat()
                time_start = start_dt.strftime("%H:%M")
                time_end = end_dt.strftime("%H:%M")

            if date not in calendar_data[email]:
                calendar_data[email][date] = []

            calendar_data[email][date].append((time_start, time_end))

    return calendar_data

def send_post(meeting_result):
    try:
        base_url = os.environ.get('BASE_URL')
        response = requests.post(
            f"{base_url}/events/create-bulk",
            json=meeting_result.dict(),
            headers={"Content-Type": "application/json"},
            timeout=3
        )
        print("✅ POST สำเร็จ:", response.status_code)
    except Exception as e:
        print("❌ POST ล้มเหลว:", str(e))



def get_available_users():
    try:
        response = requests.get("https://083e-49-228-96-87.ngrok-free.app/users/list", timeout=5)
        response.raise_for_status()  # ตรวจสอบว่า HTTP status 200
        data = response.json()
        return data.get("users", [])
    except Exception as e:
        print(f"❌ ดึง users ไม่สำเร็จ: {e}")
        return []

