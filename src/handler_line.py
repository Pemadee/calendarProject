import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Union, Any
from datetime import datetime
import threading
import requests
import aiohttp
import asyncio

app = FastAPI()
load_dotenv()
base_url = os.getenv("BASE_URL_NGROK")


def send_book_meeting(meeting_result):
    try:
        print("🚀 POST ข้อมูล:", meeting_result.dict())
        print(base_url)
        response = requests.post(
            f"{base_url}/events/create-bulk",
            json=meeting_result.dict(),
            headers={"Content-Type": "application/json"},
            timeout=3
        )
        print("✅ POST สำเร็จ:", response.status_code)
    except Exception as e:
        print("❌ POST ล้มเหลว:", str(e))

