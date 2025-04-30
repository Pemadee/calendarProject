from datetime import datetime, timedelta, date
import holidays

# Mock request
class MockRequest:
    start_date = "2025-04-30"
    end_date = "2025-05-08"
    include_holidays = False

request = MockRequest()

# Step 1: แปลง start_date และ end_date
start_datetime = datetime.fromisoformat(request.start_date).replace(hour=0, minute=0, second=0, microsecond=0)
end_datetime = datetime.fromisoformat(request.end_date).replace(hour=23, minute=59, second=59)

# Step 2: โหลดวันหยุดไทยของทุกปีที่เกี่ยวข้อง
years_to_check = list(range(start_datetime.year, end_datetime.year + 1))
thai_holidays = holidays.Thailand(years=years_to_check)

# แสดงวันหยุดที่โหลดได้
print("\n== วันหยุดนักขัตฤกษ์ที่โหลดมา ==")
for h_date, h_name in sorted(thai_holidays.items()):
    print(f"{h_date} : {h_name}")

# Step 3: วนลูปแต่ละวันในช่วงนั้น
include_holidays = getattr(request, "include_holidays", True)

date_list = []
current_date = start_datetime.date()

print("\n== ตรวจสอบวันทำงานที่คัดกรองแล้ว ==")
while current_date <= end_datetime.date():
    is_weekend = current_date.weekday() >= 5  # เสาร์=5, อาทิตย์=6
    is_holiday = current_date in thai_holidays

    print(f"{current_date} | Weekend: {is_weekend} | Holiday: {is_holiday} | Included: {not is_weekend and (include_holidays or not is_holiday)}")

    if not is_weekend and (include_holidays or not is_holiday):
        date_list.append(current_date)

    current_date += timedelta(days=1)

# แสดงผลลัพธ์วันทำงานที่เหลืออยู่
print("\n== วันทำงานที่เหลืออยู่ (after filtering) ==")
for d in date_list:
    print(d)
