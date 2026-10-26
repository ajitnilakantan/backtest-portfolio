import unittest

import numpy as np
import pandas as pd

from testfolio_dash.analytics import benchmark_relative_metrics, calculate_metrics, rolling_metrics
from testfolio_dash.portfolios import (
    export_portfolios_json,
    import_portfolios_json,
    validate_allocation_rows,
)
from testfolio_dash.sharing import decode_analysis_state, encode_analysis_state
from testfolio_dash.validation import validate_backtest_request


class ServicesTest(unittest.TestCase):
    def test_exact_short_period_cagr_and_warning(self):
        dates = pd.to_datetime(["2024-01-01", "2024-01-08"])
        metrics = calculate_metrics(pd.Series([100, 101], index=dates), 100)
        expected = 1.01 ** (365.25 / 7) - 1
        self.assertAlmostEqual(metrics["cagr"], expected)
        self.assertTrue(metrics["warnings"])

    def test_weekly_sharpe_and_relative_metrics(self):
        dates = pd.date_range("2020-01-03", periods=60, freq="W-FRI")
        portfolio = pd.Series(100 * np.cumprod(np.linspace(1.001, 1.01, 60)), index=dates)
        benchmark = pd.Series(100 * np.cumprod(np.linspace(1.001, 1.006, 60)), index=dates)
        metrics = calculate_metrics(portfolio, 100, risk_free_rate=0.02)
        relative = benchmark_relative_metrics(portfolio, benchmark, 0.02)
        self.assertTrue(np.isfinite(metrics["sharpe"]))
        self.assertIn("tracking_error", relative)
        self.assertFalse(rolling_metrics(portfolio)["1y"].dropna().empty)

    def test_validation_rejects_bad_dates_and_capital(self):
        with self.assertRaisesRegex(ValueError, "before"):
            validate_backtest_request("2024-02-01", "2024-01-01", 100)
        with self.assertRaisesRegex(ValueError, "positive"):
            validate_backtest_request("2024-01-01", "2024-02-01", 0)

    def test_portfolio_export_import_and_validation(self):
        payload = export_portfolios_json({"Custom": {"SPY": 60, "BND": 40}})
        self.assertEqual(import_portfolios_json(payload)["Custom"], {"BND": 40.0, "SPY": 60.0})
        allocation, errors = validate_allocation_rows([{"asset": "", "weight": 0}])
        self.assertFalse(allocation)
        self.assertTrue(errors)

    def test_analysis_state_round_trip(self):
        state = {"benchmark": "S&P 500", "capital": 10000, "settings": {"risk_free": 0.02}}
        self.assertEqual(decode_analysis_state(encode_analysis_state(state)), state)
        with self.assertRaisesRegex(ValueError, "Invalid"):
            decode_analysis_state("not-valid")


if __name__ == "__main__":
    unittest.main()
