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
