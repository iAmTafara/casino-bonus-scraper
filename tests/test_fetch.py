from urllib.robotparser import RobotFileParser

import pytest
import requests

from scraper import config
from scraper.fetch import BlockedError, DisallowedByRobots, Fetcher, FetchError
from tests.fakes import FakeResponse, FakeSession

URL = "https://bojoko.com/casino/review/10bet/"


def robots(*lines: str) -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse(list(lines))
    return parser


ALLOW_ALL = robots()


def fetcher(session, parser=ALLOW_ALL, sleeps=None):
    return Fetcher(session, parser, delay=1.5, sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_disallowed_url_raises_without_making_a_request():
    session = FakeSession({})
    with pytest.raises(DisallowedByRobots):
        fetcher(session, robots("User-agent: *", "Disallow: /modal/")).fetch_html("https://bojoko.com/modal/x/")
    assert session.requests == []


def test_returns_raw_bytes():
    body = "<p>Min £10</p>".encode("utf-8")
    session = FakeSession({URL: FakeResponse(200, content=body)})
    assert fetcher(session).fetch_html(URL) == body


def test_sends_user_agent_timeout_and_does_not_follow_redirects():
    session = FakeSession({URL: FakeResponse(200, "ok")})
    fetcher(session).fetch_html(URL)
    request = session.requests[0]
    assert request["headers"]["User-Agent"] == config.USER_AGENT
    assert request["timeout"] == config.REQUEST_TIMEOUT_SECONDS
    assert request["allow_redirects"] is False


@pytest.mark.parametrize("status", [401, 403, 429])
def test_block_statuses_raise_blocked_error(status):
    with pytest.raises(BlockedError, match=f"blocked: HTTP {status}"):
        fetcher(FakeSession({URL: FakeResponse(status)})).fetch_html(URL)


@pytest.mark.parametrize("status", [301, 404, 500])
def test_other_non_2xx_raise_fetch_error(status):
    with pytest.raises(FetchError, match=f"HTTP {status}") as info:
        fetcher(FakeSession({URL: FakeResponse(status)})).fetch_html(URL)
    assert not isinstance(info.value, BlockedError)


def test_network_error_raises_fetch_error():
    with pytest.raises(FetchError, match="boom"):
        fetcher(FakeSession({URL: requests.ConnectionError("boom")})).fetch_html(URL)


def test_sleeps_between_requests_but_not_before_the_first():
    other = "https://bojoko.com/casino/review/betway/"
    sleeps = []
    f = fetcher(FakeSession({URL: FakeResponse(200, "a"), other: FakeResponse(200, "b")}), sleeps=sleeps)
    f.fetch_html(URL)
    assert sleeps == []
    f.fetch_html(other)
    assert sleeps == [1.5]
