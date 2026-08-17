from pathlib import Path

import requests

from config import IG_ACCESS_TOKEN, IG_PUBLIC_URL_BASE, IG_USER_ID

GRAPH_URL = "https://graph.facebook.com/v21.0"


def _credentials() -> tuple[str, str, str]:
    if not IG_ACCESS_TOKEN or not IG_USER_ID:
        raise RuntimeError(
            "Не заданы IG_ACCESS_TOKEN и IG_USER_ID в .env. "
            "Их нужно получить через приложение Facebook с Instagram Graph API."
        )
    return IG_ACCESS_TOKEN, IG_USER_ID, IG_PUBLIC_URL_BASE


def upload_short(video_path: str, title: str, description: str) -> str:
    token, ig_user_id, public_base = _credentials()
    if not public_base:
        raise RuntimeError(
            "Для Reels задайте IG_PUBLIC_URL_BASE в .env — публичную ссылку, "
            "по которой серверы Facebook смогут скачать видео."
        )

    public_url = f"{public_base.rstrip('/')}/{Path(video_path).name}"

    media_resp = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": public_url,
            "caption": f"{title}\n\n{description}".strip(),
            "share_to_feed": "true",
            "access_token": token,
        },
        timeout=60,
    )
    media = media_resp.json()
    if "id" not in media:
        raise RuntimeError(f"Instagram media creation failed: {media}")
    creation_id = media["id"]

    publish_resp = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=60,
    )
    published = publish_resp.json()
    if "id" not in published:
        raise RuntimeError(f"Instagram publish failed: {published}")
    media_id = published["id"]

    permalink_resp = requests.get(
        f"{GRAPH_URL}/{media_id}",
        params={"fields": "permalink", "access_token": token},
        timeout=60,
    )
    permalink = permalink_resp.json().get("permalink")
    return permalink or f"https://www.instagram.com/reel/{media_id}/"