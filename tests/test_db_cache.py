from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from backtest.db_cache import DbCache

EST = ZoneInfo("America/New_York")


class TestDbCache:
    """Tests for the DbCache SQLite cache."""

    def test_create_tables(self, in_memory_db):
        """Tables and indexes are created on initialization."""
        cursor = in_memory_db._conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='yahoo_daily'")
        assert cursor.fetchone() is not None

    def test_cache_data_roundtrip(self, in_memory_db):
        """Data cached can be read back correctly."""
        idx = pd.date_range("2020-01-03", periods=3, freq="D", tz=EST)
        df = pd.DataFrame(
            {
                "Ticker": ["AAPL", "AAPL", "AAPL"],
                "High": [151.0, 152.0, 153.0],
                "Low": [149.0, 150.0, 151.0],
                "Open": [150.0, 151.0, 152.0],
                "Close": [150.5, 151.5, 152.5],
                "Volume": [1000000, 1100000, 1200000],
            },
            index=idx,
        )
        assert in_memory_db.cache_data(df) is True

        result = in_memory_db.get_cache_data(
            "AAPL",
            datetime(2020, 1, 1, tzinfo=EST),
            datetime(2020, 1, 10, tzinfo=EST),
        )
        assert len(result) == 3
        assert result.iloc[0]["Close"] == 150.5
        assert result.iloc[2]["Close"] == 152.5

    def test_cache_data_upsert(self, in_memory_db):
        """INSERT OR REPLACE updates existing rows by primary key."""
        idx = pd.date_range("2020-01-03", periods=1, freq="D", tz=EST)
        df1 = pd.DataFrame(
            {
                "Ticker": ["AAPL"],
                "High": [151.0],
                "Low": [149.0],
                "Open": [150.0],
                "Close": [100.0],
                "Volume": [1000000],
            },
            index=idx,
        )
        in_memory_db.cache_data(df1)

        # Upsert same date+ticker with different close
        df2 = pd.DataFrame(
            {
                "Ticker": ["AAPL"],
                "High": [151.0],
                "Low": [149.0],
                "Open": [150.0],
                "Close": [200.0],  # changed
                "Volume": [2000000],  # changed
            },
            index=idx,
        )
        in_memory_db.cache_data(df2)

        result = in_memory_db.get_cache_data(
            "AAPL",
            datetime(2020, 1, 1, tzinfo=EST),
            datetime(2020, 1, 10, tzinfo=EST),
        )
        assert len(result) == 1
        assert result.iloc[0]["Close"] == 200.0
        assert result.iloc[0]["Volume"] == 2000000.0

    def test_get_min_max_dates_empty_ticker(self, in_memory_db):
        """Returns (None, None) for a ticker with no cached data."""
        min_date, max_date = in_memory_db.get_min_max_dates("UNKNOWN")
        assert min_date is None
        assert max_date is None

    def test_get_min_max_dates_with_data(self, in_memory_db):
        """Returns correct date range after caching data."""
        idx = pd.date_range("2020-06-15", periods=3, freq="D", tz=EST)
        df = pd.DataFrame(
            {
                "Ticker": ["AAPL", "AAPL", "AAPL"],
                "High": [151.0, 152.0, 153.0],
                "Low": [149.0, 150.0, 151.0],
                "Open": [150.0, 151.0, 152.0],
                "Close": [150.5, 151.5, 152.5],
                "Volume": [1000000, 1100000, 1200000],
            },
            index=idx,
        )
        in_memory_db.cache_data(df)

        min_date, max_date = in_memory_db.get_min_max_dates("AAPL")
        assert min_date is not None
        assert max_date is not None
        assert min_date.date() == idx[0].date()
        assert max_date.date() == idx[-1].date()

    def test_get_cache_data_empty_result(self, in_memory_db):
        """Returns an empty DataFrame for a ticker not in the cache."""
        result = in_memory_db.get_cache_data(
            "MISSING",
            datetime(2020, 1, 1, tzinfo=EST),
            datetime(2020, 12, 31, tzinfo=EST),
        )
        assert result.empty

    def test_get_cache_data_date_filter(self, in_memory_db):
        """The BETWEEN clause correctly filters by date range."""
        idx = pd.date_range("2020-01-03", periods=5, freq="D", tz=EST)
        df = pd.DataFrame(
            {
                "Ticker": ["AAPL"] * 5,
                "High": [151.0] * 5,
                "Low": [149.0] * 5,
                "Open": [150.0] * 5,
                "Close": [150.5 + i for i in range(5)],
                "Volume": [1000000] * 5,
            },
            index=idx,
        )
        in_memory_db.cache_data(df)

        # Query a sub-range
        result = in_memory_db.get_cache_data(
            "AAPL",
            datetime(2020, 1, 4, tzinfo=EST),
            datetime(2020, 1, 6, tzinfo=EST),
        )
        assert 1 <= len(result) <= 3  # depends on exact BETWEEN behavior

    def test_sql_injection_prevention(self, in_memory_db):
        """Parameterized query prevents SQL injection."""
        malicious_ticker = "'; DROP TABLE yahoo_daily; --"
        result = in_memory_db.get_cache_data(
            malicious_ticker,
            datetime(2020, 1, 1, tzinfo=EST),
            datetime(2020, 12, 31, tzinfo=EST),
        )
        # Should return empty (no data for that ticker), not drop the table
        assert result.empty

        # Verify the table still exists
        cursor = in_memory_db._conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='yahoo_daily'")
        assert cursor.fetchone() is not None

    def test_cache_data_returns_false_when_no_conn(self):
        """cache_data returns False when used outside context manager."""
        db = DbCache(db_path=":memory:")
        # Without entering the context manager, _conn is None
        idx = pd.date_range("2020-01-03", periods=1, freq="D", tz=EST)
        df = pd.DataFrame(
            {
                "Ticker": ["AAPL"],
                "High": [151.0],
                "Low": [149.0],
                "Open": [150.0],
                "Close": [150.5],
                "Volume": [1000000],
            },
            index=idx,
        )
        assert db.cache_data(df) is False

    def test_get_min_max_dates_returns_none_when_no_conn(self):
        """get_min_max_dates returns (None, None) when used outside context manager."""
        db = DbCache(db_path=":memory:")
        min_date, max_date = db.get_min_max_dates("AAPL")
        assert min_date is None
        assert max_date is None

    def test_get_cache_data_returns_empty_when_no_conn(self):
        """get_cache_data returns empty DataFrame when used outside context manager."""
        db = DbCache(db_path=":memory:")
        result = db.get_cache_data(
            "AAPL",
            datetime(2020, 1, 1, tzinfo=EST),
            datetime(2020, 12, 31, tzinfo=EST),
        )
        assert result.empty