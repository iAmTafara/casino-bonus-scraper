import pytest
import requests

from scraper import config
from scraper.robots import RobotsUnavailable, is_allowed, load_robots
from tests.fakes import FIXTURES, FakeResponse, FakeSession

ROBOTS_URL = "https://bojoko.com/robots.txt"
ROBOTS_TXT = (FIXTURES / "robots.txt").read_text(encoding="utf-8")


def test_review_pages_allowed_but_modal_and_go_disallowed():
    parser = load_robots("https://bojoko.com", FakeSession({ROBOTS_URL: FakeResponse(200, ROBOTS_TXT)}))
    assert is_allowed(parser, "https://bojoko.com/casino/review/10bet/")
    assert not is_allowed(parser, "https://bojoko.com/modal/casino/terms-and-conditions/1627/")
    assert not is_allowed(parser, "https://bojoko.com/go/10bet-casino/")


def test_robots_fetched_with_our_user_agent():
    session = FakeSession({ROBOTS_URL: FakeResponse(200, ROBOTS_TXT)})
    load_robots("https://bojoko.com/", session)
    assert session.requests[0]["url"] == ROBOTS_URL
    assert session.requests[0]["headers"]["User-Agent"] == config.USER_AGENT


def test_missing_robots_allows_everything():
    parser = load_robots("https://bojoko.com", FakeSession({ROBOTS_URL: FakeResponse(404)}))
    assert is_allowed(parser, "https://bojoko.com/anything/")


@pytest.mark.parametrize("status", [401, 403, 500])
def test_unreadable_robots_raises(status):
    with pytest.raises(RobotsUnavailable, match=str(status)):
        load_robots("https://bojoko.com", FakeSession({ROBOTS_URL: FakeResponse(status)}))


def test_network_error_raises():
    session = FakeSession({ROBOTS_URL: requests.ConnectionError("boom")})
    with pytest.raises(RobotsUnavailable, match="boom"):
        load_robots("https://bojoko.com", session)
