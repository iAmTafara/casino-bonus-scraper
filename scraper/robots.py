"""robots.txt handling.

RobotFileParser.read() fetches with Python's default user-agent, which bojoko's
CDN answers with 403, and robotparser treats a 403 as "disallow everything".
So we fetch the file ourselves, with our own user-agent, and only use
robotparser to parse it.
"""
from urllib.robotparser import RobotFileParser

import requests

from scraper import config


class RobotsUnavailable(Exception):
    """robots.txt could not be read, so we must not scrape."""


def load_robots(base_url: str, session) -> RobotFileParser:
    url = base_url.rstrip("/") + "/robots.txt"
    try:
        response = session.get(
            url,
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise RobotsUnavailable(f"could not fetch {url}: {exc}") from exc

    parser = RobotFileParser(url)
    if response.status_code == 200:
        parser.parse(response.text.splitlines())
    elif response.status_code == 404:
        parser.parse([])  # no robots.txt means everything is allowed
    else:
        raise RobotsUnavailable(f"{url} returned HTTP {response.status_code}")
    return parser


def is_allowed(parser: RobotFileParser, url: str) -> bool:
    return parser.can_fetch(config.USER_AGENT, url)
