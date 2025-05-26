from typing import List, Optional
from pydantic import BaseModel



# โมเดลสำหรับรับข้อมูลผู้ใช้
class UserCalendar(BaseModel):
    email: str #required
    calendar_id: Optional[str] = "primary" # Optional

# โมเดลสำหรับรับข้อมูลผู้ใช้หลายคน
class UsersRequest(BaseModel):
    users: List[UserCalendar] #List ของ UserCalendar
    start_date: Optional[str] = None  # เช่น "2025-05-29"
    end_date: Optional[str] = None    # เช่น "2025-05-30"
    start_time: Optional[str] = None  # เช่น "18:30:00"
    end_time: Optional[str] = None    # เช่น "19:00:00"

class BulkEventRequest(BaseModel):
    name: str  # รับในรูปแบบ "name1-name2"
    location: str   # เช่น "Silom", "Asoke" เป็นต้น
    event_location: Optional[str] = None
    date: str       # รูปแบบ "YYYY-MM-DD" เช่น "2025-05-27"
    time: str       # รูปแบบ "HH:MM-HH:MM" เช่น "09:30-10:00"
    attendees: Optional[List[str]] = None  # รายชื่ออีเมลของผู้เข้าร่วมเพิ่มเติม


class ManagerRecruiter(BaseModel):
    file_path: Optional[str] = None
    location: str
    english_min: float
    exp_kind: str
    age_key: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    time_period: Optional[str] = None
    include_holidays: Optional[bool] = True # ถ้าไม่ใช้ก็ false


# โมเดลสำหรับรับข้อมูล Manger Recruiter
class getManagerRecruiter(BaseModel):
    location: str 
    english_min: int
    exp_kind: str
    age_key: str
    
# โมเดลสำหรับรับข้อมูล Manger Recruiter แบบกลุ่ม
class combMangerRecruiter(BaseModel):
    users: List[getManagerRecruiter] #List ของ UserCalendar
   
# Model สำหรับ API ทั้ง 3 ตัว
class ManagerRecruiter2(BaseModel):
    location: str
    english_min: float
    exp_kind: str
    age_key: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    time_period: Optional[str] = None
    include_holidays: Optional[bool] = True

class DateRequest(BaseModel):
    date: str
    location: str


class TimeSlotRequest(BaseModel):
    date: str
    time_slot: str  # Format: "HH:MM-HH:MM"
    location: str
    english_min: float
    exp_kind: str
    age_key: str

class LocationRequest(BaseModel):
    location: str



