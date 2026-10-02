import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


class FakeHttp:
    """Stands in for HttpClient: returns canned responses keyed by URL substring."""

    def __init__(self, routes: dict[str, str]):
        self.routes = routes
        self.calls = []

        class _S:
            headers = {}

        self.session = _S()

    def _match(self, url):
        for key, body in self.routes.items():
            if key in url:
                return body
        raise AssertionError(f"unexpected URL {url}")

    def get_text(self, url, params=None):
        self.calls.append((url, params))
        return self._match(url)

    def get_json(self, url, params=None):
        return json.loads(self.get_text(url, params))

    def post_text(self, url, data):
        self.calls.append((url, data))
        return self._match(url)


@pytest.fixture
def fixtures():
    return FIXTURES


@pytest.fixture
def fake_http():
    return FakeHttp
