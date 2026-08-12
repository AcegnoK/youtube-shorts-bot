import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Укажите BOT_TOKEN в файле .env")

UPLOADS_DIR = "uploads"

os.makedirs(UPLOADS_DIR, exist_ok=True)