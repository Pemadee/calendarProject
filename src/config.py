import os
import json
from dotenv import load_dotenv

load_dotenv()

TOKEN_DIR = 'tokens'

CLIENT_SECRET_FILE = os.getenv("CLIENT_SECRET_FILE")

def load_client_secrets(file_path):
    with open(file_path, "r") as f:
        data = json.load(f)
    return data["web"]["client_id"], data["web"]["client_secret"]


CLIENT_ID, CLIENT_SECRET = load_client_secrets(CLIENT_SECRET_FILE)

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid"
]
