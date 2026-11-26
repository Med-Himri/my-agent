"""Everything that needs an AI model: finding topics, writing scripts, revising them, choosing images.

LLM_PROVIDER=anthropic uses Claude (web search built in); LLM_PROVIDER=gemini uses Google Gemini
(free tier) with Google results from Serper.dev for research.
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import anthropic
from PIL import Image

from . import config, gemini, websearch

BETAS = ["server-side-fallback-2026-07-01"]   # if a request is declined, the API retries it on a fallback model
_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=4, timeout=600)
    return _client


class ClaudeError(RuntimeError):
    pass


def _create(**kw):
    r = client().beta.messages.create(model=config.MODEL, betas=BETAS, fallbacks="default", **kw)
    if r.stop_reason == "refusal":
        raise ClaudeError(f"Claude declined the request ({getattr(r.stop_details, 'category', None)})")
    if r.stop_reason == "max_tokens":
        raise ClaudeError("Claude's answer was cut off (max_tokens)")
    return r


def _json_answer(r) -> dict:
    text = next(b.text for b in r.content if b.type == "text")
    return json.loads(text)


# ------------------------------------------------------------------ schemas
COLORS = ["green", "red", "yellow", "blue", "white"]
MOODS = ["dark", "blue", "green", "red", "gray"]

PILL = {"type": "object", "additionalProperties": False, "required": ["text", "color", "cue"],
        "properties": {"text": {"type": "string"}, "color": {"type": "string", "enum": COLORS},
                       "cue": {"type": "string"}}}
SCENE = {"type": "object", "additionalProperties": False,
         "required": ["title", "mood", "voice", "image_query", "badge", "pills"],
         "properties": {"title": {"type": "string"}, "mood": {"type": "string", "enum": MOODS},
                        "voice": {"type": "string"}, "image_query": {"type": "string"},
                        "badge": {"type": "string"}, "pills": {"type": "array", "items": PILL}}}
REEL_SCHEMA = {"type": "object", "additionalProperties": False,
               "required": ["topic", "caption", "hashtags", "scenes"],
               "properties": {"topic": {"type": "string"}, "caption": {"type": "string"},
                              "hashtags": {"type": "array", "items": {"type": "string"}},
                              "scenes": {"type": "array", "items": SCENE}}}

TOPICS_TOOL = {
    "name": "submit_topics",
    "description": "Submit the final list of reel topic proposals for today. Call this exactly once, at the end.",
    "strict": True,
    "input_schema": {
        "type": "object", "additionalProperties": False, "required": ["topics"],
        "properties": {"topics": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["title_ar", "summary_ar", "angle", "why"],
            "properties": {
                "title_ar": {"type": "string", "description": "Short Arabic hook-style title, e.g. لماذا تهتز دواسة الفرامل؟"},
                "summary_ar": {"type": "string", "description": "One Arabic sentence: what the reel will explain"},
                "angle": {"type": "string", "description": "English: the key facts/structure the script should cover"},
                "why": {"type": "string", "description": "English: why this will interest the audience now (trend, season, common question)"},
            }}}},
    },
}

# ------------------------------------------------------------------ prompts
STYLE_GUIDE = f"""You write short educational Instagram reels for the Arabic car account "{config.BRAND}" ({config.BRAND_AR}).

Audience: Arabic-speaking drivers (Morocco and the wider Arab world), not mechanics.
Language: Modern Standard Arabic (فصحى), simple and friendly. Narrator: a calm male voice.

Reel structure (7-9 scenes, 100-130 words of narration in total, about 45-55 seconds):
1. Hook: a relatable question or situation that stops the scroll. Reassure or intrigue.
2. What is it? Name the system / problem plainly.
3. How it works (1-2 scenes), concrete and visual.
4. The benefit (الفائدة) or why it matters.
5. A downside, a common mistake (خطأ شائع), or when it doesn't work.
6. An important practical tip (نصيحة مهمّة).
7. Outro: "تابع {config.BRAND_AR}، لتفهم سيارتك أكثر." or a close variant, with badge.

Scene fields:
- title: the on-screen section heading, 1-3 words, often a question (تنطفئ وحدها؟ / كيف يعمل؟ / الفائدة / العيب / نصيحة مهمّة / تابعنا). Two consecutive scenes may share a title.
- mood: background colour: dark (hook/intro), blue (how it works), green (benefits, good news), red (warnings, mistakes, downsides), gray (tips, technical detail).
- voice: what the narrator says. Short sentences; commas where a breath belongs. Write numbers as Arabic words (خمس عشرة) so they are read correctly. Add shadda/tanween only where it prevents misreading. Latin acronyms like ABS are fine.
- pills: 1-3 keyword labels that pop up while the narrator speaks; at most 4 words each; digits allowed in pills (15 مرّة). color meaning: green = good/safe, red = warning/problem, yellow = key term or tip, blue = technical info, white = neutral detail. cue = the exact word(s) copied from this scene's voice text at which the pill should appear (no diacritics needed).
- image_query: an English Google Images query for a real photo or clear diagram that shows exactly what is being said (e.g. "ABS wheel speed sensor diagram"). Give an image to 4-6 scenes. Leave it "" for scenes that work better as big text pills only (mistakes, lists) and for the outro.
- badge: "" except the outro (and optionally one concept scene): 1-4 characters shown in a big yellow ring (e.g. ABS, A, ⚠).

Facts must be accurate and generally true for most modern cars; avoid brand-specific claims, prices and statistics you are not sure of. Never invent numbers.

caption: 2-4 short Arabic lines for the Instagram post: hook question, one-line answer teaser, then a call to action (save / share / follow), 1-3 emojis.
hashtags: 8-15 hashtags mixing Arabic and English, always including #ميدلوت_أوتو and #medloutauto.

Here is a reel the account owner approved; match its tone, pacing and density:
{config.EXAMPLE_REEL.read_text()}
"""


def _claude_find_topics(n: int, avoid: list[str]) -> list[dict]:
    """Research today's topic ideas with web search. Returns up to n topic dicts."""
    avoid_txt = "\n".join(f"- {t}" for t in avoid[-80:]) or "(none yet)"
    prompt = f"""Find {n} strong topics for today's reels on this account. Niche: {config.NICHE}.

Use web search to see what drivers in Morocco and the Arab world are asking about right now (seasonal issues,
common faults, new car technology, viral questions), and to check the key facts of each idea.
Good topics are concrete and explainable in under a minute with pictures (one system, one warning light, one habit),
and useful or surprising to ordinary drivers. Mix evergreen explainers with at least one timely topic.

Do not repeat or closely resemble these earlier topics:
{avoid_txt}

When you are done, call submit_topics once with exactly {n} topics."""
    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}, TOPICS_TOOL]
    for _ in range(8):
        r = _create(max_tokens=16000, system=STYLE_GUIDE, messages=messages, tools=tools,
                    thinking={"type": "adaptive"}, output_config={"effort": "medium"})
        messages.append({"role": "assistant", "content": r.content})
        for b in r.content:
            if b.type == "tool_use" and b.name == "submit_topics":
                return b.input["topics"][:n]
        if r.stop_reason == "pause_turn":
            continue                                   # server-side search loop paused; resend to resume
        if r.stop_reason == "tool_use":                # an unexpected client tool call
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": b.id, "content": "Unknown tool.", "is_error": True}
                for b in r.content if b.type == "tool_use"]})
            continue
        messages.append({"role": "user", "content": "Please call submit_topics now with your final topics."})
    raise ClaudeError("Claude did not submit topics")


def _script_prompt(topic: dict) -> str:
    return f"""Write the reel for this approved topic.

Title: {topic['title_ar']}
Summary: {topic.get('summary_ar', '')}
Key points to cover: {topic.get('angle', '')}

Return the complete reel JSON."""


def _claude_write_script(topic: dict) -> dict:
    prompt = _script_prompt(topic)
    r = _create(max_tokens=16000, system=STYLE_GUIDE, messages=[{"role": "user", "content": prompt}],
                thinking={"type": "adaptive"},
                output_config={"effort": "high", "format": {"type": "json_schema", "schema": REEL_SCHEMA}})
    return _json_answer(r)


def _revise_prompt(spec: dict, feedback: str) -> str:
    current = {k: spec[k] for k in ("topic", "caption", "hashtags")}
    current["scenes"] = [{k: s.get(k, "") for k in ("title", "mood", "voice", "image_query", "badge", "pills")}
                         for s in spec["scenes"]]
    prompt = f"""Here is the current reel:
{json.dumps(current, ensure_ascii=False, indent=1)}

The account owner reviewed the video and asks for this change:
\"\"\"{feedback}\"\"\"

Apply the change and return the complete updated reel JSON. Change only what the request needs:
keep every other scene's voice text and image_query exactly the same (unchanged scenes reuse their audio and images).
If the owner asks for a different picture in a scene, write a new, different image_query for that scene."""
    return prompt


def _claude_revise_script(spec: dict, feedback: str) -> dict:
    prompt = _revise_prompt(spec, feedback)
    r = _create(max_tokens=16000, system=STYLE_GUIDE, messages=[{"role": "user", "content": prompt}],
                thinking={"type": "adaptive"},
                output_config={"effort": "high", "format": {"type": "json_schema", "schema": REEL_SCHEMA}})
    return _json_answer(r)


def _img_block(path: Path, size: int = 768) -> dict:
    im = Image.open(path).convert("RGB")
    im.thumbnail((size, size))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=80)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(buf.getvalue()).decode()}}


PICK_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["choices"],
               "properties": {"choices": {"type": "array", "items": {
                   "type": "object", "additionalProperties": False, "required": ["scene", "image"],
                   "properties": {"scene": {"type": "integer"}, "image": {"type": "integer"}}}}}}


PICK_INSTRUCTIONS = ("You are choosing pictures for an Instagram reel. For each scene below, pick the candidate image that best "
        "shows what the narrator says. Prefer sharp, well-lit, uncluttered images; real photos or clean diagrams. "
        "Reject images with visible watermarks (getty, istock, shutterstock, alamy...), big overlaid text, logos of "
        "shops, collages, low resolution, or anything off-topic. Return image = -1 if none is acceptable.")


def _scene_label(scenes: list[dict], i: int) -> str:
    s = scenes[i]
    return f"\n## Scene {i}: {s['title']}\nNarration: {s['voice']}\nSearch: {s['image_query']}"


def _claude_pick_images(scenes: list[dict], candidates: dict[int, list[Path]]) -> dict[int, Path | None]:
    """Show Claude the candidate photos for each scene; it returns the best one (or none) per scene."""
    if not candidates:
        return {}
    content: list[dict] = [{"type": "text", "text": PICK_INSTRUCTIONS}]
    for i, paths in candidates.items():
        content.append({"type": "text", "text": _scene_label(scenes, i)})
        for k, p in enumerate(paths):
            content.append({"type": "text", "text": f"Scene {i}, image {k}:"})
            content.append(_img_block(p))
    r = _create(max_tokens=4000, messages=[{"role": "user", "content": content}],
                thinking={"type": "adaptive"},
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": PICK_SCHEMA}})
    return _apply_picks(_json_answer(r), candidates)


def _apply_picks(answer: dict, candidates: dict[int, list[Path]]) -> dict[int, Path | None]:
    out: dict[int, Path | None] = {i: None for i in candidates}
    for c in answer["choices"]:
        i, k = c["scene"], c["image"]
        if i in candidates and 0 <= k < len(candidates[i]):
            out[i] = candidates[i][k]
    return out


# ------------------------------------------------------------------ Gemini
def _gemini_find_topics(n: int, avoid: list[str]) -> list[dict]:
    avoid_txt = "\n".join(f"- {t}" for t in avoid[-80:]) or "(none yet)"
    digest = websearch.research_digest()
    prompt = f"""Propose {n} strong topics for today's reels on this account. Niche: {config.NICHE}.

Below are fresh Google search and news results about cars (Morocco and worldwide). Use them to see what drivers are
asking about and what is happening now (seasonal issues, common faults, new technology, viral questions).
Good topics are concrete and explainable in under a minute with pictures (one system, one warning light, one habit),
and useful or surprising to ordinary drivers. Mix evergreen explainers with at least one timely topic.
Only propose topics whose facts you are confident about.

Do not repeat or closely resemble these earlier topics:
{avoid_txt}

Search results:
{digest}

Return exactly {n} topics."""
    data = gemini.generate_json(STYLE_GUIDE, [{"text": prompt}], TOPICS_TOOL["input_schema"], temperature=1.0)
    return data["topics"][:n]


def _gemini_write_script(topic: dict) -> dict:
    return gemini.generate_json(STYLE_GUIDE, [{"text": _script_prompt(topic)}], REEL_SCHEMA)


def _gemini_revise_script(spec: dict, feedback: str) -> dict:
    return gemini.generate_json(STYLE_GUIDE, [{"text": _revise_prompt(spec, feedback)}], REEL_SCHEMA, temperature=0.4)


def _gemini_pick_images(scenes: list[dict], candidates: dict[int, list[Path]]) -> dict[int, Path | None]:
    """One small request per scene (free tier friendly). If Gemini is unavailable, use Google's top result."""
    out: dict[int, Path | None] = {}
    for i, paths in candidates.items():
        parts: list[dict] = [{"text": PICK_INSTRUCTIONS}, {"text": _scene_label(scenes, i)}]
        for k, p in enumerate(paths):
            parts.append({"text": f"Scene {i}, image {k}:"})
            b = _img_block(p, 512)["source"]
            parts.append({"inline_data": {"mime_type": b["media_type"], "data": b["data"]}})
        try:
            ans = gemini.generate_json("", parts, PICK_SCHEMA, temperature=0.2, max_attempts=2, timeout=60, wait=5)
            out.update(_apply_picks(ans, {i: paths}))
        except gemini.GeminiError:
            out[i] = paths[0]
    return out


# ------------------------------------------------------------------ public API
def _use_gemini() -> bool:
    return config.LLM_PROVIDER == "gemini"


def find_topics(n: int, avoid: list[str]) -> list[dict]:
    return _gemini_find_topics(n, avoid) if _use_gemini() else _claude_find_topics(n, avoid)


def write_script(topic: dict) -> dict:
    return _gemini_write_script(topic) if _use_gemini() else _claude_write_script(topic)


def revise_script(spec: dict, feedback: str) -> dict:
    return _gemini_revise_script(spec, feedback) if _use_gemini() else _claude_revise_script(spec, feedback)


def pick_images(scenes: list[dict], candidates: dict[int, list[Path]]) -> dict[int, Path | None]:
    return _gemini_pick_images(scenes, candidates) if _use_gemini() else _claude_pick_images(scenes, candidates)
