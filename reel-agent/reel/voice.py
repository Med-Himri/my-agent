"""Arabic voice-over with ElevenLabs (voice: Brian).

Set ELEVENLABS_API_KEYS to one or more keys separated by commas. When an
account runs out of credits (or its key stops working), the next key is used.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

BRIAN = "nPczCjzI2devNBz1zQrb"
MODEL = "eleven_multilingual_v2"
API = "https://api.elevenlabs.io/v1"


class OutOfCredits(RuntimeError):
    pass


def _keys() -> list[str]:
    raw = os.environ.get("ELEVENLABS_API_KEYS") or os.environ.get("ELEVENLABS_API_KEY", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise RuntimeError("Set ELEVENLABS_API_KEYS (comma-separated) in the environment")
    return keys


def _is_exhausted(r: requests.Response) -> bool:
    if r.status_code in (401, 402, 429):
        body = r.text.lower()
        return r.status_code != 429 or "quota" in body
    return False


def speak(text: str, out: Path, previous_text: str = "", next_text: str = "",
          voice_id: str = BRIAN, speed: float = 1.1) -> Path:
    """Generate one scene's voice clip. previous/next text keep the intonation continuous across scenes."""
    payload = {
        "text": text,
        "model_id": MODEL,
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.15,
                           "use_speaker_boost": True, "speed": speed},
    }
    if previous_text:
        payload["previous_text"] = previous_text
    if next_text:
        payload["next_text"] = next_text
    errors = []
    for i, key in enumerate(_keys(), 1):
        r = requests.post(f"{API}/text-to-speech/{voice_id}", params={"output_format": "mp3_44100_128"},
                          headers={"xi-api-key": key}, json=payload, timeout=120)
        if r.ok:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(r.content)
            return out
        if _is_exhausted(r):
            errors.append(f"key #{i}: {r.status_code} {r.text[:120]}")
            continue                      # try the next account
        r.raise_for_status()
    raise OutOfCredits("All ElevenLabs keys are out of credits or invalid:\n" + "\n".join(errors))


def voice_reel(scenes: list[dict], folder: Path) -> list[Path]:
    """Write voice/s1.mp3, s2.mp3, ... for every scene that doesn't have a clip yet."""
    paths = []
    for i, s in enumerate(scenes):
        out = folder / "voice" / f"s{i + 1}.mp3"
        if not out.exists():
            speak(s["voice"], out,
                  previous_text=scenes[i - 1]["voice"] if i else "",
                  next_text=scenes[i + 1]["voice"] if i + 1 < len(scenes) else "")
        paths.append(out)
    return paths
