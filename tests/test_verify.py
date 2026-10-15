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
