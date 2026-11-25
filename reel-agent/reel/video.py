"""Turn a reel spec (reel.json + images + per-scene voice clips) into a finished MP4.

reel.json  -> timeline.json (scene/pill/subtitle timings) -> renderer/render.mjs (frames)
           -> ffmpeg (voice clips + background music) -> final reel
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
GAP = 0.35          # pause between scenes (s)
TAIL = 0.9          # hold on last frame (s)
WORDS_PER_SEC = 2.4  # only used when a scene has no voice clip yet
SUB_SPLIT = re.compile(r"(?<=[،,.؟?!:])\s+")


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def strip_marks(s: str) -> str:
    """Remove Arabic diacritics so cue matching is robust."""
    return re.sub(r"[ً-ْـ]", "", s)


def is_light_background(img: Image.Image) -> bool:
    im = img.convert("L"); w, h = im.size
    corners = [im.getpixel((x, y)) for x in (2, w - 3) for y in (2, h - 3)]
    return min(corners) > 235


def prepare_image(src: Path, work: Path) -> tuple[str, str, str]:
    """Return (image_uri, bg_uri, fit). Background is a blurred, darkened copy."""
    img = Image.open(src).convert("RGB")
    fit = "contain" if is_light_background(img) else "cover"
    bg = img.copy(); bg.thumbnail((540, 960))
    bg = bg.resize((270, 480)).filter(ImageFilter.GaussianBlur(8)).resize((1080, 1920))
    bg = ImageEnhance.Brightness(bg).enhance(0.42)
    bg_path = work / f"bg_{src.stem}.jpg"; bg.save(bg_path, quality=88)
    return src.resolve().as_uri(), bg_path.resolve().as_uri(), fit


def subtitle_chunks(text: str, max_words: int = 7) -> list[str]:
    chunks = []
    for part in SUB_SPLIT.split(text.strip()):
        words = part.split()
        while len(words) > max_words:
            chunks.append(" ".join(words[:max_words // 2 + 1])); words = words[max_words // 2 + 1:]
        if words:
            chunks.append(" ".join(words))
    return chunks


def two_lines(chunk: str, max_chars: int = 26) -> list[str]:
    if len(chunk) <= max_chars:
        return [chunk]
    words = chunk.split(); best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        score = abs(len(a) - len(b))
        if best is None or score < best[0]:
            best = (score, [a, b])
    return best[1]


def build_timeline(spec_path: Path) -> dict:
    spec = json.loads(spec_path.read_text())
    base = spec_path.parent
    work = base / "build"; work.mkdir(exist_ok=True)
    t = 0.0; scenes = []; subs = []; audio = []; missing = []
    for i, s in enumerate(spec["scenes"], 1):
        clip = base / "voice" / f"s{i}.mp3"
        if clip.exists():
            dur = duration(clip); audio.append((clip, t))
        else:
            dur = len(s["voice"].split()) / WORDS_PER_SEC + 0.3; missing.append(i)
        sc = {"title": s["title"], "mood": s.get("mood", "dark"), "start": t, "dur": dur, "end": t + dur + GAP,
              "badge": s.get("badge"), "image": None, "bg_image": None, "fit": "cover"}
        if s.get("image"):
            sc["image"], sc["bg_image"], sc["fit"] = prepare_image(base / s["image"], work)
            if sc["fit"] == "contain":      # white diagrams: use the mood gradient, not a gray blur
                sc["bg_image"] = None
        # pills appear when their cue word is spoken (approximated by character position)
        plain = strip_marks(s["voice"]); last = t + 0.2; pills = []
        for p in s.get("pills", []):
            idx = plain.find(strip_marks(p.get("cue", p["text"])))
            at = t + 0.15 + (idx / max(len(plain), 1)) * dur if idx >= 0 else last + 0.6
            at = max(at, last + 0.45); last = at
            pills.append({"text": p["text"], "color": p.get("color", "yellow"), "at": round(at, 3)})
        sc["pills"] = pills
        # subtitles spread over the clip by character length
        chunks = subtitle_chunks(s["voice"]); total_chars = sum(len(c) for c in chunks); ct = t
        for c in chunks:
            d = dur * len(c) / total_chars
            subs.append({"start": round(ct, 3), "end": round(ct + d + (GAP if c is chunks[-1] else 0), 3),
                         "text": c, "lines": two_lines(c)})
            ct += d
        scenes.append(sc); t += dur + GAP
    total = t - GAP + TAIL
    scenes[-1]["end"] = total
    return {"brand": spec.get("brand", "MEDLOUT AUTO"), "fps": 30, "total": round(total, 3),
            "scenes": scenes, "subs": subs, "_audio": [(str(a), s) for a, s in audio], "_missing_voice": missing}


def mix_audio(timeline: dict, out: Path, music: Path | None, music_volume: float = 0.12) -> None:
    total = timeline["total"]; inputs = []; filters = []; labels = []
    for k, (clip, start) in enumerate(timeline["_audio"]):
        inputs += ["-i", clip]; ms = int(start * 1000)
        filters.append(f"[{k}:a]aresample=48000,adelay={ms}|{ms}[v{k}]"); labels.append(f"[v{k}]")
    if music:
        k = len(timeline["_audio"])
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        filters.append(f"[{k}:a]aresample=48000,volume={music_volume},atrim=0:{total},afade=t=out:st={total - 1.5}:d=1.5[m]")
        labels.append("[m]")
    if not labels:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(total), str(out)], check=True)
        return
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest,apad,atrim=0:{total}[a]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[a]",
                    "-ac", "2", "-c:a", "aac", "-b:a", "192k", str(out)], check=True)


def make_reel(spec_path: Path, out: Path, music: Path | None = None) -> dict:
    tl = build_timeline(spec_path)
    work = spec_path.parent / "build"
    (work / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False, indent=1))
    subprocess.run(["node", str(ROOT / "renderer" / "render.mjs"), str(work / "timeline.json"), str(work / "video.mp4")], check=True)
    mix_audio(tl, work / "audio.m4a", music)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(work / "video.mp4"), "-i", str(work / "audio.m4a"),
                    "-c:v", "copy", "-c:a", "copy", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    return tl


if __name__ == "__main__":
    import sys
    spec = Path(sys.argv[1]); out = Path(sys.argv[2])
    music = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    tl = make_reel(spec, out, music)
    print(f"✓ {out}  ({tl['total']:.1f}s)  scenes without voice: {tl['_missing_voice'] or 'none'}")
