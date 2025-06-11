from typing import List, Optional
from pydantic import BaseModel



# โมเดลสำหรับรับข้อมูลผู้ใช้
class UserCalendar(BaseModel):
    email: str #required
    calendar_id: Optional[str] = "primary" # Optional

class BulkEventRequest(BaseModel):
    name: str      # รับชื่อของ name2 สำหรับตั้งหัวข้อการประชุม
    email: str      # อีเมลของผู้ที่จะสร้างนัด
    location: str   # เช่น "Silom", "Asoke" เป็นต้น
    date: str       # รูปแบบ "YYYY-MM-DD" เช่น "2025-05-27"
    time: str       # รูปแบบ "HH:MM-HH:MM" เช่น "09:30-10:00"
    attendees: Optional[List[str]] = None  # รายชื่ออีเมลของผู้เข้าร่วมเพิ่มเติม    



class DateRequest(BaseModel):
    date: str
    location: str

class LocationRequest(BaseModel):
    location: str

class TimeslotRequest(BaseModel):
    date: str
    recruiter_email: str

class RecruiterRequest(BaseModel):
    date: str
    location: str
    
class DateConvert(BaseModel):
    date: str