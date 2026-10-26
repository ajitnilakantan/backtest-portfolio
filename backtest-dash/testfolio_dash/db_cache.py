from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DEFAULT_CACHE_PATH = os.path.join(tempfile.gettempdir(), "backtest-dash-weekly-v1.db")


class DbCache:
    """SQLite cache for end-of-week Yahoo close and dividend data."""

    SCHEMA_VERSION = "3.0"

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.getenv("TESTFOLIO_CACHE_PATH", DEFAULT_CACHE_PATH)
        self.conn: sqlite3.Connection | None = None

    def __enter__(self):
        if self.db_path != ":memory:":
            Path(self.db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=10)
        self.conn.execute("PRAGMA busy_timeout=10000")
        if self.db_path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_db()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def _init_db(self):
        if self.conn is None:
            return
        with self.conn:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS configuration (key TEXT PRIMARY KEY, value TEXT)"
            )
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS yahoo_weekly (
                    Date TEXT NOT NULL,
                    Ticker TEXT NOT NULL,
                    Close REAL NOT NULL,
                    Dividends REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY(Date, Ticker)
                )"""
            )
            self.conn.execute("CREATE INDEX IF NOT EXISTS index_weekly_date ON yahoo_weekly(Date)")
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS index_weekly_ticker ON yahoo_weekly(Ticker)"
            )
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS ticker_coverage (
                    Ticker TEXT PRIMARY KEY,
                    ValidFrom TEXT NOT NULL,
                    ValidThrough TEXT NOT NULL,
                    FetchedAt TEXT
                )"""
            )
            columns = {row[1] for row in self.conn.execute("PRAGMA table_info(ticker_coverage)")}
            if "FetchedAt" not in columns:
                self.conn.execute("ALTER TABLE ticker_coverage ADD COLUMN FetchedAt TEXT")
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS fetch_log (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Ticker TEXT NOT NULL,
                    RequestedFrom TEXT NOT NULL,
                    RequestedThrough TEXT NOT NULL,
                    ActualFrom TEXT,
                    ActualThrough TEXT,
                    FetchedAt TEXT NOT NULL,
                    Provider TEXT NOT NULL,
                    Status TEXT NOT NULL,
                    RowCount INTEGER NOT NULL DEFAULT 0,
                    ErrorCategory TEXT
                )"""
            )
            self.set_kv("schema_version", self.SCHEMA_VERSION)

    def set_kv(self, key: str, value: str):
        if self.conn is None:
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO configuration (key, value) VALUES (?, ?)",
            (key, value),
        )

    def get_kv(self, key: str, default=None):
        if self.conn is None:
            return default
        try:
            row = self.conn.execute(
                "SELECT value FROM configuration WHERE key = ?", (key,)
            ).fetchone()
        except sqlite3.OperationalError:
            return default
        return row[0] if row else default

    def cache_data(self, ticker: str, frame: pd.DataFrame) -> bool:
        if self.conn is None or frame.empty:
            return False
        rows = [
            (
                pd.Timestamp(date).date().isoformat(),
                ticker,
                float(row["Close"]),
                float(row.get("Dividends", 0.0)),
            )
            for date, row in frame.iterrows()
            if pd.notna(row["Close"])
        ]
        if not rows:
            return False
        with self.conn:
            self.conn.executemany(
                """INSERT OR REPLACE INTO yahoo_weekly
                   (Date, Ticker, Close, Dividends) VALUES (?, ?, ?, ?)""",
                rows,
            )
        return True

    def get_cache_data(self, ticker: str, start, end) -> pd.DataFrame:
        if self.conn is None:
            return pd.DataFrame(columns=["Close", "Dividends"])
        frame = pd.read_sql_query(
            """SELECT Date, Close, Dividends FROM yahoo_weekly
               WHERE Ticker = ? AND Date BETWEEN ? AND ? ORDER BY Date""",
            self.conn,
            params=(
                ticker,
                pd.Timestamp(start).date().isoformat(),
                pd.Timestamp(end).date().isoformat(),
            ),
        )
        if frame.empty:
            return pd.DataFrame(columns=["Close", "Dividends"])
        frame["Date"] = pd.to_datetime(frame["Date"])
        return frame.set_index("Date")

    def get_coverage(self, ticker: str):
        if self.conn is None:
            return None, None
        row = self.conn.execute(
            "SELECT ValidFrom, ValidThrough FROM ticker_coverage WHERE Ticker = ?",
            (ticker,),
        ).fetchone()
        if not row:
            return None, None
        return pd.Timestamp(row[0]), pd.Timestamp(row[1])

    def get_fetch_time(self, ticker: str):
        if self.conn is None:
            return None
        row = self.conn.execute(
            "SELECT FetchedAt FROM ticker_coverage WHERE Ticker = ?", (ticker,)
        ).fetchone()
        return pd.Timestamp(row[0]) if row and row[0] else None

    def set_coverage(self, ticker: str, valid_from, valid_through, fetched_at=None):
        if self.conn is None:
            return
        fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
        with self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO ticker_coverage
                   (Ticker, ValidFrom, ValidThrough, FetchedAt) VALUES (?, ?, ?, ?)""",
                (
                    ticker,
                    pd.Timestamp(valid_from).date().isoformat(),
                    pd.Timestamp(valid_through).date().isoformat(),
                    pd.Timestamp(fetched_at).isoformat(),
                ),
            )

    def extend_coverage(self, ticker: str, start, end, fetched_at=None):
        current_start, current_end = self.get_coverage(ticker)
        start = pd.Timestamp(start).normalize()
        end = pd.Timestamp(end).normalize()
        valid_from = min(start, current_start) if current_start is not None else start
        valid_through = max(end, current_end) if current_end is not None else end
        self.set_coverage(ticker, valid_from, valid_through, fetched_at)

    def invalidate_coverage(self, ticker: str):
        if self.conn is not None:
            with self.conn:
                self.conn.execute("DELETE FROM ticker_coverage WHERE Ticker = ?", (ticker,))

    def log_fetch(
        self,
        ticker: str,
        requested_from,
        requested_through,
        *,
        status: str,
        frame: pd.DataFrame | None = None,
        provider: str = "Yahoo Finance",
        error_category: str | None = None,
    ):
        if self.conn is None:
            return
        frame = frame if frame is not None else pd.DataFrame()
        actual_from = (
            pd.Timestamp(frame.index.min()).date().isoformat() if not frame.empty else None
        )
        actual_through = (
            pd.Timestamp(frame.index.max()).date().isoformat() if not frame.empty else None
        )
        with self.conn:
            self.conn.execute(
                """INSERT INTO fetch_log
                   (Ticker, RequestedFrom, RequestedThrough, ActualFrom, ActualThrough,
                    FetchedAt, Provider, Status, RowCount, ErrorCategory)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticker,
                    pd.Timestamp(requested_from).date().isoformat(),
                    pd.Timestamp(requested_through).date().isoformat(),
                    actual_from,
                    actual_through,
                    datetime.now(timezone.utc).isoformat(),
                    provider,
                    status,
                    len(frame),
                    error_category,
                ),
            )

    def latest_fetch(self, ticker: str):
        if self.conn is None:
            return None
        row = self.conn.execute(
            """SELECT FetchedAt, Provider, Status, RowCount, ActualThrough
               FROM fetch_log WHERE Ticker = ? ORDER BY Id DESC LIMIT 1""",
            (ticker,),
        ).fetchone()
        if not row:
            return None
        return {
            "fetched_at": row[0],
            "provider": row[1],
            "status": row[2],
            "row_count": row[3],
            "actual_through": row[4],
        }
