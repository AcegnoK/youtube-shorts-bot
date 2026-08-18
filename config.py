import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Укажите BOT_TOKEN в файле .env")

UPLOADS_DIR = "uploads"

TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN")
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")

IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")
IG_PUBLIC_URL_BASE = os.getenv("IG_PUBLIC_URL_BASE")

UPLOAD_POST_API_KEY = os.getenv("UPLOAD_POST_API_KEY")
UPLOAD_POST_USER = os.getenv("UPLOAD_POST_USER")
UPLOAD_POST_PLATFORMS = os.getenv("UPLOAD_POST_PLATFORMS", "youtube,tiktok,instagram")

os.makedirs(UPLOADS_DIR, exist_ok=True)