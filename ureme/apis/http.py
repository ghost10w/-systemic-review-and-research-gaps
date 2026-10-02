"""Polite HTTP client: rate limiting, retries with backoff, optional disk cache."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

from ureme import __version__

log = logging.getLogger(__name__)

# Parameters never written into cache keys (secrets).
_SECRET_PARAMS = {"api_key", "x-api-key"}


class HttpError(RuntimeError):
    pass


class HttpClient:
    def __init__(
        self,
        min_interval: float = 0.34,
        cache_dir: Path | None = None,
        timeout: float = 30.0,
        max_retries: int = 5,
        headers: dict[str, str] | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.min_interval = min_interval
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": f"UREME/{__version__} (research synthesis engine)"})
        if headers:
            self.session.headers.update(headers)
        self._last = 0.0

    def _cache_path(self, method: str, url: str, params: dict | None, data: dict | None) -> Path | None:
        if not self.cache_dir:
            return None
        def clean(d: dict | None) -> dict:
            return {k: v for k, v in sorted((d or {}).items()) if k not in _SECRET_PARAMS}

        key = json.dumps([method, url, clean(params), clean(data)], sort_keys=True, default=str)
        return self.cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()}.txt"

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def request(self, method: str, url: str, params: dict | None = None, data: dict | None = None) -> str:
        cache = self._cache_path(method, url, params, data)
        if cache and cache.exists():
            return cache.read_text(encoding="utf-8")
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                resp = self.session.request(method, url, params=params, data=data, timeout=self.timeout)
            except requests.RequestException as exc:
                last_err = exc
                time.sleep(min(2**attempt, 30))
                continue
            if resp.status_code == 200:
                text = resp.text
                if cache:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_text(text, encoding="utf-8")
                return text
            if resp.status_code == 404:
                raise HttpError(f"404 Not Found: {url}")
            if resp.status_code in (429, 500, 502, 503, 504):
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(2 ** (attempt + 1), 60)
                log.warning("HTTP %s from %s; retrying in %.0fs", resp.status_code, url, delay)
                last_err = HttpError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                time.sleep(delay)
                continue
            raise HttpError(f"HTTP {resp.status_code} for {url}: {resp.text[:300]}")
        raise HttpError(f"Giving up on {url} after {self.max_retries} attempts: {last_err}")

    def get_text(self, url: str, params: dict | None = None) -> str:
        return self.request("GET", url, params=params)

    def get_json(self, url: str, params: dict | None = None) -> Any:
        return json.loads(self.get_text(url, params))

    def post_text(self, url: str, data: dict) -> str:
        return self.request("POST", url, data=data)
