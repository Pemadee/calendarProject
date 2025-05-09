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

# โมเดลสำหรับการนัดหมายพร้อมกันหลายคน
class BulkEventRequest(BaseModel):
    user_emails: List[str]  # รายชื่ออีเมลของผู้ที่จะสร้างปฏิทิน
    summary: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_time: str  # รูปแบบ ISO format เช่น "2025-04-20T09:00:00+07:00"
    end_time: str    # รูปแบบ ISO format เช่น "2025-04-20T10:00:00+07:00"
    attendees: Optional[List[str]] = None  # รายชื่ออีเมลของผู้เข้าร่วมเพิ่มเติม (จะถูกเพิ่มในทุกปฏิทิน)

# โมเดลสำหรับรับข้อมูลผู้ใช้หลายคน จากข้อมูลใน excel
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
    english_min: float
    exp_kind: str
    age_key: str

class TimeSlotRequest(BaseModel):
    date: str
    time_slot: str  # Format: "HH:MM-HH:MM"
    location: str
    english_min: float
    exp_kind: str
    age_key: str