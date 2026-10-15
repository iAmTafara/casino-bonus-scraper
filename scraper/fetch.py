"""Polite HTTP fetching: robots check first, honest user-agent, a delay, no retries.

A block (401/403/429) is reported, never worked around.
"""
import time

import requests

from scraper import config
from scraper.robots import is_allowed


class FetchError(Exception):
    """The page could not be fetched."""


class DisallowedByRobots(FetchError):
    """robots.txt does not allow this URL."""


class BlockedError(FetchError):
    """The site refused us. We stop rather than try to get around it."""


class Fetcher:
    def __init__(self, session, robots, delay: float = config.REQUEST_DELAY_SECONDS, sleep=time.sleep):
        self._session = session
        self._robots = robots
        self._delay = delay
        self._sleep = sleep
        self._has_fetched = False

    def fetch_html(self, url: str) -> bytes:
        if not is_allowed(self._robots, url):
            raise DisallowedByRobots(f"robots.txt disallows {url}")
        if self._has_fetched:
            self._sleep(self._delay)
        self._has_fetched = True

        try:
            response = self._session.get(
                url,
                headers={"User-Agent": config.USER_AGENT},
                timeout=config.REQUEST_TIMEOUT_SECONDS,
                allow_redirects=False,  # a redirect could lead to a path robots.txt disallows
            )
        except requests.RequestException as exc:
            raise FetchError(f"request failed: {exc}") from exc

        if response.status_code in (401, 403, 429):
            raise BlockedError(f"blocked: HTTP {response.status_code}")
        if not 200 <= response.status_code < 300:
            raise FetchError(f"HTTP {response.status_code} for {url}")
        return response.content
