"""Turn a bonus snippet's free-text terms into structured fields with Gemini."""
from google.genai import types
from pydantic import ValidationError

from scraper.models import BonusFields, BonusSnippet

SYSTEM_PROMPT = """You extract casino welcome-bonus terms into JSON.
Rules:
- Use only facts stated in the provided text. Never guess or use outside knowledge.
- welcome_bonus: a short summary such as "100% up to £25" or "150 free spins". If the offer has both a deposit match and spins, combine them, e.g. "100% up to £100 + 50 free spins".
- wagering_requirement: the wagering multiplier as a number (35 for "35x"). If several are given, use the one on bonus money. Return 0 only if the text explicitly says the welcome offer has no wagering. Return null if it is not stated.
- minimum_deposit: the minimum deposit or qualifying stake for the welcome offer, as an amount and an ISO 4217 currency code (£ = GBP, € = EUR, $ = USD). Return null if it is not stated."""


class ExtractionError(Exception):
    """The LLM call failed or returned data that does not fit the schema."""


def build_prompt(snippet: BonusSnippet) -> str:
    rows = "\n".join(f"{name}: {value}" for name, value in snippet.info_rows.items())
    return (
        f"Casino: {snippet.casino}\n\n"
        f"Offer summary table:\n{rows or '(none)'}\n\n"
        f"Terms and conditions:\n{snippet.terms_text}"
    )


def extract_fields(snippet: BonusSnippet, client, model: str) -> BonusFields:
    try:
        response = client.models.generate_content(
            model=model,
            contents=build_prompt(snippet),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0,
                response_mime_type="application/json",
                response_schema=BonusFields,
            ),
        )
    except Exception as exc:  # the SDK raises several error types; any of them fails only this casino
        raise ExtractionError(f"Gemini request failed: {exc}") from exc

    try:
        return BonusFields.model_validate_json(response.text or "")
    except ValidationError as exc:
        raise ExtractionError(f"Gemini returned invalid data: {exc}") from exc
