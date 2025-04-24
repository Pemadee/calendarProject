# Standard library
import os
# Third-party libraries
from dotenv import load_dotenv
import uvicorn
# Local application
from lineChatbot import *
from test import *
from config import *
from utils.func import *
from api.endpoints import *


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
    # print(f"เข้าถึง API documentation ได้ที่: http://localhost:{port}/docs")
    # print(f"กำหนด redirect URI สำหรับ OAuth2: {REDIRECT_URI} (port: {AUTH_PORT})")
    # uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
    # venv\Scripts\activate
    # uvicorn main:app --host 0.0.0.0 --port 8000 --reload
