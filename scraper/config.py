"""Static configuration. Only the Gemini model can be overridden from the environment."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SOURCE_BASE = "https://bojoko.com"
SOURCE_NAME = "bojoko.com"
CASINO_SLUGS = ["10bet", "mr-vegas", "betway"]
REVIEW_URL = SOURCE_BASE + "/casino/review/{slug}/"

USER_AGENT = "casino-bonus-scraper/1.0 (screening task; respects robots.txt)"
REQUEST_DELAY_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 20

DEFAULT_GEMINI_MODEL = "gemini-flash-latest"

JSON_PATH = ROOT / "docs" / "bonuses.json"
HTML_PATH = ROOT / "docs" / "index.html"


def gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL
