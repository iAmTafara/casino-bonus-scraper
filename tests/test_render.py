import json

from scraper.models import BonusReport
from scraper.render import format_deposit, format_timestamp, format_wagering, render, render_html


def report_dict(**overrides) -> dict:
    data = {
        "generated_at": "2026-10-15T10:00:00Z",
        "source": "https://bojoko.com",
        "model": "gemini-flash-latest",
        "casinos": [
            {
                "casino": "10Bet",
                "welcome_bonus": "100% up to £25",
                "wagering_requirement": 10,
                "minimum_deposit": {"amount": 10, "currency": "GBP"},
                "source_url": "https://bojoko.com/casino/review/10bet/",
                "warnings": [],
            },
            {
                "casino": "Betway",
                "welcome_bonus": "150 free spins",
                "wagering_requirement": 0,
                "minimum_deposit": None,
                "source_url": "https://bojoko.com/casino/review/betway/",
                "warnings": [],
            },
        ],
        "errors": [],
    }
    data.update(overrides)
    return data


def html_for(**overrides) -> str:
    return render_html(BonusReport.model_validate(report_dict(**overrides)))


def test_formatters():
    assert format_wagering(10) == "10x"
    assert format_wagering(0.5) == "0.5x"
    assert format_wagering(0) == "None"
    assert format_wagering(None) == "Not stated"
    assert format_deposit(None) == "Not stated"
    assert format_deposit({"amount": 10, "currency": "GBP"}) == "£10"
    assert format_deposit({"amount": 10, "currency": "XYZ"}) == "10 XYZ"
    assert format_timestamp("2026-10-15T10:00:00Z") == "15 October 2026, 10:00 UTC"


def test_page_lists_every_casino_with_formatted_values():
    html = html_for()
    for text in ["10Bet", "Betway", "100% up to £25", "10x", "None", "£10", "Not stated"]:
        assert text in html
    assert 'href="https://bojoko.com/casino/review/10bet/"' in html
    assert 'rel="nofollow noopener"' in html


def test_page_is_phone_ready_and_has_no_javascript():
    html = html_for()
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    assert 'data-label="Wagering"' in html
    assert "@media (max-width: 600px)" in html
    assert "<script" not in html.lower()


def test_footer_names_source_time_and_model():
    html = html_for()
    assert "15 October 2026, 10:00 UTC" in html
    assert "gemini-flash-latest" in html
    assert "18+" in html


def test_values_are_escaped_once():
    data = report_dict()
    data["casinos"][0]["casino"] = "<script>alert(1)</script>"
    data["casinos"][1]["welcome_bonus"] = "Spins & Cash"
    html = render_html(BonusReport.model_validate(data))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "Spins &amp; Cash" in html
    assert "&amp;amp;" not in html


def test_errors_are_listed_in_a_note():
    html = html_for(errors=[{"casino": "mr-vegas", "source_url": "https://bojoko.com/casino/review/mr-vegas/", "error": "blocked: HTTP 403"}])
    assert "Not available" in html
    assert "mr-vegas" in html


def test_empty_report_shows_message_not_table():
    html = html_for(
        casinos=[],
        errors=[{"casino": "10bet", "source_url": "https://bojoko.com/casino/review/10bet/", "error": "blocked: HTTP 403"}],
    )
    assert "No bonus data is available" in html
    assert "<table" not in html


def test_render_reads_json_file_and_writes_html(tmp_path):
    json_path = tmp_path / "bonuses.json"
    html_path = tmp_path / "out" / "index.html"
    json_path.write_text(json.dumps(report_dict(), ensure_ascii=False), encoding="utf-8")
    render(json_path, html_path)
    assert "10Bet" in html_path.read_text(encoding="utf-8")
