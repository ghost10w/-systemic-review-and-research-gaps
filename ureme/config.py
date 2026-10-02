"""Runtime settings, resolved from CLI flags first, then environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    email: str | None = None
    ncbi_api_key: str | None = None
    s2_api_key: str | None = None
    cache_dir: Path | None = None
    timeout: float = 30.0
    max_retries: int = 5
    fetch_full_text: bool = True
    fetch_citations: bool = False
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        cache = overrides.pop("cache_dir", None) or os.environ.get("UREME_CACHE_DIR")
        s = cls(
            email=os.environ.get("NCBI_EMAIL") or os.environ.get("UREME_EMAIL"),
            ncbi_api_key=os.environ.get("NCBI_API_KEY"),
            s2_api_key=os.environ.get("S2_API_KEY") or os.environ.get("SEMANTIC_SCHOLAR_API_KEY"),
            cache_dir=Path(cache).expanduser() if cache else None,
        )
        for k, v in overrides.items():
            if v is not None:
                setattr(s, k, v)
        return s
