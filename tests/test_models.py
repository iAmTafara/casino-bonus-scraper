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
