"""Publish a reel to Instagram through the official Graph API.

The video is uploaded directly to Instagram (resumable upload), so no public video hosting is needed.
Needs an Instagram Business or Creator account, its user id and a long-lived access token
(see SETUP.md). Long-lived tokens last 60 days; refresh_token() renews them.
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

from . import config


class InstagramError(RuntimeError):
    pass


def _base() -> str:
    return f"https://{config.IG_GRAPH_HOST}/{config.IG_API_VERSION}"


def _check(r: requests.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        data = {"raw": r.text[:300]}
    if not r.ok or "error" in data:
        err = data.get("error", data)
        raise InstagramError(f"Instagram API error {r.status_code}: {err}")
    return data


def publish_reel(video: Path, caption: str, token: str, user_id: str | None = None,
                 timeout_s: int = 900) -> dict:
    user_id = user_id or config.IG_USER_ID
    if not (user_id and token):
        raise InstagramError("IG_USER_ID / IG_ACCESS_TOKEN are not set")
    # 1. create a media container for a resumable upload
    c = _check(requests.post(f"{_base()}/{user_id}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption,
        "share_to_feed": "true", "access_token": token}, timeout=60))
    container, upload_uri = c["id"], c["uri"]
    # 2. upload the video bytes
    data = video.read_bytes()
    _check(requests.post(upload_uri, data=data, timeout=600, headers={
        "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(data))}))
    # 3. wait for Instagram to process it
    deadline = time.time() + timeout_s
    while True:
        st = _check(requests.get(f"{_base()}/{container}", params={
            "fields": "status_code,status", "access_token": token}, timeout=30))
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise InstagramError(f"Instagram could not process the video: {st.get('status')}")
        if time.time() > deadline:
            raise InstagramError("Timed out waiting for Instagram to process the video")
        time.sleep(10)
    # 4. publish
    pub = _check(requests.post(f"{_base()}/{user_id}/media_publish", data={
        "creation_id": container, "access_token": token}, timeout=60))
    media_id = pub["id"]
    info = _check(requests.get(f"{_base()}/{media_id}", params={
        "fields": "permalink", "access_token": token}, timeout=30))
    return {"id": media_id, "permalink": info.get("permalink")}


def refresh_token(token: str) -> str:
    """Exchange a long-lived Instagram-login token for a fresh one (valid 60 more days)."""
    if config.IG_GRAPH_HOST != "graph.instagram.com":
        return token          # Facebook-login page tokens do not expire this way
    r = _check(requests.get("https://graph.instagram.com/refresh_access_token", params={
        "grant_type": "ig_refresh_token", "access_token": token}, timeout=30))
    return r["access_token"]
