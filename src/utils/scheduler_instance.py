from apscheduler.schedulers.background import BackgroundScheduler

# สร้าง scheduler instance ด้วยค่าที่เหมาะสม
scheduler = BackgroundScheduler(
    job_defaults={
        'coalesce': False,  # ไม่รวม jobs ที่พลาดไป
        'max_instances': 1,  # จำกัดให้แต่ละ job ทำงานได้เพียง 1 instance
        'misfire_grace_time': 60  # ยอมให้ jobs ที่พลาดช่วงเวลาทำงานได้ภายใน 60 วินาที
    }
)

