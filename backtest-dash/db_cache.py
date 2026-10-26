"""Backward-compatible import for the packaged SQLite cache."""

from testfolio_dash.db_cache import DEFAULT_CACHE_PATH, DbCache

__all__ = ["DEFAULT_CACHE_PATH", "DbCache"]
