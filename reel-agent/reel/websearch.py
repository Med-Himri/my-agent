"""Google web + news search through Serper.dev, used for daily topic research."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import requests

QUERIES = [
    ("search", "أعطال السيارات الشائعة", "ar"),
    ("search", "نصائح صيانة السيارة", "ar"),
    ("news", "سيارات المغرب", "ar"),
    ("news", "أخبار السيارات", "ar"),
    ("news", "car technology explained", "en"),
    ("search", "most common car problems drivers ask", "en"),
    ("news", "car recall warning drivers", "en"),
]


def _one(endpoint: str, q: str, hl: str) -> list[str]:
    try:
        r = requests.post(f"https://google.serper.dev/{endpoint}",
                          headers={"X-API-KEY": os.environ.get("SERPER_API_KEY", ""), "Content-Type": "application/json"},
                          json={"q": q, "num": 10, "gl": "ma", "hl": hl}, timeout=20)
        r.raise_for_status()
    except requests.RequestException:
        return []
    d = r.json()
    out = []
    for it in (d.get("news") or d.get("organic") or [])[:10]:
        date = f" ({it['date']})" if it.get("date") else ""
        out.append(f"- {it.get('title', '')}{date}: {it.get('snippet', '')}")
    for it in d.get("peopleAlsoAsk", [])[:5]:
        out.append(f"- People also ask: {it.get('question', '')}")
    return out


def research_digest() -> str:
    """A text digest of what is being searched and reported about cars right now."""
    with ThreadPoolExecutor(len(QUERIES)) as ex:
        results = list(ex.map(lambda a: _one(*a), QUERIES))
    blocks = [f"## {ep}: {q}\n" + "\n".join(lines) for (ep, q, _), lines in zip(QUERIES, results) if lines]
    return "\n\n".join(blocks)
