import os

# โฟลเดอร์เก็บไฟล์ token
TOKEN_DIR = 'tokens'
# กำหนด scope การเข้าถึง Google Calendar
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid'
]
#file เก็บข้อมูล client secret ของ OAuth
CLIENT_SECRET_FILE = os.getenv("CLIENT_SECRET_FILE")