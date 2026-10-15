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
