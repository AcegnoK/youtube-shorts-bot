import pickle
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.pickle"
REDIRECT_URI = "http://localhost:8080/"


def load_credentials():
    if not Path(TOKEN_FILE).exists():
        return None
    with open(TOKEN_FILE, "rb") as f:
        return pickle.load(f)


def credentials_valid() -> bool:
    credentials = load_credentials()
    if credentials is None:
        return False
    if credentials.valid:
        return True
    return bool(credentials.expired and credentials.refresh_token)


def build_auth_flow() -> InstalledAppFlow:
    return InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRET_FILE, SCOPES, redirect_uri=REDIRECT_URI
    )


def get_auth_url(flow: InstalledAppFlow) -> str:
    return flow.authorization_url(prompt="consent")[0]


def save_token_from_code(flow: InstalledAppFlow, code: str) -> None:
    flow.fetch_token(code=code)
    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(flow.credentials, f)


def extract_code(text: str) -> str:
    if "code=" in text:
        return text.split("code=", 1)[1].split("&", 1)[0]
    return text.strip()


def get_authenticated_service():
    credentials = load_credentials()
    if credentials is None:
        raise RuntimeError(
            "Нет авторизации. Напишите /start и пройдите авторизацию по ссылке."
        )
    if not credentials.valid:
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            with open(TOKEN_FILE, "wb") as f:
                pickle.dump(credentials, f)
        else:
            raise RuntimeError("Авторизация недействительна. Напишите /start заново.")
    return build("youtube", "v3", credentials=credentials)


def upload_short(video_path: str, title: str, description: str) -> str:
    if "#Shorts" not in title:
        title = f"{title} #Shorts"

    youtube = get_authenticated_service()

    body = {
        "snippet": {
            "title": title,
            "description": description,
        },
        "status": {
            "privacyStatus": "public",
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Загрузка: {int(status.progress() * 100)}%")

    video_id = response["id"]
    return f"https://youtu.be/{video_id}"


if __name__ == "__main__":
    if not credentials_valid():
        flow = build_auth_flow()
        print("Открой ссылку (можно на телефоне):")
        print(get_auth_url(flow))
        code = input("Вставь код из адресной строки: ").strip()
        save_token_from_code(flow, extract_code(code))
        print("Авторизация сохранена.")
    video_path = input("Путь к видео: ").strip()
    title = input("Заголовок: ").strip()
    description = input("Описание: ").strip()
    url = upload_short(video_path, title, description)
    print(f"Опубликовано: {url}")
    time.sleep(2)