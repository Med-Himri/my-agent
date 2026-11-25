"""Image search + download.

Sources (tried in order):
  1. Google Images via Serper.dev  (needs SERPER_API_KEY)
  2. Wikimedia Commons             (free, no key)
Claude then reviews candidates and picks the best ones (see reel/pick.py).
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import requests

UA = {"User-Agent": "MedloutReelBot/0.1 (automated reel builder)"}


@dataclass
class Candidate:
    url: str
    title: str
    width: int
    height: int
    source: str


def search_google(query: str, n: int = 10) -> list[Candidate]:
    key = os.environ.get("SERPER_API_KEY")
    if not key:
        return []
    r = requests.post(
        "https://google.serper.dev/images",
        headers={"X-API-KEY": key, "Content-Type": "application/json"},
        json={"q": query, "num": n},
        timeout=20,
    )
    r.raise_for_status()
    return [
        Candidate(i["imageUrl"], i.get("title", ""), i.get("imageWidth", 0), i.get("imageHeight", 0), "google")
        for i in r.json().get("images", [])
    ]


def search_wikimedia(query: str, n: int = 10) -> list[Candidate]:
    r = requests.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query", "format": "json", "generator": "search",
            "gsrnamespace": 6, "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": n,
            "prop": "imageinfo", "iiprop": "url|size|mime", "iiurlwidth": 1280,
        },
        headers=UA, timeout=20,
    )
    r.raise_for_status()
    out = []
    for p in r.json().get("query", {}).get("pages", {}).values():
        ii = p["imageinfo"][0]
        if ii.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
            continue
        out.append(Candidate(ii.get("thumburl") or ii["url"], p["title"], ii["width"], ii["height"], "wikimedia"))
    return out


def search(query: str, n: int = 10, min_width: int = 600) -> list[Candidate]:
    cands = search_google(query, n) or search_wikimedia(query, n)
    return [c for c in cands if not c.width or c.width >= min_width]


BLOCKED_HOSTS = ("lookaside.", "alamy.", "gettyimages.", "istockphoto.", "shutterstock.", "ftcdn.", "123rf.",
                 "dreamstime.", "depositphotos.", "pinimg.", "tiktok.", "ytimg.", "amazon.", "ebayimg.", "walmartimages.")


def usable(c: Candidate) -> bool:
    return not any(h in c.url for h in BLOCKED_HOSTS)


def download(c: Candidate, folder: Path) -> Path | None:
    folder.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(c.url, headers=UA, timeout=30)
        r.raise_for_status()
        if not r.headers.get("content-type", "").startswith("image/"):
            return None
    except requests.RequestException:
        return None
    ext = {"image/png": ".png", "image/webp": ".webp"}.get(r.headers["content-type"].split(";")[0], ".jpg")
    path = folder / (hashlib.sha1(c.url.encode()).hexdigest()[:12] + ext)
    path.write_bytes(r.content)
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.load()
            if im.width < 500 or im.height < 300:
                raise ValueError("too small")
            if ext == ".webp" or im.mode not in ("RGB", "L"):   # normalise for the renderer
                im.convert("RGB").save(path.with_suffix(".jpg"), quality=92)
                if path.suffix != ".jpg":
                    path.unlink(); path = path.with_suffix(".jpg")
    except Exception:
        path.unlink(missing_ok=True)
        return None
    return path


def candidates_for(query: str, folder: Path, want: int = 5) -> list[Path]:
    """Search, skip stock/watermark/social hosts, download the first `want` usable images."""
    out = []
    for c in search(query, 20):
        if len(out) >= want:
            break
        if usable(c) and (p := download(c, folder)):
            out.append(p)
    return out


if __name__ == "__main__":
    import sys
    for c in search(" ".join(sys.argv[1:])):
        print(c.width, c.height, c.title, c.url)
