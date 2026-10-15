import json
from datetime import datetime, timezone

import pytest

import scraper.__main__ as cli
from scraper import config
from scraper.fetch import BlockedError
from tests.fakes import FIXTURES, FakeFetcher, FakeGeminiClient

NOW = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
VALID = '{"welcome_bonus": "100% up to £25", "wagering_requirement": 10, "minimum_deposit": {"amount": 10, "currency": "GBP"}}'


def url(slug: str) -> str:
    return config.REVIEW_URL.format(slug=slug)


def test_one_failure_does_not_stop_the_others():
    fetcher = FakeFetcher({
        url("10bet"): (FIXTURES / "10bet.html").read_bytes(),
        url("mr-vegas"): BlockedError("blocked: HTTP 403"),
    })
    report = cli.build_report(["10bet", "mr-vegas"], fetcher, FakeGeminiClient(VALID), "test-model", NOW)

    assert report.generated_at == "2026-10-15T10:00:00Z"
    assert report.model == "test-model"
    assert report.source == "https://bojoko.com"
    assert [c.casino for c in report.casinos] == ["10Bet"]
    assert report.casinos[0].source_url == url("10bet")
    assert report.casinos[0].warnings == []
    assert [(e.casino, e.error) for e in report.errors] == [("mr-vegas", "blocked: HTTP 403")]


def test_verify_warnings_are_kept_on_the_casino():
    invented = '{"welcome_bonus": "x", "wagering_requirement": 99, "minimum_deposit": null}'
    fetcher = FakeFetcher({url("10bet"): (FIXTURES / "10bet.html").read_bytes()})
    report = cli.build_report(["10bet"], fetcher, FakeGeminiClient(invented), "m", NOW)
    assert report.casinos[0].warnings == ["wagering_requirement 99 not found in source text"]
    assert report.errors == []


def test_write_report_keeps_pound_sign_readable(tmp_path):
    fetcher = FakeFetcher({url("10bet"): (FIXTURES / "10bet.html").read_bytes()})
    report = cli.build_report(["10bet"], fetcher, FakeGeminiClient(VALID), "m", NOW)
    path = tmp_path / "docs" / "bonuses.json"
    cli.write_report(report, path)
    text = path.read_text(encoding="utf-8")
    assert "£25" in text
    assert json.loads(text)["casinos"][0]["wagering_requirement"] == 10


@pytest.fixture
def no_dotenv(monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_api_key_exits_2_before_any_network(monkeypatch, no_dotenv, value, capsys):
    if value is None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("GEMINI_API_KEY", value)
    monkeypatch.setattr(cli.requests, "Session", lambda: pytest.fail("no network expected"))
    assert cli.main([]) == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err


def test_all_casinos_failing_still_writes_outputs(monkeypatch, no_dotenv, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "JSON_PATH", tmp_path / "bonuses.json")
    monkeypatch.setattr(config, "HTML_PATH", tmp_path / "index.html")
    monkeypatch.setattr(cli, "make_client", lambda api_key: FakeGeminiClient(VALID))
    monkeypatch.setattr(cli, "load_robots", lambda base, session: None)
    blocked = {url(slug): BlockedError("blocked: HTTP 403") for slug in config.CASINO_SLUGS}
    monkeypatch.setattr(cli, "Fetcher", lambda session, robots: FakeFetcher(blocked))

    assert cli.main([]) == 1
    data = json.loads((tmp_path / "bonuses.json").read_text(encoding="utf-8"))
    assert data["casinos"] == []
    assert len(data["errors"]) == 3
    assert "No bonus data is available" in (tmp_path / "index.html").read_text(encoding="utf-8")


def test_unreadable_robots_exits_1_and_writes_nothing(monkeypatch, no_dotenv, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "JSON_PATH", tmp_path / "bonuses.json")
    monkeypatch.setattr(cli, "make_client", lambda api_key: FakeGeminiClient(VALID))

    def unreadable(base, session):
        raise cli.RobotsUnavailable("https://bojoko.com/robots.txt returned HTTP 403")

    monkeypatch.setattr(cli, "load_robots", unreadable)
    assert cli.main([]) == 1
    assert not (tmp_path / "bonuses.json").exists()


def test_render_only_needs_no_key_or_network(monkeypatch, no_dotenv, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(cli.requests, "Session", lambda: pytest.fail("no network expected"))
    json_path = tmp_path / "bonuses.json"
    json_path.write_text(json.dumps({
        "generated_at": "2026-10-15T10:00:00Z", "source": "https://bojoko.com", "model": "m",
        "casinos": [], "errors": [],
    }), encoding="utf-8")
    monkeypatch.setattr(config, "JSON_PATH", json_path)
    monkeypatch.setattr(config, "HTML_PATH", tmp_path / "index.html")
    assert cli.main(["--render-only"]) == 0
    assert (tmp_path / "index.html").exists()


def test_render_only_without_json_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "JSON_PATH", tmp_path / "missing.json")
    assert cli.main(["--render-only"]) == 1
    assert "python -m scraper" in capsys.readouterr().err
