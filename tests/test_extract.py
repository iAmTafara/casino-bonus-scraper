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
