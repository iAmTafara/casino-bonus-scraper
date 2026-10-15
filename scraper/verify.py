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
