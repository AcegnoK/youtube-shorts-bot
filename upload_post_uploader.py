from pathlib import Path

import requests

from config import UPLOAD_POST_API_KEY, UPLOAD_POST_PLATFORMS, UPLOAD_POST_USER

API_URL = "https://api.upload-post.com/api/upload"


def _credentials() -> tuple[str, str, list[str]]:
    if not UPLOAD_POST_API_KEY or not UPLOAD_POST_USER:
        raise RuntimeError(
            "Не заданы UPLOAD_POST_API_KEY и UPLOAD_POST_USER в .env.\n"
            "Ключ: https://app.upload-post.com/api-keys\n"
            "user — имя профиля в дашборде Upload-Post."
        )
    platforms = [p.strip() for p in UPLOAD_POST_PLATFORMS.split(",") if p.strip()]
    return UPLOAD_POST_API_KEY, UPLOAD_POST_USER, platforms


def upload_short(video_path: str, title: str, description: str) -> str:
    api_key, user, platforms = _credentials()

    with open(video_path, "rb") as f:
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Apikey {api_key}"},
            files={"video": (Path(video_path).name, f, "application/octet-stream")},
            data={
                "user": user,
                "platform[]": platforms,
                "title": title,
                "description": description,
            },
            timeout=900,
        )

    payload = resp.json()
    if not payload.get("success"):
        error = payload.get("error") or payload.get("message") or payload
        raise RuntimeError(f"Upload-Post: {resp.status_code} — {error}")

    parts = [part for part in (payload.get("job_id"), payload.get("message")) if part]
    return "Upload-Post: " + " — ".join(parts)