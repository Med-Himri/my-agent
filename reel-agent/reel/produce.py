"""One reel from start to finish: script -> images -> voice -> video."""
from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import brain, config, images, video, voice


def _choose_images(spec: dict, folder: Path, old: dict | None = None) -> None:
    """Fill scene['image'] for scenes with an image_query; reuse the old pick when the query is unchanged."""
    reuse = {}
    if old:
        reuse = {s["image_query"]: s.get("image") for s in old["scenes"] if s.get("image_query") and s.get("image")}
    need = {}
    for i, s in enumerate(spec["scenes"]):
        q = s.get("image_query", "").strip()
        s["image"] = None
        if not q:
            continue
        if q in reuse and (folder / reuse[q]).exists():
            s["image"] = reuse[q]
        else:
            need[i] = q
    if not need:
        return
    with ThreadPoolExecutor(4) as ex:
        found = dict(zip(need, ex.map(lambda q: images.candidates_for(q, folder / "candidates" / str(abs(hash(q)))), need.values())))
    found = {i: paths for i, paths in found.items() if paths}
    picks = brain.pick_images(spec["scenes"], found)
    (folder / "img").mkdir(exist_ok=True)
    for i, path in picks.items():
        if path:
            dst = folder / "img" / f"{path.stem}{path.suffix}"
            shutil.copy(path, dst)
            spec["scenes"][i]["image"] = str(dst.relative_to(folder))


def _build(spec: dict, folder: Path) -> Path:
    voice.voice_reel(spec["scenes"], folder)
    (folder / "reel.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1))
    out = folder / "reel.mp4"
    video.make_reel(folder / "reel.json", out, config.MUSIC if config.MUSIC.exists() else None)
    shutil.rmtree(folder / "build", ignore_errors=True)
    return out


def produce(topic: dict, folder: Path) -> tuple[Path, dict]:
    folder.mkdir(parents=True, exist_ok=True)
    spec = brain.write_script(topic)
    spec["brand"] = config.BRAND
    _choose_images(spec, folder)
    return _build(spec, folder), spec


def revise(folder: Path, feedback: str) -> tuple[Path, dict]:
    old = json.loads((folder / "reel.json").read_text())
    spec = brain.revise_script(old, feedback)
    spec["brand"] = config.BRAND
    _choose_images(spec, folder, old)
    return _build(spec, folder), spec


def caption_text(spec: dict) -> str:
    tags = " ".join(t if t.startswith("#") else "#" + t for t in spec.get("hashtags", [])[:30])
    return f"{spec.get('caption', '').strip()}\n\n{tags}".strip()[:2200]
