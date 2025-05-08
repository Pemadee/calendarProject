# Standard library
import os
# Third-party libraries
from dotenv import load_dotenv
import uvicorn
# Local application
# from line_bot import *
from lineBot import *
from test import *
from config import *
from utils.func import *
from api.endpoints import *
from utils.scheduler_instance import scheduler
import utils.auto_refresh_jobs 
from models.token_model import init_db
init_db()  # ✅ เพิ่มตรงนี้
# ลบและสร้างโฟลเดอร์ tokens ใหม่เพื่อหลีกเลี่ยงปัญหา
try:
    if os.path.exists(TOKEN_DIR):
        # shutil.rmtree(TOKEN_DIR)
        # print(f"ลบโฟลเดอร์ {TOKEN_DIR} เดิมแล้ว")
        pass 
    else :
        os.makedirs(TOKEN_DIR)
        print(f"สร้างโฟลเดอร์ {TOKEN_DIR} ใหม่แล้ว")
except Exception as e:
    print(f"เกิดข้อผิดพลาดในการจัดการโฟลเดอร์ {TOKEN_DIR}: {str(e)}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"เริ่มต้น FastAPI บน port {port}...")
    # venv\Scripts\activate
    # uvicorn main:app --host 0.0.0.0 --port 8000 --reload
