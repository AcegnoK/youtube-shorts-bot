import logging
import time
from datetime import datetime
from pathlib import Path

import requests

from config import (
    PMP_ACCESS_TOKEN,
    PMP_ACCOUNT_IDS,
    PMP_PROJECT_ID,
    PMP_TZ_OFFSET,
)

API_URL = "https://api.postmypost.io/v4.1"
PMP_DASHBOARD_URL = "https://app.postmypost.io/"

STATUS_UPLOADED = 1
STATUS_ERROR = 2


def _headers() -> dict:
    if not PMP_ACCESS_TOKEN:
        raise RuntimeError(
            "Не задан PMP_ACCESS_TOKEN в .env.\n"
            "Токен можно получить в настройках PostMyPost."
        )
    if not PMP_PROJECT_ID:
        raise RuntimeError("Не задан PMP_PROJECT_ID в .env.")
    if not PMP_ACCOUNT_IDS:
        raise RuntimeError("Не задан PMP_ACCOUNT_IDS в .env (через запятую).")
    return {
        "Authorization": f"Bearer {PMP_ACCESS_TOKEN}",
        "Accept": "application/json",
    }


def _unwrap(payload):
    if isinstance(payload, dict) and isinstance(payload.get("data"), (dict, list)):
        return payload["data"]
    return payload


def _init_upload(video_path: str) -> dict:
    path = Path(video_path)
    resp = requests.post(
        f"{API_URL}/upload/init",
        headers=_headers(),
        json={
            "project_id": PMP_PROJECT_ID,
            "name": path.name,
            "size": path.stat().st_size,
        },
        timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"PostMyPost init: {resp.status_code} — {resp.text[:300]}")
    return _unwrap(resp.json())


def _upload_file(init_data: dict, video_path: str) -> None:
    fields = {
        item["key"]: item.get("value", "")
        for item in init_data.get("fields", [])
    }
    action = init_data.get("action")
    if not action:
        raise RuntimeError("PostMyPost: не получен URL для загрузки файла.")

    with open(video_path, "rb") as fh:
        files = {"file": (Path(video_path).name, fh, "video/mp4")}
        resp = requests.post(action, data=fields, files=files, timeout=1800)

    if resp.status_code >= 400:
        raise RuntimeError(f"PostMyPost S3 upload: {resp.status_code} — {resp.text[:300]}")


def _wait_processed(upload_id, timeout_sec: int = 1200) -> int:
    """Ждёт обработки файла и возвращает итоговый file_id для публикации."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        resp = requests.get(
            f"{API_URL}/upload/status",
            headers=_headers(),
            params={"id": upload_id},
            timeout=30,
        )
        if resp.ok:
            data = _unwrap(resp.json())
            if isinstance(data, dict):
                status = data.get("status")
                file_id = data.get("file_id")
                if status == STATUS_UPLOADED and file_id:
                    return int(file_id)
                if status == STATUS_ERROR:
                    raise RuntimeError(
                        "PostMyPost: ошибка обработки загруженного файла."
                    )
        time.sleep(5)
    raise TimeoutError("PostMyPost: файл слишком долго обрабатывается.")


def _create_publication(file_id: int, title: str, description: str) -> str:
    post_at = (
        datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + PMP_TZ_OFFSET
    )
    payload = {
        "project_id": PMP_PROJECT_ID,
        "post_at": post_at,
        "account_ids": PMP_ACCOUNT_IDS,
        "publication_status": 5,
        "details": [
            {
                "publication_type": 4,
                "file_ids": [file_id],
                "title": title,
                "content": description or title,
            }
        ],
    }
    resp = requests.post(
        f"{API_URL}/publications",
        headers={**_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(
            f"PostMyPost create publication: {resp.status_code} — {resp.text[:300]}"
        )
    return resp.text[:200]


def upload_short(video_path: str, title: str, description: str) -> str:
    init_data = _init_upload(video_path)
    upload_id = init_data.get("id")

    _upload_file(init_data, video_path)

    complete = requests.post(
        f"{API_URL}/upload/complete",
        headers=_headers(),
        params={"id": upload_id},
        timeout=60,
    )
    if not complete.ok:
        raise RuntimeError(
            f"PostMyPost complete: {complete.status_code} — {complete.text[:300]}"
        )

    file_id = _wait_processed(upload_id)
    logging.info("PostMyPost: файл обработан, file_id=%s", file_id)
    result = _create_publication(file_id, title, description)
    logging.info("PostMyPost: %s", result)
    return PMP_DASHBOARD_URL
