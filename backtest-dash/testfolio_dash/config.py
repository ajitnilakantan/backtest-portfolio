from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    host: str = os.getenv("TESTFOLIO_HOST", "127.0.0.1")
    port: int = int(os.getenv("TESTFOLIO_PORT", "8050"))
    debug: bool = _env_bool("TESTFOLIO_DEBUG")
    risk_free_rate: float = float(os.getenv("TESTFOLIO_RISK_FREE_RATE", "0.02"))
    recent_cache_ttl_hours: int = int(os.getenv("TESTFOLIO_CACHE_TTL_HOURS", "12"))


CONFIG = AppConfig()
