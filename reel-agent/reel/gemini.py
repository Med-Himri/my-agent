"""Minimal Google Gemini client (REST) with retries for the free tier's busy/limit errors."""
from __future__ import annotations

import json
import os
import time

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(RuntimeError):
    pass


def models() -> list[str]:
    first = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    chain = [first, "gemini-flash-latest", "gemini-3.5-flash-lite"]
    return list(dict.fromkeys(chain))          # unique, keep order


def generate_json(system: str, parts: list[dict], schema: dict, temperature: float = 0.8,
                  max_attempts: int = 6) -> dict:
    """Ask Gemini for JSON matching `schema`. Tries fallback models and waits on 429/503."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise GeminiError("GEMINI_API_KEY is not set")
    body = {
        "systemInstruction": {"parts": [{"text": system}]} if system else None,
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema,
                             "temperature": temperature},
    }
    body = {k: v for k, v in body.items() if v is not None}
    errors = []
    for attempt in range(max_attempts):
        model = models()[min(attempt // 2, len(models()) - 1)]       # 2 tries per model
        try:
            r = requests.post(f"{API}/{model}:generateContent", headers={"x-goog-api-key": key},
                              json=body, timeout=120)
        except requests.RequestException as e:
            errors.append(f"{model}: {e}"); time.sleep(5); continue
        if r.status_code in (429, 500, 503, 504):
            msg = r.json().get("error", {}).get("message", r.text)[:150] if r.content else r.status_code
            errors.append(f"{model}: {r.status_code} {msg}")
            time.sleep(min(60, 10 * (attempt + 1)))
            continue
        if not r.ok:
            raise GeminiError(f"{model}: {r.status_code} {r.text[:400]}")
        d = r.json()
        cand = (d.get("candidates") or [{}])[0]
        if cand.get("finishReason") not in (None, "STOP"):
            errors.append(f"{model}: finishReason={cand.get('finishReason')}"); continue
        text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            errors.append(f"{model}: invalid JSON"); continue
    raise GeminiError("Gemini did not answer:\n" + "\n".join(errors[-4:]))
