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
