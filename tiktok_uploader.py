import time
from pathlib import Path

import requests

from config import TIKTOK_ACCESS_TOKEN

API_BASE = "https://open.tiktok.com"
CHUNK_SIZE = 4 * 1024 * 1024


def _access_token() -> str:
    if not TIKTOK_ACCESS_TOKEN:
        raise RuntimeError(
            "Не задан TIKTOK_ACCESS_TOKEN в .env. "
            "Получите его после регистрации приложения на https://developers.tiktok.com/"
        )
    return TIKTOK_ACCESS_TOKEN


def upload_short(video_path: str, title: str, description: str) -> str:
    token = _access_token()
    video_size = Path(video_path).stat().st_size
    total_chunks = max(1, (video_size + CHUNK_SIZE - 1) // CHUNK_SIZE)

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    init_payload = {
        "post_info": {
            "title": title,
            "description": description,
            "privacy_level": "PUBLIC_TO_EVERYONE",
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": CHUNK_SIZE,
            "total_chunk_count": total_chunks,
        },
    }

    init_resp = requests.post(
        f"{API_BASE}/v2/post/publish/video/init/",
        headers=headers,
        json=init_payload,
        timeout=60,
    )
    init_data = init_resp.json()
    if init_data.get("error", {}).get("code"):
        raise RuntimeError(f"TikTok init failed: {init_data['error']}")
    data = init_data["data"]
    publish_id = data["publish_id"]
    upload_url = data["upload_url"]

    upload_headers = {"Access-Token": token}
    for key, value in (data.get("uploader") or {}).get("headers", {}).items():
        upload_headers[key.lower()] = value

    with open(video_path, "rb") as f:
        start = 0
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            end = start + len(chunk) - 1
            upload_headers["Content-Range"] = f"bytes {start}-{end}/{video_size}"
            resp = requests.put(upload_url, headers=upload_headers, data=chunk, timeout=300)
            if resp.status_code not in (200, 201, 204):
                raise RuntimeError(
                    f"TikTok chunk upload failed: {resp.status_code} {resp.text[:300]}"
                )
            start = end + 1

    poll_payload = {"publish_id": publish_id}
    for _ in range(20):
        time.sleep(3)
        poll_resp = requests.post(
            f"{API_BASE}/v2/post/publish/video/fetch/",
            headers=headers,
            json=poll_payload,
            timeout=60,
        )
        poll_data = poll_resp.json()
        if poll_data.get("error", {}).get("code"):
            raise RuntimeError(f"TikTok fetch failed: {poll_data['error']}")
        status = poll_data.get("data", {}).get("status")
        if status == "PUBLISH_COMPLETE":
            post = poll_data["data"].get("post", {})
            return post.get("share_url") or post.get("video_url") or f"publish_id={publish_id}"
        if status == "FAILED":
            raise RuntimeError("TikTok video status FAILED")

    raise RuntimeError(f"TikTok publish timeout (publish_id={publish_id})")