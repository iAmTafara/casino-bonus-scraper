"""Test doubles for HTTP and Gemini. Tests never touch the network."""
from pathlib import Path
from types import SimpleNamespace

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, status_code: int, text: str = "", content: bytes | None = None):
        self.status_code = status_code
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")
        self.headers = {}


class FakeSession:
    """Returns canned responses keyed by URL and records every request made."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append({"url": url, **kwargs})
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


class FakeModels:
    def __init__(self, text, error):
        self.text = text
        self.error = error
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.error is not None:
            raise self.error
        return SimpleNamespace(text=self.text)


class FakeGeminiClient:
    """Mimics genai.Client: client.models.generate_content(...) returns an object with .text."""

    def __init__(self, text: str | None = None, error: Exception | None = None):
        self.models = FakeModels(text, error)


class FakeFetcher:
    """Mimics scraper.fetch.Fetcher: maps URL -> bytes, or an Exception to raise."""

    def __init__(self, pages: dict):
        self.pages = pages

    def fetch_html(self, url: str) -> bytes:
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return page
