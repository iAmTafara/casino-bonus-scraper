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
