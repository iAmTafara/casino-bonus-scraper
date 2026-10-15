# Casino Bonus Scraper — Design

Date: 2026-10-15
Status: Approved in brainstorming; awaiting written-spec review

## 1. Context and goal

Screening task for a Web Developer role (3-hour cap). Pull welcome-bonus data for
3 online casinos from one public source, use a language model to turn free-text
bonus terms into structured fields, write them to JSON, and publish a
phone-readable table generated from that JSON on a free host.

Reviewers value: production-minded, not over-engineered, clean code, a README
that lets them install and run in minutes.

Workflow: this spec → implementation plan → Gemini implements → Claude reviews
and finalises.

### Hard requirements from the brief

- One source; 3 casinos; fields per casino: welcome bonus, wagering requirement
  (multiplier), minimum deposit, source URL.
- A language model performs at least one step (free-text terms → fields).
- Runs with a single command.
- Respects robots.txt; never bypasses logins, CAPTCHAs or blocks.
- No hand-typed data.
- Table generated from the JSON file, hosted free, readable on a phone.
- Repo contains script, JSON output, README (install + run).

### Out of scope for the implementation

The written production part, the "five lines on AI" and the time log are
written by the candidate. The implementer does not write them.

## 2. Decisions

| Topic | Decision | Reason |
|---|---|---|
| Language | Python 3.10+ (developed on 3.13) | stdlib robots parser, standard scraping stack |
| LLM | Gemini via the `google-genai` SDK | Free tier, so reviewers can run it; native `response_schema` |
| Source | bojoko.com casino review pages | robots.txt allows `/casino/review/`; plain HTTP returns 200; has a structured bonus card plus free-text T&Cs |
| Casinos | `10bet`, `mr-vegas`, `betway` | Covers three shapes: deposit match, labelled terms, free-spins with no wagering |
| Extraction | Scoped HTML → LLM → schema validation → numeric cross-check | Small prompt, low hallucination surface, debuggable |
| Page | Static HTML rendered from the JSON at build time, no JS | Simplest; works without JS |
| Hosting | GitHub Pages from `/docs` on `main` | Free, no build step |
| Repo | New git repo at `casino-bonus-scraper/` (subfolder) | Keeps the recruiter email and brief PDF out of the repo |

### Source research findings (verified 2026-10-15)

- Rejected: casino.guru, askgamblers, casinomeister, bonus.com, oddschecker
  (403 bot block); lcb.org, casino.org, covers, casinobonusesnow,
  nodepositrewards (robots.txt disallows). gamblingsites.com is allowed but its
  wagering and min-deposit data appear only in review prose.
- **robots.txt gotcha:** `urllib.robotparser.RobotFileParser.read()` fetches
  with the default `Python-urllib` user-agent. bojoko (Cloudflare) answers that
  with 403, and robotparser treats a 403 as *disallow all*. The scraper MUST
  fetch robots.txt itself with its own user-agent and call
  `RobotFileParser.parse(lines)`.
- bojoko robots.txt disallows `/modal/`. The "Full terms" links on review pages
  open `/modal/casino/terms-and-conditions/...`. These MUST NOT be fetched.

## 3. Repository layout

```
casino-bonus-scraper/
├── scraper/
│   ├── __init__.py
│   ├── __main__.py    # CLI entry: `python -m scraper [--render-only]`
│   ├── config.py      # constants + env overrides
│   ├── robots.py      # robots.txt fetch (own UA) + can_fetch
│   ├── fetch.py       # polite HTTP GET
│   ├── parse.py       # HTML → BonusSnippet
│   ├── extract.py     # BonusSnippet → BonusFields via Gemini
│   ├── verify.py      # cross-check LLM numbers against snippet text
│   ├── models.py      # Pydantic models
│   └── render.py      # bonuses.json → index.html
├── docs/              # GitHub Pages root
│   ├── bonuses.json   # committed scraper output
│   └── index.html     # committed generated page
├── tests/
│   ├── fixtures/      # saved HTML for the 3 casinos, a no-card page, robots.txt
│   └── test_*.py
├── specs/             # this spec and the implementation plan (not published)
├── requirements.txt   # requests, beautifulsoup4, google-genai, pydantic, python-dotenv, pytest
├── .env.example       # GEMINI_API_KEY=
├── .gitignore         # .env, .venv/, __pycache__/, .pytest_cache/
└── README.md
```

## 4. Components

Each module has one job and can be tested on its own.

### config.py
- `SOURCE_BASE = "https://bojoko.com"`
- `CASINO_SLUGS = ["10bet", "mr-vegas", "betway"]`
- `REVIEW_URL = SOURCE_BASE + "/casino/review/{slug}/"`
- `USER_AGENT = "casino-bonus-scraper/1.0 (screening task; respects robots.txt)"`
- `REQUEST_DELAY_SECONDS = 1.5`, `REQUEST_TIMEOUT_SECONDS = 20`
- `GEMINI_MODEL`: env `GEMINI_MODEL`, default `"gemini-flash-latest"`. The
  implementer must confirm during the live smoke run that the default resolves.
  If it doesn't, set the default to the current stable Flash model id and note
  it in the README.
- Output paths: `docs/bonuses.json`, `docs/index.html` (resolved relative to
  the repo root, not the current working directory).

### robots.py
- `load_robots(base_url, session) -> RobotFileParser`: GET `/robots.txt` with
  `USER_AGENT`.
  - 200: `rp.parse(text.splitlines())`.
  - 404: allow all, matching the robots convention.
  - Any other status or a network error: raise `RobotsUnavailable`. We do not
    scrape when robots.txt can't be read.
- `is_allowed(rp, url) -> bool` uses `USER_AGENT`.

### fetch.py
- `fetch_html(url, rp, session) -> str`:
  - Raises `DisallowedByRobots` if not allowed.
  - Sleeps `REQUEST_DELAY_SECONDS` between requests (not before the first).
  - GETs with `USER_AGENT` and the timeout.
  - Raises `BlockedError` on 401, 403 or 429, and `FetchError` on any other
    non-2xx or network error.
- No retries, no header spoofing, no proxies.

### parse.py
- `parse_bonus(html, slug) -> BonusSnippet`, using BeautifulSoup
  (`html.parser`):
  - **Card:** the first element matching
    `.card-toplist-row__content--bonus-card`. If none, raise `BonusCardNotFound`.
  - **Info rows:** inside the card, each `tr.card-toplist-row__info-row` gives
    `th.card-toplist-row__info-name` text → `td.card-toplist-row__info-value`
    text, whitespace-normalised, as `dict[str, str]`. It may be empty; some
    pages have no rows.
  - **Terms:** the first `small.card-toplist-row__footer--bonus-card` on the
    page, read with `get_text(" ", strip=True)` and whitespace-normalised. In
    the bojoko markup this is a later sibling of the card, not inside it. If
    missing, raise `BonusCardNotFound`.
  - **Casino name:** prefer the `data-ga-label` attribute of the first
    `.card-toplist-row__cta-wrapper--bonus-card a[data-ga-label]` (a sibling
    of the card, e.g. `10Bet`), else the slug. Do not use `<h1>`: it contains
    extra text such as "Casino Review 2026".
  - Verified markup notes (2026-10-15):
    - The class string `card-toplist-row__content--bonus-card` also appears
      in an inline `<style>` block. That's harmless with CSS selectors, but
      it means string or regex searches on raw HTML give false matches. Use
      BeautifulSoup only.
    - The CTA's `href` is `/go/...`, which robots.txt disallows. Read the
      attribute only; never request it.
    - Info rows seen include "1st deposit bonus" (`100%/£25`), "Minimum
      deposit for bonus" (`£10`), "Wagering requirements (bonus money)"
      (`10x (B)`, or `0x` for betway) and "Wagering requirements (bonus
      spins)".

### models.py (Pydantic v2)
```python
class MinimumDeposit(BaseModel):
    amount: float
    currency: str          # ISO 4217, e.g. "GBP"

class BonusFields(BaseModel):          # exactly what the LLM returns
    welcome_bonus: str                 # short, e.g. "100% up to £25", "150 free spins"
    wagering_requirement: float | None # 0 = explicitly no wagering; None = not stated
    minimum_deposit: MinimumDeposit | None

class BonusSnippet(BaseModel):
    slug: str
    casino: str
    source_url: str
    info_rows: dict[str, str]
    terms_text: str

class CasinoBonus(BonusFields):
    casino: str
    source_url: str
    warnings: list[str] = []

class CasinoError(BaseModel):
    casino: str            # the slug
    source_url: str
    error: str

class BonusReport(BaseModel):
    generated_at: str      # ISO 8601 UTC, "Z" suffix
    source: str
    model: str
    casinos: list[CasinoBonus]
    errors: list[CasinoError]
```
`casino` and `source_url` are always set by code, never by the LLM.

### extract.py
- `extract_fields(snippet, client, model) -> BonusFields`. `client` is injected
  (a real `genai.Client` or a test fake).
- Call `client.models.generate_content` with `temperature=0`,
  `response_mime_type="application/json"`, `response_schema=BonusFields`.
- Parse `response.text` with `BonusFields.model_validate_json`. Invalid JSON or
  a schema error raises `ExtractionError`.
- Prompt (system and user content), stating these rules explicitly:
  - Use only facts stated in the provided text. Never guess or use outside
    knowledge.
  - `welcome_bonus`: a short summary in the style "100% up to £25" or
    "150 free spins". Combine match and spins if both exist, e.g.
    "100% up to £100 + 50 free spins".
  - `wagering_requirement`: the multiplier as a number. If several are given,
    use the one on bonus money. Return 0 only if the text explicitly says no
    wagering on the welcome offer. Return null if not stated.
  - `minimum_deposit`: the minimum deposit or qualifying stake for the welcome
    offer, with an ISO currency code (£ → GBP, € → EUR, $ → USD). Null if not
    stated.
  - The input is the info-table rows as `Name: Value` lines, followed by the
    T&Cs text.
- A missing `GEMINI_API_KEY` is checked in `__main__` before any network
  request. The script prints a clear message and exits with code 2.

### verify.py
- `verify(fields, snippet) -> list[str]` (warnings). The haystack is
  `terms_text` plus info-row values, lowercased.
  - **Wagering:**
    - If the value is null, no check.
    - If 0: warn unless the haystack contains "no wagering", "wager-free",
      "wagering free" or "0x".
    - Otherwise: warn unless the number (formatted without a trailing `.0`)
      appears immediately before an "x" (allowing optional whitespace), using
      regex `(?<![\d.])N\s*x`.
  - **Min deposit:** if not null, warn unless the amount (no trailing `.0`)
    appears in the haystack directly after the currency symbol for its code
    (GBP £, EUR €, USD $) or before the code itself.
- Warnings are human-readable, e.g.
  `"wagering_requirement 35 not found in source text"`.

### render.py
- `render(json_path, html_path)` reads the JSON file (not in-memory data),
  validates it as `BonusReport`, and writes a single self-contained HTML file.
- Every interpolated value goes through `html.escape`.
- **Page content:**
  - `<meta name="viewport" content="width=device-width, initial-scale=1">`
  - Title "Casino Welcome Bonuses".
  - A `<table>` with a `<caption>` and the columns Casino · Welcome bonus ·
    Wagering · Min deposit · Source.
    - **Wagering:** `10x`; `0` → "None"; null → "Not stated".
    - **Min deposit:** currency symbol + amount (`£10`); unknown currency →
      `10 XYZ`; null → "Not stated".
    - **Source:** a link labelled "bojoko.com", with
      `rel="nofollow noopener"` and `target="_blank"`.
  - Footer: "Data scraped from bojoko.com on <generated_at, human-readable UTC>
    using <model>." plus "18+ · Gamble responsibly · BeGambleAware.org".
  - If `errors` is not empty, a short "Not available" note listing the failed
    casinos.
- **CSS (inline):**
  - System font stack and readable contrast.
  - At `max-width: 600px`, rows become stacked cards: `thead` is visually
    hidden, and each `td` shows `attr(data-label)` as a label.
  - No horizontal scroll at 320px.
  - No JavaScript.

### __main__.py
- `python -m scraper`:
  1. Load `.env` (python-dotenv). Exit 2 if `GEMINI_API_KEY` is missing.
  2. Create a `requests.Session` and load robots.
     `RobotsUnavailable` → exit 1 with a message, writing nothing.
  3. For each slug run fetch → parse → extract → verify. Any exception from
     those steps becomes a `CasinoError` and processing continues with the
     next casino.
  4. Build a `BonusReport` and write `docs/bonuses.json` (indent 2, UTF-8,
     `ensure_ascii=False`).
  5. Call `render`.
  6. Log a one-line summary per casino to stderr. Exit 1 if `errors` is not
     empty, else 0.
- `python -m scraper --render-only` runs only `render` against the existing
  JSON. It needs no API key and makes no network calls.
- Logging: the stdlib `logging` module at INFO, to stderr.

## 5. Error handling summary

| Situation | Behaviour |
|---|---|
| No API key | Exit 2 before any network call |
| robots.txt unreadable (non-200/404, network) | Exit 1, nothing written |
| Page disallowed by robots | `CasinoError`, continue |
| 401/403/429 | `CasinoError("blocked: HTTP 403")`, continue, no retry |
| Bonus card missing | `CasinoError`, continue |
| LLM error / invalid JSON / schema mismatch | `CasinoError`, continue |
| Verify mismatch | Kept in `casinos` with `warnings`, logged, does not fail the run |
| Any `errors` | JSON and page still written; exit 1 |

## 6. Testing

pytest. No network or LLM calls in tests.

- **Fixtures:**
  - Saved review HTML for `10bet`, `mr-vegas` and `betway`, captured once
    with the scraper's own fetch so robots rules apply.
  - A small no-card HTML file.
  - A copy of bojoko's robots.txt.
- **test_robots:** `/casino/review/10bet/` is allowed; `/modal/casino/x/` is
  disallowed; 404 → allow all; 403 → `RobotsUnavailable` (use a fake session).
- **test_fetch:** a disallowed URL raises before any HTTP call; 403 →
  `BlockedError` (fake session).
- **test_parse:** for each fixture, the card is found, `terms_text` contains a
  known phrase (10bet: "Wager bonus 10x"; mr-vegas: "Wagering requirement:
  10x"; betway: "No wagering requirements"), and `casino` is not empty. The
  no-card fixture raises `BonusCardNotFound`.
- **test_extract:** a fake client returning valid JSON gives `BonusFields`;
  invalid JSON or a missing field raises `ExtractionError`; the prompt sent
  contains the terms text.
- **test_verify:**
  - 10 with "Wager bonus 10x" → no warning.
  - 35 with the same text → a warning.
  - 0 with "No wagering requirements" → no warning.
  - Min deposit 10 GBP with "Min £10" → no warning; 20 GBP → a warning.
- **test_render:**
  - A sample JSON gives HTML that contains every casino name.
  - `<script>` in a value is escaped.
  - Null values show "Not stated" and 0 wagering shows "None".
  - The viewport meta is present.
  - Errors appear in the note.

## 7. Acceptance criteria

1. `pip install -r requirements.txt`, then `pytest` passes.
2. With a valid key, `python -m scraper` exits 0 and writes `docs/bonuses.json`
   with 3 casinos and `docs/index.html`.
3. The values in `bonuses.json` match what is visible on the three bojoko review
   pages (checked manually at review time).
4. `python -m scraper --render-only` works without a key or network.
5. The page has no horizontal scroll at 320px width and is readable as stacked
   cards on a phone.
6. No request goes to a robots-disallowed path, including `/modal/`.
7. The README covers prerequisites, venv setup, installing, `.env` /
   `GEMINI_API_KEY` (with a link to get a free key), running, `--render-only`,
   running tests, how GitHub Pages serves `/docs`, the source choice and its
   robots compliance, and known limitations (GBP values; bojoko markup
   dependency; values are the UK offers shown on bojoko).
8. `docs/bonuses.json` and `docs/index.html` from a real run are committed.

## 8. Known limitations (to state in README)

- Coupled to bojoko's CSS class names. A markup change surfaces as
  `BonusCardNotFound` errors, not wrong data.
- Values are the UK offers as listed by bojoko, which may differ from the
  casino's own site or other regions.
- `verify` is a heuristic: it catches invented numbers but not a correct number
  attributed to the wrong field.
