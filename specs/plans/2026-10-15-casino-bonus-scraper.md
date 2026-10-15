# Casino Bonus Scraper Implementation Plan

> **For agentic workers (Gemini is the implementer):** Execute the tasks in order and tick the checkboxes (`- [ ]`) as you go. If you have the superpowers skills, use superpowers:executing-plans; otherwise follow the steps literally. Commit after every task. When finished, hand back to the reviewer with the report described in Task 9, Step 7.

**Goal:** Running `python -m scraper` fetches 3 bojoko.com casino review pages (respecting robots.txt), uses Gemini to turn the free-text bonus terms into structured fields, writes `docs/bonuses.json`, and renders a phone-readable static `docs/index.html` from that JSON.

**Architecture:** A small Python package, `scraper/`, with one module per step: robots → fetch → parse → extract (LLM) → verify → render, plus `__main__` to orchestrate. Each module is unit-tested with fakes and saved HTML fixtures, so the tests never touch the network or the LLM. One casino failing is recorded in `errors[]` and doesn't stop the others.

**Tech Stack:** Python 3.10+, requests, beautifulsoup4, google-genai, pydantic v2, python-dotenv, pytest.

**Spec:** `specs/2026-10-15-casino-bonus-scraper-design.md`. Read it before starting; this plan implements it.

All paths are relative to the repo root `casino-bonus-scraper/`. All commands assume you are in the repo root with the venv activated (`source .venv/bin/activate`).

## Global Constraints

- Python floor: 3.10. Use `X | None` syntax; no 3.11+-only features.
- Dependencies: exactly `requests`, `beautifulsoup4`, `google-genai`, `pydantic>=2`, `python-dotenv`, `pytest`. Nothing else.
- Use the `google-genai` SDK (`from google import genai`), NOT the deprecated `google-generativeai`.
- User-Agent, exact: `casino-bonus-scraper/1.0 (screening task; respects robots.txt)`
- Source: `https://bojoko.com`. Casinos, exact slugs in this order: `10bet`, `mr-vegas`, `betway`.
- Delay between page requests: 1.5 s. Timeout: 20 s. No retries, no header spoofing, no proxies, no following redirects.
- Never request `/modal/...` or `/go/...` URLs (robots.txt disallows them). Read attributes that point to them, but never fetch them.
- robots.txt must be fetched with our own User-Agent and fed to `RobotFileParser.parse()`. Never call `RobotFileParser.read()`: it uses Python's default UA, gets a 403 from bojoko's CDN, and then treats the whole site as disallowed.
- Parse HTML only with BeautifulSoup CSS selectors. Never search raw HTML strings: bojoko's inline `<style>` contains the same class names.
- `casino` and `source_url` are always set by code, never by the LLM.
- The page has no JavaScript, and every scraped value is HTML-escaped.
- Tests must pass with no network access and no `GEMINI_API_KEY` set.
- Don't write the "written part", the "five lines on AI" or a time log. The candidate writes those.
- Don't create a GitHub remote or push. The candidate does that.

## Review Focus

Input classes the spec implies but doesn't spell out, most likely to bite first. Each has a test in its owning task.

1. **The LLM returns a currency symbol or lowercase code** (`"£"`, `"gbp"`) instead of `"GBP"`: it should be normalised to the ISO code. Tests: Task 1 `test_currency_symbol_normalised`, Task 5 `test_currency_symbol_from_llm_is_normalised`.
2. **Number formats in source text** (`£1,000`, `x35`, `35 times`, or a `£100` that must not count as evidence for `£10`; `10x` must not count as "0x / no wagering"): `verify` should neither flag correct values nor miss invented ones. Tests: Task 6.
3. **Encoding:** `£` and `&nbsp;` in the page must come out as a correct `£` and a normal space. The fetcher returns raw bytes so BeautifulSoup reads the page's own charset. Tests: Task 3 `test_returns_raw_bytes`, Task 4 `test_pound_sign_and_nbsp_survive`.
4. **Special characters in scraped text** (`&`, `<script>`): escaped exactly once on the page, never double-escaped. Tests: Task 7 `test_values_are_escaped_once`.
5. **Every casino fails** (e.g. bojoko starts blocking): JSON is still written, the page shows a clear "no data" message instead of an empty table, and the exit code is 1. Tests: Task 7 `test_empty_report_shows_message_not_table`, Task 8 `test_all_casinos_failing_still_writes_outputs`.

---

### Task 1: Project skeleton, config, models, test fakes

**Files:**
- Already present (committed by the reviewer): `.gitignore`. A local `.env` also already exists and is ignored.
- Create: `requirements.txt`, `.env.example`, `pytest.ini`
- Create: `scraper/__init__.py`, `scraper/config.py`, `scraper/models.py`
- Create: `tests/__init__.py`, `tests/fakes.py`, `tests/fixtures/` (directory)
- Test: `tests/test_models.py`

**Interfaces:**
- Produces:
  - `scraper.config`:
    - `ROOT: Path`, `SOURCE_BASE: str`, `SOURCE_NAME: str`, `CASINO_SLUGS: list[str]`, `REVIEW_URL: str` (format with `slug=`)
    - `USER_AGENT: str`, `REQUEST_DELAY_SECONDS: float`, `REQUEST_TIMEOUT_SECONDS: int`
    - `DEFAULT_GEMINI_MODEL: str`, `gemini_model() -> str`
    - `JSON_PATH: Path`, `HTML_PATH: Path`
  - `scraper.models`:
    - `CURRENCY_SYMBOLS: dict[str, str]` (code → symbol), `tidy_number(value: float | None) -> float | int | None`, `format_number(value: float) -> str`
    - `MinimumDeposit(amount: float, currency: str)`, `BonusFields(welcome_bonus, wagering_requirement, minimum_deposit)`, `BonusSnippet(slug, casino, source_url, info_rows, terms_text)`
    - `CasinoBonus(casino, welcome_bonus, wagering_requirement, minimum_deposit, source_url, warnings)`, `CasinoError(casino, source_url, error)`, `BonusReport(generated_at, source, model, casinos, errors)`
  - `tests.fakes`: `FIXTURES: Path`, `FakeResponse`, `FakeSession`, `FakeGeminiClient`, `FakeFetcher`

- [x] **Step 1: Create the venv and the static project files**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

`.gitignore` already exists with this content. Check it, don't recreate it:
```
.env
.venv/
__pycache__/
.pytest_cache/
*.pyc
```

`requirements.txt`:
```
requests>=2.31
beautifulsoup4>=4.12
google-genai>=1.0
pydantic>=2.6
python-dotenv>=1.0
pytest>=8.0
```

`.env.example`:
```
# Free key: https://aistudio.google.com/apikey
GEMINI_API_KEY=
# Optional override of the Gemini model id
# GEMINI_MODEL=gemini-flash-latest
```

`pytest.ini`:
```
[pytest]
testpaths = tests
```

`scraper/__init__.py` and `tests/__init__.py`: empty files.

Run: `pip install -r requirements.txt`
Expected: installs without errors.

- [x] **Step 2: Write `scraper/config.py`**

```python
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
```

- [x] **Step 3: Write `tests/fakes.py`** (used by later tasks; created now so every task can import it)

```python
"""Test doubles for HTTP and Gemini. Tests never touch the network."""
from pathlib import Path
from types import SimpleNamespace

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, status_code: int, text: str = "", content: bytes | None = None):
        self.status_code = status_code
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")
        self.headers = {}


class FakeSession:
    """Returns canned responses keyed by URL and records every request made."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append({"url": url, **kwargs})
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


class FakeModels:
    def __init__(self, text, error):
        self.text = text
        self.error = error
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.error is not None:
            raise self.error
        return SimpleNamespace(text=self.text)


class FakeGeminiClient:
    """Mimics genai.Client: client.models.generate_content(...) returns an object with .text."""

    def __init__(self, text: str | None = None, error: Exception | None = None):
        self.models = FakeModels(text, error)


class FakeFetcher:
    """Mimics scraper.fetch.Fetcher: maps URL -> bytes, or an Exception to raise."""

    def __init__(self, pages: dict):
        self.pages = pages

    def fetch_html(self, url: str) -> bytes:
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return page
```

- [x] **Step 4: Write the failing tests `tests/test_models.py`**

```python
import json

import pytest
from pydantic import ValidationError

from scraper.models import BonusFields, CasinoBonus, MinimumDeposit, format_number, tidy_number


@pytest.mark.parametrize("raw, expected", [("£", "GBP"), ("€", "EUR"), ("$", "USD"), (" gbp ", "GBP"), ("EUR", "EUR")])
def test_currency_symbol_normalised(raw, expected):
    assert MinimumDeposit(amount=10, currency=raw).currency == expected


def test_whole_numbers_serialise_as_integers():
    bonus = CasinoBonus(
        casino="10Bet",
        welcome_bonus="100% up to £25",
        wagering_requirement=10.0,
        minimum_deposit=MinimumDeposit(amount=10.0, currency="GBP"),
        source_url="https://bojoko.com/casino/review/10bet/",
    )
    data = json.loads(bonus.model_dump_json())
    assert data["wagering_requirement"] == 10 and isinstance(data["wagering_requirement"], int)
    assert data["minimum_deposit"] == {"amount": 10, "currency": "GBP"}
    assert isinstance(data["minimum_deposit"]["amount"], int)
    assert data["warnings"] == []
    assert list(data)[0] == "casino"


def test_fractional_numbers_kept():
    assert tidy_number(0.5) == 0.5
    assert tidy_number(None) is None
    assert format_number(35.0) == "35"
    assert format_number(0.5) == "0.5"


def test_bonus_fields_allow_nulls():
    fields = BonusFields(welcome_bonus="150 free spins", wagering_requirement=None, minimum_deposit=None)
    assert fields.wagering_requirement is None


def test_bonus_fields_require_welcome_bonus():
    with pytest.raises(ValidationError):
        BonusFields.model_validate({"wagering_requirement": 10, "minimum_deposit": None})
```

- [x] **Step 5: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.models'`

- [x] **Step 6: Write `scraper/models.py`**

```python
"""Data shapes shared by the LLM output, the JSON file and the page."""
from pydantic import BaseModel, Field, field_serializer, field_validator

# ISO 4217 code -> symbol. Used to normalise LLM output, verify amounts and format the page.
CURRENCY_SYMBOLS = {"GBP": "£", "EUR": "€", "USD": "$"}
_SYMBOL_TO_CODE = {symbol: code for code, symbol in CURRENCY_SYMBOLS.items()}


def tidy_number(value: float | None) -> float | int | None:
    """10.0 -> 10 so the JSON reads like the source ("10x"), while 0.5 stays 0.5."""
    if value is not None and float(value).is_integer():
        return int(value)
    return value


def format_number(value: float) -> str:
    return str(tidy_number(value))


class MinimumDeposit(BaseModel):
    amount: float
    currency: str  # ISO 4217, e.g. "GBP"

    @field_validator("currency")
    @classmethod
    def normalise_currency(cls, value: str) -> str:
        value = value.strip()
        return _SYMBOL_TO_CODE.get(value, value.upper())

    @field_serializer("amount")
    def _tidy_amount(self, value: float) -> float | int:
        return tidy_number(value)


class BonusFields(BaseModel):
    """Exactly what the LLM is asked to return."""

    welcome_bonus: str
    wagering_requirement: float | None  # 0 = explicitly no wagering; None = not stated
    minimum_deposit: MinimumDeposit | None


class BonusSnippet(BaseModel):
    """The scoped part of a review page that is sent to the LLM."""

    slug: str
    casino: str
    source_url: str
    info_rows: dict[str, str]
    terms_text: str


class CasinoBonus(BaseModel):
    casino: str
    welcome_bonus: str
    wagering_requirement: float | None
    minimum_deposit: MinimumDeposit | None
    source_url: str
    warnings: list[str] = Field(default_factory=list)

    @field_serializer("wagering_requirement")
    def _tidy_wagering(self, value: float | None) -> float | int | None:
        return tidy_number(value)


class CasinoError(BaseModel):
    casino: str  # the slug
    source_url: str
    error: str


class BonusReport(BaseModel):
    generated_at: str  # ISO 8601 UTC with "Z" suffix
    source: str
    model: str
    casinos: list[CasinoBonus]
    errors: list[CasinoError]
```

Note: `CasinoBonus` lists its fields explicitly instead of subclassing `BonusFields`, so `casino` comes first in the JSON. This is a deliberate small deviation from the spec's sketch.

- [x] **Step 7: Run the tests and confirm they pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: 9 passed

- [x] **Step 8: Commit**

```bash
git add requirements.txt .env.example pytest.ini scraper/__init__.py scraper/config.py scraper/models.py tests/__init__.py tests/fakes.py tests/test_models.py
git commit -m "feat: project skeleton, config and data models"
```

---

### Task 2: robots.txt handling

**Files:**
- Create: `scraper/robots.py`
- Create: `tests/fixtures/robots.txt`
- Test: `tests/test_robots.py`

**Interfaces:**
- Consumes: `config.USER_AGENT`, `config.REQUEST_TIMEOUT_SECONDS`; `tests.fakes.FakeSession`, `FakeResponse`, `FIXTURES`
- Produces:
  - `class RobotsUnavailable(Exception)`
  - `load_robots(base_url: str, session) -> urllib.robotparser.RobotFileParser`
  - `is_allowed(parser: RobotFileParser, url: str) -> bool`

- [x] **Step 1: Create `tests/fixtures/robots.txt`** (bojoko's robots.txt as of 2026-10-15)

```
User-Agent: *
Disallow: /modal/
Disallow: /go/
Disallow: /ca/modal/
Disallow: /fi/modal/
Disallow: /admin/
Disallow: /ca/admin/
Disallow: /fi/admin/
Disallow: /api/*/ajax-load/toplist-first-item-footer/
Sitemap: https://bojoko.com/sitemap.xml
```

- [x] **Step 2: Write the failing tests `tests/test_robots.py`**

```python
import pytest
import requests

from scraper import config
from scraper.robots import RobotsUnavailable, is_allowed, load_robots
from tests.fakes import FIXTURES, FakeResponse, FakeSession

ROBOTS_URL = "https://bojoko.com/robots.txt"
ROBOTS_TXT = (FIXTURES / "robots.txt").read_text(encoding="utf-8")


def test_review_pages_allowed_but_modal_and_go_disallowed():
    parser = load_robots("https://bojoko.com", FakeSession({ROBOTS_URL: FakeResponse(200, ROBOTS_TXT)}))
    assert is_allowed(parser, "https://bojoko.com/casino/review/10bet/")
    assert not is_allowed(parser, "https://bojoko.com/modal/casino/terms-and-conditions/1627/")
    assert not is_allowed(parser, "https://bojoko.com/go/10bet-casino/")


def test_robots_fetched_with_our_user_agent():
    session = FakeSession({ROBOTS_URL: FakeResponse(200, ROBOTS_TXT)})
    load_robots("https://bojoko.com/", session)
    assert session.requests[0]["url"] == ROBOTS_URL
    assert session.requests[0]["headers"]["User-Agent"] == config.USER_AGENT


def test_missing_robots_allows_everything():
    parser = load_robots("https://bojoko.com", FakeSession({ROBOTS_URL: FakeResponse(404)}))
    assert is_allowed(parser, "https://bojoko.com/anything/")


@pytest.mark.parametrize("status", [401, 403, 500])
def test_unreadable_robots_raises(status):
    with pytest.raises(RobotsUnavailable, match=str(status)):
        load_robots("https://bojoko.com", FakeSession({ROBOTS_URL: FakeResponse(status)}))


def test_network_error_raises():
    session = FakeSession({ROBOTS_URL: requests.ConnectionError("boom")})
    with pytest.raises(RobotsUnavailable, match="boom"):
        load_robots("https://bojoko.com", session)
```

- [x] **Step 3: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_robots.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.robots'`

- [x] **Step 4: Write `scraper/robots.py`**

```python
"""robots.txt handling.

RobotFileParser.read() fetches with Python's default user-agent, which bojoko's
CDN answers with 403, and robotparser treats a 403 as "disallow everything".
So we fetch the file ourselves, with our own user-agent, and only use
robotparser to parse it.
"""
from urllib.robotparser import RobotFileParser

import requests

from scraper import config


class RobotsUnavailable(Exception):
    """robots.txt could not be read, so we must not scrape."""


def load_robots(base_url: str, session) -> RobotFileParser:
    url = base_url.rstrip("/") + "/robots.txt"
    try:
        response = session.get(
            url,
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise RobotsUnavailable(f"could not fetch {url}: {exc}") from exc

    parser = RobotFileParser(url)
    if response.status_code == 200:
        parser.parse(response.text.splitlines())
    elif response.status_code == 404:
        parser.parse([])  # no robots.txt means everything is allowed
    else:
        raise RobotsUnavailable(f"{url} returned HTTP {response.status_code}")
    return parser


def is_allowed(parser: RobotFileParser, url: str) -> bool:
    return parser.can_fetch(config.USER_AGENT, url)
```

- [x] **Step 5: Run the tests and confirm they pass**

Run: `python -m pytest tests/test_robots.py -v`
Expected: 7 passed

- [x] **Step 6: Commit**

```bash
git add scraper/robots.py tests/fixtures/robots.txt tests/test_robots.py
git commit -m "feat: robots.txt loading with our own user-agent"
```

---

### Task 3: Polite fetcher

**Files:**
- Create: `scraper/fetch.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Consumes: `scraper.robots.is_allowed`; `config.USER_AGENT`, `config.REQUEST_DELAY_SECONDS`, `config.REQUEST_TIMEOUT_SECONDS`
- Produces:
  - `class FetchError(Exception)`, `class DisallowedByRobots(FetchError)`, `class BlockedError(FetchError)`
  - `class Fetcher(session, robots: RobotFileParser, delay: float = config.REQUEST_DELAY_SECONDS, sleep=time.sleep)` with method `fetch_html(url: str) -> bytes`

Note: the spec sketched a `fetch_html(url, rp, session)` function. A small class replaces it because "delay between requests, not before the first" needs state. The method returns raw **bytes** so BeautifulSoup can read the page's own charset declaration, which avoids `requests` mis-guessing the encoding and turning `£` into `Â£`.

- [x] **Step 1: Write the failing tests `tests/test_fetch.py`**

```python
from urllib.robotparser import RobotFileParser

import pytest
import requests

from scraper import config
from scraper.fetch import BlockedError, DisallowedByRobots, Fetcher, FetchError
from tests.fakes import FakeResponse, FakeSession

URL = "https://bojoko.com/casino/review/10bet/"


def robots(*lines: str) -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse(list(lines))
    return parser


ALLOW_ALL = robots()


def fetcher(session, parser=ALLOW_ALL, sleeps=None):
    return Fetcher(session, parser, delay=1.5, sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_disallowed_url_raises_without_making_a_request():
    session = FakeSession({})
    with pytest.raises(DisallowedByRobots):
        fetcher(session, robots("User-agent: *", "Disallow: /modal/")).fetch_html("https://bojoko.com/modal/x/")
    assert session.requests == []


def test_returns_raw_bytes():
    body = "<p>Min £10</p>".encode("utf-8")
    session = FakeSession({URL: FakeResponse(200, content=body)})
    assert fetcher(session).fetch_html(URL) == body


def test_sends_user_agent_timeout_and_does_not_follow_redirects():
    session = FakeSession({URL: FakeResponse(200, "ok")})
    fetcher(session).fetch_html(URL)
    request = session.requests[0]
    assert request["headers"]["User-Agent"] == config.USER_AGENT
    assert request["timeout"] == config.REQUEST_TIMEOUT_SECONDS
    assert request["allow_redirects"] is False


@pytest.mark.parametrize("status", [401, 403, 429])
def test_block_statuses_raise_blocked_error(status):
    with pytest.raises(BlockedError, match=f"blocked: HTTP {status}"):
        fetcher(FakeSession({URL: FakeResponse(status)})).fetch_html(URL)


@pytest.mark.parametrize("status", [301, 404, 500])
def test_other_non_2xx_raise_fetch_error(status):
    with pytest.raises(FetchError, match=f"HTTP {status}") as info:
        fetcher(FakeSession({URL: FakeResponse(status)})).fetch_html(URL)
    assert not isinstance(info.value, BlockedError)


def test_network_error_raises_fetch_error():
    with pytest.raises(FetchError, match="boom"):
        fetcher(FakeSession({URL: requests.ConnectionError("boom")})).fetch_html(URL)


def test_sleeps_between_requests_but_not_before_the_first():
    other = "https://bojoko.com/casino/review/betway/"
    sleeps = []
    f = fetcher(FakeSession({URL: FakeResponse(200, "a"), other: FakeResponse(200, "b")}), sleeps=sleeps)
    f.fetch_html(URL)
    assert sleeps == []
    f.fetch_html(other)
    assert sleeps == [1.5]
```

- [x] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.fetch'`

- [x] **Step 3: Write `scraper/fetch.py`**

```python
"""Polite HTTP fetching: robots check first, honest user-agent, a delay, no retries.

A block (401/403/429) is reported, never worked around.
"""
import time

import requests

from scraper import config
from scraper.robots import is_allowed


class FetchError(Exception):
    """The page could not be fetched."""


class DisallowedByRobots(FetchError):
    """robots.txt does not allow this URL."""


class BlockedError(FetchError):
    """The site refused us. We stop rather than try to get around it."""


class Fetcher:
    def __init__(self, session, robots, delay: float = config.REQUEST_DELAY_SECONDS, sleep=time.sleep):
        self._session = session
        self._robots = robots
        self._delay = delay
        self._sleep = sleep
        self._has_fetched = False

    def fetch_html(self, url: str) -> bytes:
        if not is_allowed(self._robots, url):
            raise DisallowedByRobots(f"robots.txt disallows {url}")
        if self._has_fetched:
            self._sleep(self._delay)
        self._has_fetched = True

        try:
            response = self._session.get(
                url,
                headers={"User-Agent": config.USER_AGENT},
                timeout=config.REQUEST_TIMEOUT_SECONDS,
                allow_redirects=False,  # a redirect could lead to a path robots.txt disallows
            )
        except requests.RequestException as exc:
            raise FetchError(f"request failed: {exc}") from exc

        if response.status_code in (401, 403, 429):
            raise BlockedError(f"blocked: HTTP {response.status_code}")
        if not 200 <= response.status_code < 300:
            raise FetchError(f"HTTP {response.status_code} for {url}")
        return response.content
```

- [x] **Step 4: Run the tests and confirm they pass**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: 11 passed

- [x] **Step 5: Commit**

```bash
git add scraper/fetch.py tests/test_fetch.py
git commit -m "feat: polite fetcher that respects robots.txt and blocks"
```

---

### Task 4: HTML fixtures and bonus-card parser

**Files:**
- Create: `tests/fixtures/10bet.html`, `tests/fixtures/mr-vegas.html`, `tests/fixtures/betway.html` (captured live), `tests/fixtures/no-card.html`
- Create: `scraper/parse.py`
- Test: `tests/test_parse.py`

**Interfaces:**
- Consumes: `Fetcher`, `load_robots` (only to capture the fixtures); `BonusSnippet`
- Produces:
  - `class BonusCardNotFound(Exception)`
  - `parse_bonus(html: bytes | str, slug: str, source_url: str) -> BonusSnippet`

- [x] **Step 1: Capture the three review pages with our own fetcher** (the only network use in this task; it goes through the robots check and the delay)

```bash
python - <<'EOF'
import requests
from scraper import config
from scraper.fetch import Fetcher
from scraper.robots import load_robots

session = requests.Session()
fetcher = Fetcher(session, load_robots(config.SOURCE_BASE, session))
for slug in config.CASINO_SLUGS:
    html = fetcher.fetch_html(config.REVIEW_URL.format(slug=slug))
    (config.ROOT / "tests" / "fixtures" / f"{slug}.html").write_bytes(html)
    print(slug, len(html), "bytes")
EOF
```

Expected: three lines, each over 100000 bytes. If this raises `BlockedError` or `DisallowedByRobots`, STOP and report back. Don't try to work around it.

- [x] **Step 2: Create `tests/fixtures/no-card.html`.** The `<style>` contains the class names on purpose, to prove the parser ignores them:

```html
<!doctype html>
<html><head><meta charset="utf-8">
<style>.card-toplist-row__content--bonus-card{display:grid}.card-toplist-row__footer--bonus-card{font-size:12px}</style>
</head><body><h1>Some Casino Review</h1><p>No offer right now.</p></body></html>
```

- [x] **Step 3: Write the failing tests `tests/test_parse.py`**

```python
import pytest

from scraper.parse import BonusCardNotFound, parse_bonus
from tests.fakes import FIXTURES


def url(slug: str) -> str:
    return f"https://bojoko.com/casino/review/{slug}/"


def load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# Phrases verified on the live pages on 2026-10-15.
@pytest.mark.parametrize(
    "slug, phrase",
    [
        ("10bet", "Wager bonus 10x"),
        ("mr-vegas", "Wagering requirement: 10x"),
        ("betway", "No wagering requirements"),
    ],
)
def test_terms_text_extracted_from_live_fixtures(slug, phrase):
    snippet = parse_bonus(load(f"{slug}.html"), slug, url(slug))
    assert phrase in snippet.terms_text
    assert "  " not in snippet.terms_text
    assert snippet.casino
    assert snippet.slug == slug
    assert snippet.source_url == url(slug)


def test_10bet_info_rows_and_name():
    snippet = parse_bonus(load("10bet.html"), "10bet", url("10bet"))
    assert snippet.casino == "10Bet"
    assert snippet.info_rows["1st deposit bonus"] == "100%/£25"
    assert snippet.info_rows["Minimum deposit for bonus"] == "£10"


def test_class_names_inside_style_do_not_count_as_a_card():
    with pytest.raises(BonusCardNotFound, match="no-card"):
        parse_bonus(load("no-card.html"), "no-card", url("no-card"))


def page(footer: str, with_cta: bool = True) -> bytes:
    cta = (
        '<div class="card-toplist-row__cta-wrapper card-toplist-row__cta-wrapper--bonus-card">'
        '<a href="/go/example/" data-ga-label="Example Casino">Play here »</a></div>'
        if with_cta
        else ""
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"></head><body>{cta}
<div class="card-toplist-row__content card-toplist-row__content--bonus-card"><table><tbody>
<tr class="card-toplist-row__info-row"><th class="card-toplist-row__info-name" scope="row">1st
  deposit bonus</th><td class="card-toplist-row__info-value"> 100%/£50 </td></tr>
</tbody></table></div>
<small class="card-toplist-row__footer card-toplist-row__footer--bonus-card">{footer}</small>
</body></html>""".encode("utf-8")


def test_pound_sign_and_nbsp_survive():
    snippet = parse_bonus(page("Min&nbsp;£10.\n   Wager 35x."), "example", url("example"))
    assert snippet.terms_text == "Min £10. Wager 35x."
    assert snippet.info_rows == {"1st deposit bonus": "100%/£50"}
    assert snippet.casino == "Example Casino"


def test_casino_name_falls_back_to_slug():
    snippet = parse_bonus(page("Wager 35x.", with_cta=False), "example", url("example"))
    assert snippet.casino == "example"


def test_missing_terms_footer_raises():
    html = page("x").replace(b'card-toplist-row__footer--bonus-card', b"something-else")
    with pytest.raises(BonusCardNotFound):
        parse_bonus(html, "example", url("example"))
```

If a live fixture's wording no longer matches a phrase above (bojoko changed the offer since 2026-10-15), update the phrase to the text actually in the fixture and mention it in your hand-back report. Do NOT change the parser to make a stale phrase pass.

- [x] **Step 4: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_parse.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.parse'`

- [x] **Step 5: Write `scraper/parse.py`**

```python
"""Isolate the welcome-bonus card from a bojoko review page.

Only CSS selectors are used: the same class names also appear inside an inline
<style> block, so searching the raw HTML string would give false matches.
"""
from bs4 import BeautifulSoup

from scraper.models import BonusSnippet

CARD = ".card-toplist-row__content--bonus-card"
TERMS = "small.card-toplist-row__footer--bonus-card"
CTA = ".card-toplist-row__cta-wrapper--bonus-card a[data-ga-label]"  # href is /go/..., never fetched


class BonusCardNotFound(Exception):
    """The page has no bonus card. Most likely bojoko changed its markup."""


def _clean(text: str) -> str:
    return " ".join(text.split())  # also turns non-breaking spaces into normal ones


def parse_bonus(html: bytes | str, slug: str, source_url: str) -> BonusSnippet:
    soup = BeautifulSoup(html, "html.parser")
    card = soup.select_one(CARD)
    terms = soup.select_one(TERMS)
    if card is None or terms is None:
        raise BonusCardNotFound(f"no bonus card found on the {slug} page")

    info_rows = {}
    for row in card.select("tr.card-toplist-row__info-row"):
        name = row.select_one("th.card-toplist-row__info-name")
        value = row.select_one("td.card-toplist-row__info-value")
        if name is not None and value is not None:
            info_rows[_clean(name.get_text(" "))] = _clean(value.get_text(" "))

    cta = soup.select_one(CTA)
    casino = _clean(cta["data-ga-label"]) if cta is not None else slug

    return BonusSnippet(
        slug=slug,
        casino=casino or slug,
        source_url=source_url,
        info_rows=info_rows,
        terms_text=_clean(terms.get_text(" ")),
    )
```

- [x] **Step 6: Run the tests and confirm they pass**

Run: `python -m pytest tests/test_parse.py -v`
Expected: 8 passed

- [x] **Step 7: Commit**

```bash
git add scraper/parse.py tests/test_parse.py tests/fixtures/
git commit -m "feat: parse bonus card and T&Cs from bojoko review pages"
```

---

### Task 5: Gemini extraction

**Files:**
- Create: `scraper/extract.py`
- Test: `tests/test_extract.py`

**Interfaces:**
- Consumes: `BonusSnippet`, `BonusFields`; `tests.fakes.FakeGeminiClient`
- Produces:
  - `class ExtractionError(Exception)`
  - `SYSTEM_PROMPT: str`, `build_prompt(snippet: BonusSnippet) -> str`
  - `extract_fields(snippet: BonusSnippet, client, model: str) -> BonusFields`. `client` is a `genai.Client` or a fake with `.models.generate_content(model=, contents=, config=)`.

- [x] **Step 1: Write the failing tests `tests/test_extract.py`**

```python
import pytest

from scraper.extract import ExtractionError, SYSTEM_PROMPT, extract_fields
from scraper.models import BonusFields, BonusSnippet
from tests.fakes import FakeGeminiClient

SNIPPET = BonusSnippet(
    slug="10bet",
    casino="10Bet",
    source_url="https://bojoko.com/casino/review/10bet/",
    info_rows={"1st deposit bonus": "100%/£25", "Minimum deposit for bonus": "£10"},
    terms_text="Wager bonus 10x within 3 days on slots. Max bonus winnings: £1,000.",
)
VALID = '{"welcome_bonus": "100% up to £25", "wagering_requirement": 10, "minimum_deposit": {"amount": 10, "currency": "GBP"}}'


def test_valid_response_becomes_bonus_fields():
    fields = extract_fields(SNIPPET, FakeGeminiClient(VALID), "test-model")
    assert fields == BonusFields(
        welcome_bonus="100% up to £25",
        wagering_requirement=10,
        minimum_deposit={"amount": 10, "currency": "GBP"},
    )


def test_nulls_are_accepted():
    text = '{"welcome_bonus": "150 free spins", "wagering_requirement": null, "minimum_deposit": null}'
    fields = extract_fields(SNIPPET, FakeGeminiClient(text), "test-model")
    assert fields.wagering_requirement is None
    assert fields.minimum_deposit is None


def test_currency_symbol_from_llm_is_normalised():
    text = '{"welcome_bonus": "x", "wagering_requirement": 0, "minimum_deposit": {"amount": 10, "currency": "£"}}'
    assert extract_fields(SNIPPET, FakeGeminiClient(text), "m").minimum_deposit.currency == "GBP"


def test_request_sends_snippet_with_schema_and_zero_temperature():
    client = FakeGeminiClient(VALID)
    extract_fields(SNIPPET, client, "test-model")
    call = client.models.calls[0]
    assert call["model"] == "test-model"
    assert "Wager bonus 10x within 3 days" in call["contents"]
    assert "1st deposit bonus: 100%/£25" in call["contents"]
    config = call["config"]
    assert config.temperature == 0
    assert config.response_mime_type == "application/json"
    assert config.response_schema is BonusFields
    assert config.system_instruction == SYSTEM_PROMPT


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"wagering_requirement": 10, "minimum_deposit": null}',  # missing welcome_bonus
        '{"welcome_bonus": "x", "wagering_requirement": "lots", "minimum_deposit": null}',
        None,
    ],
)
def test_bad_responses_raise_extraction_error(text):
    with pytest.raises(ExtractionError, match="invalid data"):
        extract_fields(SNIPPET, FakeGeminiClient(text), "test-model")


def test_sdk_error_raises_extraction_error():
    with pytest.raises(ExtractionError, match="quota"):
        extract_fields(SNIPPET, FakeGeminiClient(error=RuntimeError("quota exceeded")), "test-model")
```

- [x] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_extract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.extract'`

- [x] **Step 3: Write `scraper/extract.py`**

```python
"""Turn a bonus snippet's free-text terms into structured fields with Gemini."""
from google.genai import types
from pydantic import ValidationError

from scraper.models import BonusFields, BonusSnippet

SYSTEM_PROMPT = """You extract casino welcome-bonus terms into JSON.
Rules:
- Use only facts stated in the provided text. Never guess or use outside knowledge.
- welcome_bonus: a short summary such as "100% up to £25" or "150 free spins". If the offer has both a deposit match and spins, combine them, e.g. "100% up to £100 + 50 free spins".
- wagering_requirement: the wagering multiplier as a number (35 for "35x"). If several are given, use the one on bonus money. Return 0 only if the text explicitly says the welcome offer has no wagering. Return null if it is not stated.
- minimum_deposit: the minimum deposit or qualifying stake for the welcome offer, as an amount and an ISO 4217 currency code (£ = GBP, € = EUR, $ = USD). Return null if it is not stated."""


class ExtractionError(Exception):
    """The LLM call failed or returned data that does not fit the schema."""


def build_prompt(snippet: BonusSnippet) -> str:
    rows = "\n".join(f"{name}: {value}" for name, value in snippet.info_rows.items())
    return (
        f"Casino: {snippet.casino}\n\n"
        f"Offer summary table:\n{rows or '(none)'}\n\n"
        f"Terms and conditions:\n{snippet.terms_text}"
    )


def extract_fields(snippet: BonusSnippet, client, model: str) -> BonusFields:
    try:
        response = client.models.generate_content(
            model=model,
            contents=build_prompt(snippet),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0,
                response_mime_type="application/json",
                response_schema=BonusFields,
            ),
        )
    except Exception as exc:  # the SDK raises several error types; any of them fails only this casino
        raise ExtractionError(f"Gemini request failed: {exc}") from exc

    try:
        return BonusFields.model_validate_json(response.text or "")
    except ValidationError as exc:
        raise ExtractionError(f"Gemini returned invalid data: {exc}") from exc
```

- [x] **Step 4: Run the tests and confirm they pass**

Run: `python -m pytest tests/test_extract.py -v`
Expected: 9 passed

- [x] **Step 5: Commit**

```bash
git add scraper/extract.py tests/test_extract.py
git commit -m "feat: extract structured bonus fields with Gemini"
```

---

### Task 6: Verify LLM numbers against the source text

**Files:**
- Create: `scraper/verify.py`
- Test: `tests/test_verify.py`

**Interfaces:**
- Consumes: `BonusFields`, `BonusSnippet`, `CURRENCY_SYMBOLS`, `format_number`
- Produces: `verify(fields: BonusFields, snippet: BonusSnippet) -> list[str]` (human-readable warnings; empty means OK)

- [x] **Step 1: Write the failing tests `tests/test_verify.py`**

```python
import pytest

from scraper.models import BonusFields, BonusSnippet
from scraper.verify import verify


def snippet(terms: str, rows: dict | None = None) -> BonusSnippet:
    return BonusSnippet(slug="s", casino="C", source_url="https://bojoko.com/casino/review/s/", info_rows=rows or {}, terms_text=terms)


def fields(wagering=None, deposit=None) -> BonusFields:
    return BonusFields(welcome_bonus="offer", wagering_requirement=wagering, minimum_deposit=deposit)


@pytest.mark.parametrize(
    "wagering, terms",
    [
        (10, "Wager bonus 10x within 3 days on slots."),
        (10, "Wagering requirement: 10 x the bonus."),
        (35, "You must wager x35 before withdrawing."),
        (35, "Bonus must be wagered 35 times."),
        (0.5, "Wager 0.5x the bonus."),
        (0, "No wagering requirements on Free Spins Winnings."),
        (0, "Wager-free spins."),
        (None, "Anything at all."),
    ],
)
def test_supported_wagering_is_not_flagged(wagering, terms):
    assert verify(fields(wagering=wagering), snippet(terms)) == []


def test_wagering_from_info_rows_counts():
    assert verify(fields(wagering=0), snippet("Spins expire after 7 days.", {"Wagering requirements (bonus money)": "0x"})) == []


@pytest.mark.parametrize(
    "wagering, terms",
    [
        (35, "Wager bonus 10x within 3 days."),
        (10, "Wager bonus 100x."),           # 10 must not match inside 100
        (0, "Wager bonus 10x."),             # the "0x" inside "10x" is not "no wagering"
    ],
)
def test_unsupported_wagering_is_flagged(wagering, terms):
    warnings = verify(fields(wagering=wagering), snippet(terms))
    assert len(warnings) == 1
    assert warnings[0].startswith(f"wagering_requirement {wagering}")


@pytest.mark.parametrize(
    "amount, currency, terms",
    [
        (10, "GBP", "Deposit & Stake Min £10."),
        (10, "GBP", "Min deposit £ 10.00 required"),
        (1000, "GBP", "Minimum deposit £1,000."),
        (20, "EUR", "Minimum deposit 20 EUR."),
        (5, "USD", "Deposit $5 to qualify"),
    ],
)
def test_supported_deposit_is_not_flagged(amount, currency, terms):
    assert verify(fields(deposit={"amount": amount, "currency": currency}), snippet(terms)) == []


def test_deposit_from_info_rows_counts():
    rows = {"Minimum deposit for bonus": "£10"}
    assert verify(fields(deposit={"amount": 10, "currency": "GBP"}), snippet("T&Cs apply.", rows)) == []


@pytest.mark.parametrize(
    "amount, terms",
    [
        (20, "Deposit & Stake Min £10."),
        (10, "Max bonus winnings £100."),   # 10 must not match inside 100
        (10, "10p per spin, £0.10 each."),  # no "£10" anywhere
    ],
)
def test_unsupported_deposit_is_flagged(amount, terms):
    warnings = verify(fields(deposit={"amount": amount, "currency": "GBP"}), snippet(terms))
    assert warnings == [f"minimum_deposit {amount} GBP not found in source text"]
```

- [x] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_verify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.verify'`

- [x] **Step 3: Write `scraper/verify.py`**

```python
"""Cross-check the LLM's numbers against the source text to catch invented values.

A mismatch is a warning, not a failure: it is logged and stored with the casino
so a human can check it. This is a heuristic. It catches invented numbers, but
not a real number attributed to the wrong field.
"""
import re

from scraper.models import CURRENCY_SYMBOLS, BonusFields, BonusSnippet, format_number

# The number must not continue: "10" must not match inside "100" or "10.5".
_NUMBER_END = r"(?!\d|[.,]\d)"
_NUMBER_START = r"(?<![\d.])"
_NO_WAGERING = re.compile(r"no wagering|wager-free|wagering[- ]free|(?<![\d.])0\s*x\b")


def _haystack(snippet: BonusSnippet) -> str:
    text = " ".join([snippet.terms_text, *snippet.info_rows.values()]).lower()
    return re.sub(r"(?<=\d),(?=\d{3})", "", text)  # "£1,000" -> "£1000"


def _check_wagering(value: float | None, haystack: str) -> list[str]:
    if value is None:
        return []
    if value == 0:
        if _NO_WAGERING.search(haystack):
            return []
        return ["wagering_requirement 0 but the source text does not say there is no wagering"]
    n = re.escape(format_number(value))
    pattern = rf"{_NUMBER_START}{n}\s*x\b|\bx\s*{n}{_NUMBER_END}|{_NUMBER_START}{n}\s*times\b"
    if re.search(pattern, haystack):
        return []
    return [f"wagering_requirement {format_number(value)} not found in source text"]


def _check_deposit(fields: BonusFields, haystack: str) -> list[str]:
    deposit = fields.minimum_deposit
    if deposit is None:
        return []
    n = re.escape(format_number(deposit.amount))
    amount = rf"{n}(?:\.00)?{_NUMBER_END}"
    options = [rf"{_NUMBER_START}{amount}\s*{re.escape(deposit.currency.lower())}\b"]
    symbol = CURRENCY_SYMBOLS.get(deposit.currency)
    if symbol:
        options.append(rf"{re.escape(symbol)}\s*{amount}")
    if re.search("|".join(options), haystack):
        return []
    return [f"minimum_deposit {format_number(deposit.amount)} {deposit.currency} not found in source text"]


def verify(fields: BonusFields, snippet: BonusSnippet) -> list[str]:
    haystack = _haystack(snippet)
    return _check_wagering(fields.wagering_requirement, haystack) + _check_deposit(fields, haystack)
```

- [x] **Step 4: Run the tests and confirm they pass**

Run: `python -m pytest tests/test_verify.py -v`
Expected: 21 passed

- [x] **Step 5: Commit**

```bash
git add scraper/verify.py tests/test_verify.py
git commit -m "feat: cross-check LLM values against source text"
```

---

### Task 7: Static page renderer

**Files:**
- Create: `scraper/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `BonusReport`, `CasinoBonus`, `MinimumDeposit`, `CURRENCY_SYMBOLS`, `format_number`; `config.SOURCE_NAME`
- Produces:
  - `format_wagering(value: float | None) -> str`, `format_deposit(deposit: MinimumDeposit | None) -> str`, `format_timestamp(iso: str) -> str`
  - `render_html(report: BonusReport) -> str`
  - `render(json_path: Path, html_path: Path) -> None` (reads the JSON file, writes the HTML file)

- [x] **Step 1: Write the failing tests `tests/test_render.py`**

```python
import json

from scraper.models import BonusReport
from scraper.render import format_deposit, format_timestamp, format_wagering, render, render_html


def report_dict(**overrides) -> dict:
    data = {
        "generated_at": "2026-10-15T10:00:00Z",
        "source": "https://bojoko.com",
        "model": "gemini-flash-latest",
        "casinos": [
            {
                "casino": "10Bet",
                "welcome_bonus": "100% up to £25",
                "wagering_requirement": 10,
                "minimum_deposit": {"amount": 10, "currency": "GBP"},
                "source_url": "https://bojoko.com/casino/review/10bet/",
                "warnings": [],
            },
            {
                "casino": "Betway",
                "welcome_bonus": "150 free spins",
                "wagering_requirement": 0,
                "minimum_deposit": None,
                "source_url": "https://bojoko.com/casino/review/betway/",
                "warnings": [],
            },
        ],
        "errors": [],
    }
    data.update(overrides)
    return data


def html_for(**overrides) -> str:
    return render_html(BonusReport.model_validate(report_dict(**overrides)))


def test_formatters():
    assert format_wagering(10) == "10x"
    assert format_wagering(0.5) == "0.5x"
    assert format_wagering(0) == "None"
    assert format_wagering(None) == "Not stated"
    assert format_deposit(None) == "Not stated"
    assert format_deposit({"amount": 10, "currency": "GBP"}) == "£10"
    assert format_deposit({"amount": 10, "currency": "XYZ"}) == "10 XYZ"
    assert format_timestamp("2026-10-15T10:00:00Z") == "15 October 2026, 10:00 UTC"


def test_page_lists_every_casino_with_formatted_values():
    html = html_for()
    for text in ["10Bet", "Betway", "100% up to £25", "10x", "None", "£10", "Not stated"]:
        assert text in html
    assert 'href="https://bojoko.com/casino/review/10bet/"' in html
    assert 'rel="nofollow noopener"' in html


def test_page_is_phone_ready_and_has_no_javascript():
    html = html_for()
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    assert 'data-label="Wagering"' in html
    assert "@media (max-width: 600px)" in html
    assert "<script" not in html.lower()


def test_footer_names_source_time_and_model():
    html = html_for()
    assert "15 October 2026, 10:00 UTC" in html
    assert "gemini-flash-latest" in html
    assert "18+" in html


def test_values_are_escaped_once():
    data = report_dict()
    data["casinos"][0]["casino"] = "<script>alert(1)</script>"
    data["casinos"][1]["welcome_bonus"] = "Spins & Cash"
    html = render_html(BonusReport.model_validate(data))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "Spins &amp; Cash" in html
    assert "&amp;amp;" not in html


def test_errors_are_listed_in_a_note():
    html = html_for(errors=[{"casino": "mr-vegas", "source_url": "https://bojoko.com/casino/review/mr-vegas/", "error": "blocked: HTTP 403"}])
    assert "Not available" in html
    assert "mr-vegas" in html


def test_empty_report_shows_message_not_table():
    html = html_for(
        casinos=[],
        errors=[{"casino": "10bet", "source_url": "https://bojoko.com/casino/review/10bet/", "error": "blocked: HTTP 403"}],
    )
    assert "No bonus data is available" in html
    assert "<table" not in html


def test_render_reads_json_file_and_writes_html(tmp_path):
    json_path = tmp_path / "bonuses.json"
    html_path = tmp_path / "out" / "index.html"
    json_path.write_text(json.dumps(report_dict(), ensure_ascii=False), encoding="utf-8")
    render(json_path, html_path)
    assert "10Bet" in html_path.read_text(encoding="utf-8")
```

- [x] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.render'`

- [x] **Step 3: Write `scraper/render.py`**

```python
"""Render docs/index.html from docs/bonuses.json: static HTML, inline CSS, no JavaScript."""
from datetime import datetime
from html import escape
from pathlib import Path
from string import Template

from scraper import config
from scraper.models import CURRENCY_SYMBOLS, BonusReport, CasinoBonus, MinimumDeposit, format_number

PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Casino Welcome Bonuses</title>
<style>
  :root { color-scheme: light dark; --fg: #1a1a1a; --bg: #ffffff; --muted: #5c5c5c; --line: #dddddd; --accent: #0b5cad; }
  @media (prefers-color-scheme: dark) {
    :root { --fg: #ececec; --bg: #121212; --muted: #a8a8a8; --line: #333333; --accent: #7ab7ff; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 24px 16px; font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: var(--fg); background: var(--bg); }
  main { max-width: 960px; margin: 0 auto; }
  h1 { font-size: 1.6rem; line-height: 1.2; margin: 0 0 8px; }
  p { margin: 0 0 12px; }
  .muted, footer { color: var(--muted); }
  a { color: var(--accent); }
  table { width: 100%; border-collapse: collapse; margin: 16px 0; }
  caption { text-align: left; color: var(--muted); padding-bottom: 8px; }
  th, td { text-align: left; vertical-align: top; padding: 10px 12px; border-bottom: 1px solid var(--line); overflow-wrap: anywhere; }
  th { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
  .note { border-left: 4px solid var(--line); padding: 8px 12px; }
  footer { font-size: 0.875rem; margin-top: 24px; }
  @media (max-width: 600px) {
    thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
    table, tbody, tr, td { display: block; width: 100%; }
    tr { border: 1px solid var(--line); border-radius: 8px; padding: 4px 12px; margin-bottom: 12px; }
    td { display: flex; justify-content: space-between; gap: 16px; padding: 8px 0; text-align: right; }
    td:last-child { border-bottom: 0; }
    td::before { content: attr(data-label); font-weight: 600; text-align: left; }
  }
</style>
</head>
<body>
<main>
<h1>Casino Welcome Bonuses</h1>
<p class="muted">Welcome offers for $count casinos, extracted from their review pages on $source_name.</p>
$body
$note
<footer>
<p>Data scraped from $source_name on $generated_at using $model.</p>
<p>18+ · Gamble responsibly · <a href="https://www.begambleaware.org/" rel="nofollow noopener" target="_blank">BeGambleAware.org</a></p>
</footer>
</main>
</body>
</html>
""")

COLUMNS = ["Casino", "Welcome bonus", "Wagering", "Min deposit", "Source"]


def format_wagering(value: float | None) -> str:
    if value is None:
        return "Not stated"
    if value == 0:
        return "None"
    return f"{format_number(value)}x"


def format_deposit(deposit: MinimumDeposit | dict | None) -> str:
    if deposit is None:
        return "Not stated"
    deposit = MinimumDeposit.model_validate(deposit)
    symbol = CURRENCY_SYMBOLS.get(deposit.currency)
    if symbol:
        return f"{symbol}{format_number(deposit.amount)}"
    return f"{format_number(deposit.amount)} {deposit.currency}"


def format_timestamp(iso: str) -> str:
    moment = datetime.fromisoformat(iso.replace("Z", "+00:00"))  # 3.10 does not accept "Z"
    return f"{moment.day} {moment:%B %Y, %H:%M} UTC"


def _row(casino: CasinoBonus) -> str:
    link = (
        f'<a href="{escape(casino.source_url)}" rel="nofollow noopener" target="_blank">'
        f"{escape(config.SOURCE_NAME)}</a>"
    )
    cells = [
        escape(casino.casino),
        escape(casino.welcome_bonus),
        escape(format_wagering(casino.wagering_requirement)),
        escape(format_deposit(casino.minimum_deposit)),
        link,
    ]
    return "<tr>" + "".join(f'<td data-label="{label}">{cell}</td>' for label, cell in zip(COLUMNS, cells)) + "</tr>"


def _table(report: BonusReport) -> str:
    if not report.casinos:
        return '<p class="note">No bonus data is available right now.</p>'
    head = "".join(f'<th scope="col">{label}</th>' for label in COLUMNS)
    rows = "\n".join(_row(casino) for casino in report.casinos)
    return (
        "<table>\n<caption>Welcome bonus, wagering requirement and minimum deposit per casino</caption>\n"
        f"<thead><tr>{head}</tr></thead>\n<tbody>\n{rows}\n</tbody>\n</table>"
    )


def _note(report: BonusReport) -> str:
    if not report.errors:
        return ""
    names = ", ".join(escape(error.casino) for error in report.errors)
    return f'<p class="note">Not available in this run: {names}.</p>'


def render_html(report: BonusReport) -> str:
    return PAGE.substitute(
        count=len(report.casinos),
        source_name=escape(config.SOURCE_NAME),
        body=_table(report),
        note=_note(report),
        generated_at=escape(format_timestamp(report.generated_at)),
        model=escape(report.model),
    )


def render(json_path: Path, html_path: Path) -> None:
    report = BonusReport.model_validate_json(Path(json_path).read_text(encoding="utf-8"))
    html_path = Path(html_path)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_html(report), encoding="utf-8")
```

- [x] **Step 4: Run the tests and confirm they pass**

Run: `python -m pytest tests/test_render.py -v`
Expected: 8 passed

- [x] **Step 5: Commit**

```bash
git add scraper/render.py tests/test_render.py
git commit -m "feat: render phone-friendly static page from JSON"
```

---

### Task 8: Command-line entry point

**Files:**
- Create: `scraper/__main__.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: everything above. `Fetcher`-like objects need only `.fetch_html(url) -> bytes`; client objects need only `.models.generate_content(...)`.
- Produces:
  - `scrape_one(slug: str, url: str, fetcher, client, model: str) -> CasinoBonus`
  - `build_report(slugs: list[str], fetcher, client, model: str, now: datetime) -> BonusReport`
  - `write_report(report: BonusReport, path: Path) -> None`
  - `main(argv: list[str] | None = None) -> int`. Exit codes: 0 all ok; 1 any casino failed, robots.txt unreadable, or `--render-only` without JSON; 2 no API key.

- [x] **Step 1: Write the failing tests `tests/test_main.py`**

```python
import json
from datetime import datetime, timezone

import pytest

import scraper.__main__ as cli
from scraper import config
from scraper.fetch import BlockedError
from tests.fakes import FIXTURES, FakeFetcher, FakeGeminiClient

NOW = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
VALID = '{"welcome_bonus": "100% up to £25", "wagering_requirement": 10, "minimum_deposit": {"amount": 10, "currency": "GBP"}}'


def url(slug: str) -> str:
    return config.REVIEW_URL.format(slug=slug)


def test_one_failure_does_not_stop_the_others():
    fetcher = FakeFetcher({
        url("10bet"): (FIXTURES / "10bet.html").read_bytes(),
        url("mr-vegas"): BlockedError("blocked: HTTP 403"),
    })
    report = cli.build_report(["10bet", "mr-vegas"], fetcher, FakeGeminiClient(VALID), "test-model", NOW)

    assert report.generated_at == "2026-10-15T10:00:00Z"
    assert report.model == "test-model"
    assert report.source == "https://bojoko.com"
    assert [c.casino for c in report.casinos] == ["10Bet"]
    assert report.casinos[0].source_url == url("10bet")
    assert report.casinos[0].warnings == []
    assert [(e.casino, e.error) for e in report.errors] == [("mr-vegas", "blocked: HTTP 403")]


def test_verify_warnings_are_kept_on_the_casino():
    invented = '{"welcome_bonus": "x", "wagering_requirement": 99, "minimum_deposit": null}'
    fetcher = FakeFetcher({url("10bet"): (FIXTURES / "10bet.html").read_bytes()})
    report = cli.build_report(["10bet"], fetcher, FakeGeminiClient(invented), "m", NOW)
    assert report.casinos[0].warnings == ["wagering_requirement 99 not found in source text"]
    assert report.errors == []


def test_write_report_keeps_pound_sign_readable(tmp_path):
    fetcher = FakeFetcher({url("10bet"): (FIXTURES / "10bet.html").read_bytes()})
    report = cli.build_report(["10bet"], fetcher, FakeGeminiClient(VALID), "m", NOW)
    path = tmp_path / "docs" / "bonuses.json"
    cli.write_report(report, path)
    text = path.read_text(encoding="utf-8")
    assert "£25" in text
    assert json.loads(text)["casinos"][0]["wagering_requirement"] == 10


@pytest.fixture
def no_dotenv(monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_api_key_exits_2_before_any_network(monkeypatch, no_dotenv, value, capsys):
    if value is None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("GEMINI_API_KEY", value)
    monkeypatch.setattr(cli.requests, "Session", lambda: pytest.fail("no network expected"))
    assert cli.main([]) == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err


def test_all_casinos_failing_still_writes_outputs(monkeypatch, no_dotenv, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "JSON_PATH", tmp_path / "bonuses.json")
    monkeypatch.setattr(config, "HTML_PATH", tmp_path / "index.html")
    monkeypatch.setattr(cli, "make_client", lambda api_key: FakeGeminiClient(VALID))
    monkeypatch.setattr(cli, "load_robots", lambda base, session: None)
    blocked = {url(slug): BlockedError("blocked: HTTP 403") for slug in config.CASINO_SLUGS}
    monkeypatch.setattr(cli, "Fetcher", lambda session, robots: FakeFetcher(blocked))

    assert cli.main([]) == 1
    data = json.loads((tmp_path / "bonuses.json").read_text(encoding="utf-8"))
    assert data["casinos"] == []
    assert len(data["errors"]) == 3
    assert "No bonus data is available" in (tmp_path / "index.html").read_text(encoding="utf-8")


def test_unreadable_robots_exits_1_and_writes_nothing(monkeypatch, no_dotenv, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "JSON_PATH", tmp_path / "bonuses.json")
    monkeypatch.setattr(cli, "make_client", lambda api_key: FakeGeminiClient(VALID))

    def unreadable(base, session):
        raise cli.RobotsUnavailable("https://bojoko.com/robots.txt returned HTTP 403")

    monkeypatch.setattr(cli, "load_robots", unreadable)
    assert cli.main([]) == 1
    assert not (tmp_path / "bonuses.json").exists()


def test_render_only_needs_no_key_or_network(monkeypatch, no_dotenv, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(cli.requests, "Session", lambda: pytest.fail("no network expected"))
    json_path = tmp_path / "bonuses.json"
    json_path.write_text(json.dumps({
        "generated_at": "2026-10-15T10:00:00Z", "source": "https://bojoko.com", "model": "m",
        "casinos": [], "errors": [],
    }), encoding="utf-8")
    monkeypatch.setattr(config, "JSON_PATH", json_path)
    monkeypatch.setattr(config, "HTML_PATH", tmp_path / "index.html")
    assert cli.main(["--render-only"]) == 0
    assert (tmp_path / "index.html").exists()


def test_render_only_without_json_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "JSON_PATH", tmp_path / "missing.json")
    assert cli.main(["--render-only"]) == 1
    assert "python -m scraper" in capsys.readouterr().err
```

- [x] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.__main__'`

- [x] **Step 3: Write `scraper/__main__.py`**

```python
"""Entry point: `python -m scraper` scrapes, writes docs/bonuses.json and renders docs/index.html.

Exit codes: 0 = all casinos scraped; 1 = one or more failed (see errors[] in the
JSON), robots.txt unreadable, or --render-only with no JSON; 2 = GEMINI_API_KEY missing.
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from scraper import config
from scraper.extract import extract_fields
from scraper.fetch import Fetcher
from scraper.models import BonusReport, CasinoBonus, CasinoError
from scraper.parse import parse_bonus
from scraper.render import render
from scraper.robots import RobotsUnavailable, load_robots
from scraper.verify import verify

log = logging.getLogger("scraper")


def make_client(api_key: str):
    from google import genai  # imported here so --render-only and tests never need the SDK set up

    return genai.Client(api_key=api_key)


def scrape_one(slug: str, url: str, fetcher, client, model: str) -> CasinoBonus:
    snippet = parse_bonus(fetcher.fetch_html(url), slug, url)
    fields = extract_fields(snippet, client, model)
    warnings = verify(fields, snippet)
    for warning in warnings:
        log.warning("%s: %s", slug, warning)
    return CasinoBonus(casino=snippet.casino, source_url=url, warnings=warnings, **fields.model_dump())


def build_report(slugs: list[str], fetcher, client, model: str, now: datetime) -> BonusReport:
    casinos, errors = [], []
    for slug in slugs:
        url = config.REVIEW_URL.format(slug=slug)
        try:
            casinos.append(scrape_one(slug, url, fetcher, client, model))
            log.info("%s: ok", slug)
        except Exception as exc:  # one casino failing must not stop the others
            log.error("%s: %s", slug, exc)
            errors.append(CasinoError(casino=slug, source_url=url, error=str(exc)))
    return BonusReport(
        generated_at=now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source=config.SOURCE_BASE,
        model=model,
        casinos=casinos,
        errors=errors,
    )


def write_report(report: BonusReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scraper", description="Scrape casino welcome bonuses and render the page.")
    parser.add_argument("--render-only", action="store_true", help="re-render the page from the existing JSON (no network, no API key)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.render_only:
        if not config.JSON_PATH.exists():
            print(f"{config.JSON_PATH} does not exist yet. Run `python -m scraper` first.", file=sys.stderr)
            return 1
        render(config.JSON_PATH, config.HTML_PATH)
        log.info("rendered %s", config.HTML_PATH)
        return 0

    load_dotenv(config.ROOT / ".env")
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add a free key "
            "from https://aistudio.google.com/apikey",
            file=sys.stderr,
        )
        return 2

    client = make_client(api_key)
    session = requests.Session()
    try:
        robots = load_robots(config.SOURCE_BASE, session)
    except RobotsUnavailable as exc:
        log.error("%s. Not scraping.", exc)
        return 1

    model = config.gemini_model()
    report = build_report(config.CASINO_SLUGS, Fetcher(session, robots), client, model, datetime.now(timezone.utc))
    write_report(report, config.JSON_PATH)
    render(config.JSON_PATH, config.HTML_PATH)
    log.info("wrote %s and %s: %d ok, %d failed", config.JSON_PATH, config.HTML_PATH, len(report.casinos), len(report.errors))
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 4: Run the tests and confirm they pass**

Run: `python -m pytest tests/test_main.py -v`
Expected: 10 passed

- [x] **Step 5: Run the full suite with no API key in the environment**

Run: `env -u GEMINI_API_KEY python -m pytest -q`
Expected: 83 passed, with no network access needed (counts: models 9, robots 7, fetch 11, parse 8, extract 9, verify 21, render 8, main 10)

- [x] **Step 6: Commit**

```bash
git add scraper/__main__.py tests/test_main.py
git commit -m "feat: single-command entry point with exit codes"
```

---

### Task 9: Live run, README, hand-back

**Files:**
- Create: `README.md`
- Create (generated): `docs/bonuses.json`, `docs/index.html`
- Possibly modify: `scraper/config.py` (only `DEFAULT_GEMINI_MODEL`, and only if Step 2 says so)

**Interfaces:**
- Consumes: the whole package.
- Produces: the committed outputs and README the reviewer checks.

- [x] **Step 1: Make sure `.env` has a real key.** `.env` already exists. The human fills in `GEMINI_API_KEY=` themselves. Check without printing the key: `grep -q '^GEMINI_API_KEY=.\+' .env && echo key-present || echo key-missing`. If it prints `key-missing`, stop and ask the human to add their key to `.env`; don't ask them to paste it into chat. Never commit `.env`, and never print the key.

Run: `git check-ignore .env`
Expected: `.env` (so it is ignored)

- [x] **Step 2: Run the scraper for real**

Run: `python -m scraper; echo "exit=$?"`
Expected: `INFO 10bet: ok`, `INFO mr-vegas: ok`, `INFO betway: ok`, a summary line, `exit=0`.

- If every casino fails with a model error (e.g. `404 ... models/gemini-flash-latest is not found`), the alias doesn't resolve. Set `DEFAULT_GEMINI_MODEL` in `scraper/config.py` to the current stable Gemini Flash model id listed at https://ai.google.dev/gemini-api/docs/models, rerun, and note this in the hand-back report.
- If Gemini rejects `response_schema=BonusFields` (a schema conversion error), change that argument in `scraper/extract.py` to `response_json_schema=BonusFields.model_json_schema()`. Update `test_request_sends_snippet_with_schema_and_zero_temperature` to assert `config.response_json_schema == BonusFields.model_json_schema()`, rerun the tests, and note it in the report.
- If a casino reports `blocked` or `robots.txt disallows`, STOP and report back. Don't work around it.
- A `WARNING ... not found in source text` line doesn't fail the run. Record it in the report.

- [x] **Step 3: Check the output against the source by eye**

Run: `cat docs/bonuses.json`
Expected for each casino, compared with the T&Cs text in its `tests/fixtures/<slug>.html`:
- **10bet:** welcome bonus about "100% up to £25", wagering 10, minimum deposit 10 GBP.
- **mr-vegas:** wagering 10, minimum deposit 10 GBP.
- **betway:** a free-spins offer (about "150 free spins"), wagering 0, minimum deposit 10 GBP.

The live offers may have changed since 2026-10-15. What matters is that each value matches the current source text. List any value you believe is wrong in the report; don't hand-edit the JSON.

- [x] **Step 4: Check the page.** Open `docs/index.html` in a browser at full width and with the device toolbar at 320px. Expected: a table at full width, stacked labelled cards at 320px, no horizontal scrolling.

- [x] **Step 5: Write `README.md`**

~~~~markdown
# Casino Bonus Scraper

Scrapes the welcome bonus for three online casinos from their review pages on
[bojoko.com](https://bojoko.com), uses Google Gemini to turn the free-text bonus
terms into structured fields, writes them to [`docs/bonuses.json`](docs/bonuses.json),
and renders a phone-friendly table at [`docs/index.html`](docs/index.html),
served by GitHub Pages.

Casinos: 10bet, Mr Vegas, Betway.

## Requirements

- Python 3.10 or newer
- A free Gemini API key from https://aistudio.google.com/apikey

## Install

Clone the repository, then from its root:

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then put your key after GEMINI_API_KEY=
```

## Run

```bash
python -m scraper
```

This fetches the three review pages, extracts the bonus fields with Gemini,
writes `docs/bonuses.json`, and regenerates `docs/index.html` from that file.

| Exit code | Meaning |
|---|---|
| 0 | All casinos scraped |
| 1 | One or more casinos failed (details in `errors` in the JSON and in the log), or robots.txt could not be read |
| 2 | `GEMINI_API_KEY` is not set |

Other commands:

- `python -m scraper --render-only` rebuilds the page from the existing JSON,
  with no network and no API key.
- `GEMINI_MODEL=<model id> python -m scraper` uses a different Gemini model.

## Tests

```bash
python -m pytest
```

The tests use saved HTML fixtures and fake HTTP/Gemini clients. They need no
network access and no API key.

## How it works

1. **robots.txt:** fetched once with the scraper's own user-agent, then checked
   before every request. (Python's `RobotFileParser.read()` is not used: it
   sends a default user-agent that bojoko's CDN rejects with 403, which
   robotparser then treats as "disallow everything".)
2. **Fetch:** one request per review page, 1.5 s apart, with an honest
   user-agent. Redirects aren't followed, and a 401/403/429 is reported, never
   retried or worked around.
3. **Parse:** BeautifulSoup isolates the page's bonus card: a small summary
   table plus the significant terms and conditions text.
4. **Extract (LLM):** only that snippet (about 500 characters) is sent to Gemini,
   with a JSON schema and temperature 0. Gemini returns the welcome bonus,
   wagering multiplier and minimum deposit. Values the text doesn't state come
   back as `null` rather than being guessed. The casino name and source URL are
   set by code, not by the model.
5. **Verify:** the wagering multiplier and deposit amount Gemini returned are
   searched for in the source text. A value that cannot be found is kept but
   flagged in `warnings` and the log, so invented numbers get noticed.
6. **Render:** `docs/index.html` is generated from `docs/bonuses.json`. It's a
   static page with no JavaScript. On narrow screens each row becomes a card.

If one casino fails, the others are still written, and the failure is recorded
in `errors`.

## Output

```json
{
  "generated_at": "2026-10-15T10:00:00Z",
  "source": "https://bojoko.com",
  "model": "gemini-flash-latest",
  "casinos": [
    {
      "casino": "10Bet",
      "welcome_bonus": "100% up to £25",
      "wagering_requirement": 10,
      "minimum_deposit": { "amount": 10, "currency": "GBP" },
      "source_url": "https://bojoko.com/casino/review/10bet/",
      "warnings": []
    }
  ],
  "errors": []
}
```

`wagering_requirement` is the multiplier on bonus money: `0` means the terms
explicitly say there is no wagering, and `null` means the terms don't say.

## Hosting

GitHub Pages serves the `docs/` folder (Settings → Pages → Deploy from a branch
→ `main` / `/docs`). To update the live page, run the scraper, commit `docs/`,
and push.

## Source and robots.txt

bojoko.com was chosen because its robots.txt allows `/casino/review/` pages,
the pages are served as plain HTML without JavaScript or bot challenges, and each
review has free-text bonus terms. Several larger comparison sites were ruled out
because they either return 403 to scripted requests or disallow crawling in
robots.txt. The "full terms" links on bojoko (`/modal/...`) and its affiliate
links (`/go/...`) are disallowed by robots.txt and are never requested.

## Known limitations

- The parser depends on bojoko's CSS class names. A markup change shows up as a
  "no bonus card found" error, not as wrong data.
- Values are the UK offers as listed by bojoko (amounts in GBP). They may differ
  from the casino's own site or from other regions.
- The verification step is a heuristic. It catches invented numbers, but not a
  real number attached to the wrong field.
~~~~

If Step 2 changed the default model, update the `"model"` value in the README's JSON example to match.

- [x] **Step 6: Run the full suite again, then commit**

Run: `env -u GEMINI_API_KEY python -m pytest -q`
Expected: all tests pass (83, or the same count after any Step 2 adjustment)

```bash
git add README.md docs/bonuses.json docs/index.html scraper/ tests/
git status --short   # must NOT list .env
git commit -m "feat: live scrape output and README"
```

- [x] **Step 7: Hand back to the reviewer.** Your final message must include:
  1. `git log --oneline`
  2. The output of `python -m pytest -q`
  3. The full log of the live run from Step 2, including the exit code
  4. The contents of `docs/bonuses.json`
  5. Every deviation from this plan and why, including changed test phrases, a model id change or a schema-argument change
  6. Anything you are unsure about
