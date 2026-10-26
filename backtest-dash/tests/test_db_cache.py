import tempfile
import unittest
from pathlib import Path

import pandas as pd

from db_cache import DbCache


class DbCacheTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tempdir.name) / "cache.db")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_schema_cache_round_trip_and_upsert(self):
        dates = pd.to_datetime(["2024-01-05", "2024-01-12"])
        frame = pd.DataFrame(
            {"Close": [100.0, 101.0], "Dividends": [0.0, 1.0]},
            index=dates,
        )
        with DbCache(self.path) as cache:
            self.assertTrue(cache.cache_data("SPY", frame))
            result = cache.get_cache_data("SPY", "2024-01-01", "2024-01-31")
            self.assertEqual(len(result), 2)
            self.assertEqual(result.iloc[-1]["Dividends"], 1.0)
            replacement = pd.DataFrame({"Close": [105.0], "Dividends": [2.0]}, index=[dates[-1]])
            cache.cache_data("SPY", replacement)
            result = cache.get_cache_data("SPY", "2024-01-01", "2024-01-31")
            self.assertEqual(result.loc[dates[-1], "Close"], 105.0)
            self.assertEqual(result.loc[dates[-1], "Dividends"], 2.0)

    def test_coverage_extends_both_directions(self):
        with DbCache(self.path) as cache:
            self.assertEqual(cache.get_coverage("SPY"), (None, None))
            cache.extend_coverage("SPY", "2024-02-01", "2024-03-01")
            cache.extend_coverage("SPY", "2024-01-01", "2024-04-01")
            start, end = cache.get_coverage("SPY")
            self.assertEqual(start, pd.Timestamp("2024-01-01"))
            self.assertEqual(end, pd.Timestamp("2024-04-01"))

    def test_date_filter_and_parameterized_ticker(self):
        dates = pd.date_range("2024-01-05", periods=3, freq="W-FRI")
        frame = pd.DataFrame({"Close": [1, 2, 3], "Dividends": 0}, index=dates)
        with DbCache(self.path) as cache:
            cache.cache_data("SPY", frame)
            result = cache.get_cache_data("SPY", "2024-01-10", "2024-01-20")
            self.assertEqual(list(result["Close"]), [2.0, 3.0])
            malicious = cache.get_cache_data(
                "'; DROP TABLE yahoo_weekly; --", "2024-01-01", "2024-02-01"
            )
            self.assertTrue(malicious.empty)
            self.assertEqual(len(cache.get_cache_data("SPY", "2024-01-01", "2024-02-01")), 3)

    def test_methods_outside_context_are_safe(self):
        cache = DbCache(self.path)
        self.assertTrue(cache.get_cache_data("SPY", "2024-01-01", "2024-02-01").empty)
        self.assertEqual(cache.get_coverage("SPY"), (None, None))
        self.assertFalse(cache.cache_data("SPY", pd.DataFrame()))


if __name__ == "__main__":
    unittest.main()
