from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime
from typing import Final

import pandas as pd


class NullContextManager:
    """A safe placeholder context manager that does nothing and returns None."""
    def __enter__(self) -> None:
        return None
        
    def __exit__(self, _exc_type, _exc_val, _exc_tb) -> bool:
        return True # Suppresses errors inside the block if they occur

class DbCache:
    """SQLite cache for Yahoo Finance daily data."""

    SCHEMA_VERSION: Final = "1.0"

    _db_path: str
    _conn: sqlite3.Connection | None = None

    def __init__(self, db_path: str = os.path.join(tempfile.gettempdir(), "finance-data.db")):
        self._db_path = db_path
        self._conn = None

    @property
    def conn(self) -> sqlite3.Connection | NullContextManager:
        """Returns the real connection, or a safe null manager if None."""
        if self._conn is None:
            return NullContextManager()
        return self._conn

    def __enter__(self):
        """ To implement "with" """
        # Establish the connection file handle
        self._conn = sqlite3.connect(self._db_path)
        
        # Run the table initialization immediately
        self._init_db()
        
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        """ Cleanup at the end of "with" """
        if self._conn:
            self._conn.close()

    def _init_db(self) -> bool:
        """Internal helper to build the schema on startup if missing."""
        # Use an explicit 'with conn' to commit the schema changes automatically
        # If self._conn is None, 'with' hits NullContextManager and skips execution safely
        with self.conn as active_conn:
            if active_conn is None:
                return True

            # Schema change, so reset the cache
            if self.get_kv("schema_version") != DbCache.SCHEMA_VERSION:
                self._drop_db()

            # Create yahoo_daily and configuration tables
            cursor = active_conn.cursor()
            try:
                cursor.execute("pragma encoding=UTF8")
                cursor.execute("""CREATE TABLE IF NOT EXISTS yahoo_daily
                    (Date TEXT,
                     Ticker TEXT,
                     High NUMERIC,
                     Low NUMERIC,
                     Open NUMERIC,
                     Close NUMERIC,
                     Volume NUMERIC,
                     PRIMARY KEY(Date, Ticker))""")
                cursor.execute("CREATE INDEX index_Date ON yahoo_daily(Date)")
                cursor.execute("CREATE INDEX index_Ticker ON yahoo_daily(Ticker)")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS configuration (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)

                # Set for versioning of the database
                self.set_kv("schema_version", DbCache.SCHEMA_VERSION)

                return True
            except sqlite3.DatabaseError:
                return False

    def _drop_db(self) -> bool:
        """Internal helper to reset the database, e.g. on schema change."""
        # Use an explicit 'with conn' to commit the schema changes automatically
        # If self._conn is None, 'with' hits NullContextManager and skips execution safely
        with self.conn as active_conn:
            if active_conn is None:
                return True
            active_conn.execute("DROP TABLE IF EXISTS yahoo_daily")
            active_conn.execute("DROP TABLE IF EXISTS configuration")
        return True

    def get_cache_data(self, ticker: str, min_date: datetime, max_date: datetime) -> pd.DataFrame:
        with self.conn as active_conn:
            if active_conn is None:
                return pd.DataFrame() # Completely empty DataFrame (0 rows, 0 columns)
            query = """SELECT Date, Ticker, High, Low, Open, Close, Volume
                       FROM yahoo_daily
                       WHERE Ticker = ?
                       AND Date BETWEEN ? AND ?
                       ORDER BY DATE(Date) ASC"""
            df = pd.read_sql_query(
                sql=query,
                con=active_conn,
                params=[ticker, min_date.isoformat(), max_date.isoformat()],
                index_col="Date",
                parse_dates={"Date": "%Y-%m-%dT%H:%M:%S%z"},
            )
            return df

    def cache_data(self, df: pd.DataFrame) -> bool:
        with self.conn as active_conn:
            if active_conn is None:
                return False

            zip_rows = zip(
                df.index,
                df["Ticker"],
                df["High"],
                df["Low"],
                df["Open"],
                df["Close"],
                df["Volume"],
                strict=True,
            )
            rows = [
                (
                    row[0].isoformat(),
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                )
                for row in zip_rows
            ]

            query = "INSERT OR REPLACE INTO yahoo_daily (Date, Ticker, High, Low, Open, Close, Volume) VALUES(?,?,?,?,?,?,?);"
            active_conn.executemany(query, rows)
        return True


    def get_min_max_dates(self, ticker: str) -> tuple[datetime | None, datetime | None]:
        with self.conn as active_conn:
            if active_conn is None:
                return (None, None)

            query = "SELECT Min(Date), Max(Date) from yahoo_daily where Ticker = ?"
            cursor = active_conn.cursor()
            a = cursor.execute(query, (ticker,)).fetchall()
            cursor.close()
            min_date = None
            max_date = None
            if a and a[0] and a[0][0]:
                min_date = datetime.strptime(a[0][0], "%Y-%m-%dT%H:%M:%S%z")
            if a and a[0] and a[0][1]:
                max_date = datetime.strptime(a[0][1], "%Y-%m-%dT%H:%M:%S%z")
            return (min_date, max_date)

    def set_kv(self, key: str, value: str):
        """Insert a new key-value pair or overwrite the value if the key exists."""
        with self.conn as active_conn:
            if active_conn is None:
                return
            active_conn.execute(
                    "INSERT OR REPLACE INTO configuration (key, value) VALUES (?, ?)",
                    (key, value)
                )

    def get_kv(self, key: str, default=None) -> str | None:
        """Retrieve a value by its key. Returns default if not found."""
        try:
            with self.conn as active_conn:
                if active_conn is None:
                    return default
                cursor = active_conn.execute(
                    "SELECT value FROM configuration WHERE key = ?", 
                    (key,)
                )
                row = cursor.fetchone()
                return row[0] if row else default
        except sqlite3.OperationalError:
            # Safe fallback if the table itself doesn't exist yet during check
            return default
