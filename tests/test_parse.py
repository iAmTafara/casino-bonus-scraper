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
