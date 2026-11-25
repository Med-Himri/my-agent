"""All settings come from environment variables (or a .env file next to bot.py)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    return v.strip() if isinstance(v, str) else v


DATA = Path(env("DATA_DIR", str(ROOT / "data")))
REELS_DIR = DATA / "reels"
DB_PATH = DATA / "agent.db"

BRAND = env("BRAND", "MEDLOUT AUTO")
BRAND_AR = env("BRAND_AR", "ميدلوت أوتو")
NICHE = env("NICHE", "cars: how car systems work, maintenance tips, common faults, warning lights, "
                     "safe-driving tips and car technology explained, for Arabic-speaking drivers")
TIMEZONE = env("TIMEZONE", "Africa/Casablanca")
DAILY_TIME = env("DAILY_TIME", "09:00")          # when topic ideas are sent to Telegram
TOPICS_PER_DAY = int(env("TOPICS_PER_DAY", "4"))

MODEL = env("CLAUDE_MODEL", "claude-opus-5-5")

TELEGRAM_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_OWNER_ID = int(env("TELEGRAM_OWNER_ID", "0") or 0)

IG_USER_ID = env("IG_USER_ID")
IG_ACCESS_TOKEN = env("IG_ACCESS_TOKEN")
IG_GRAPH_HOST = env("IG_GRAPH_HOST", "graph.instagram.com")   # or graph.facebook.com (Facebook-login apps)
IG_API_VERSION = env("IG_API_VERSION", "v23.0")

MUSIC = Path(env("MUSIC_FILE", str(ROOT / "assets" / "music" / "background.mp3")))
EXAMPLE_REEL = ROOT / "assets" / "example_reel.json"
