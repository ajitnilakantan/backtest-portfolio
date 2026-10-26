import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import app


class PortfolioHelpersTest(unittest.TestCase):
    def test_layout_uses_compact_theme_and_chart_heights(self):
        self.assertEqual(app.app.title, "Backtest Portfolio")
        self.assertIn("compact-app", app.app.layout.className)
        layout_text = str(app.app.layout)
        self.assertIn("370px", layout_text)
        self.assertIn("340px", layout_text)
        self.assertIn("compact-manager", layout_text)

    def test_layout_defaults_to_english_and_one_million_investment(self):
        self.assertIn('lang="en"', app.app.index_string)
        self.assertEqual(app.DEFAULT_INVESTMENT, 1_000_000)
        layout_text = str(app.app.layout)
        self.assertIn("1000000", layout_text)

    def test_portfolio_options_list_users_first_and_sort_predefined(self):
        options = app.portfolio_options({"zebra": {}, "Alpha": {}})
        user_labels = [option["label"] for option in options if option["value"].startswith("user:")]
        self.assertEqual(user_labels, ["User — Alpha", "User — zebra"])
        self.assertTrue(options[0]["value"].startswith("user:"))
        self.assertTrue(options[-1]["value"].startswith("predefined:"))

    def test_clean_rows_combines_duplicates_and_ignores_invalid_weights(self):
        rows = [
            {"asset": " spy ", "weight": 40},
            {"asset": "SPY", "weight": "10"},
            {"asset": "QQQ", "weight": "bad"},
            {"asset": "BND", "weight": -5},
            {"asset": "GLD", "weight": np.nan},
        ]
        self.assertEqual(app.clean_allocation_rows(rows), {"SPY": 50.0})

    def test_normalize_allocation(self):
        normalized = app.normalize_allocation({"QQQ": 60, "SPY": 40})
        self.assertEqual(normalized, {"QQQ": 0.6, "SPY": 0.4})

    def test_portfolio_display_name_uses_safe_fallback(self):
        self.assertEqual(
            app.portfolio_display_name("user:Retirement", "Portfolio"),
            "Retirement",
        )
        self.assertEqual(app.portfolio_display_name("", "Portfolio"), "Portfolio")

    def test_invalid_portfolio_save_preserves_existing_data(self):
        result = app.save_portfolio(
            1,
            "user:Custom",
            [{"asset": "", "weight": 0}],
            {"Custom": {"QQQ": 100}},
        )
        self.assertIs(result, app.dash.no_update)

    def test_normalize_portfolio_rows(self):
        rows = app.normalize_portfolio_table(
            1,
            [{"asset": "SPY", "weight": 1}, {"asset": "BND", "weight": 3}],
        )
        self.assertEqual(rows, [{"asset": "SPY", "weight": 25.0}, {"asset": "BND", "weight": 75.0}])

    def test_fixed_benchmarks(self):
        self.assertEqual(
            app.BENCHMARK_PORTFOLIOS,
            {
                "S&P 500": {"SPY": 100.0},
                "Nasdaq": {"QQQ": 100.0},
                "60/40 Nasdaq/S&P Mix": {"QQQ": 60.0, "SPY": 40.0},
            },
        )
        self.assertEqual(
            [option["label"] for option in app.benchmark_options()],
            [
                "Benchmark — S&P 500",
                "Benchmark — Nasdaq",
                "Benchmark — 60/40 Nasdaq/S&P Mix",
            ],
        )

    def test_registry_loads_relative_file(self):
        self.assertEqual(app.load_benchmark_registry(), app.BENCHMARK_PORTFOLIOS)

    def test_registry_rejects_invalid_weights(self):
        with self.assertRaisesRegex(ValueError, "positive finite weights"):
            app.validate_benchmark_registry({"S&P 500": {"SPY": "invalid"}})

    def test_registry_requires_default_benchmark(self):
        with self.assertRaisesRegex(ValueError, "must include the default"):
            app.validate_benchmark_registry({"Other": {"SPY": 100}})

    def test_registry_file_reports_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmarks.json"
            path.write_text("not-json", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Unable to load"):
                app.load_benchmark_registry(path)

    def test_portfolio_type_labels(self):
        self.assertEqual(
            app.portfolio_type_label("predefined:Classic 60/40"),
            "Predefined portfolio",
        )
        self.assertEqual(app.portfolio_type_label("user:Custom"), "User portfolio")

    def test_simulation_and_metrics_use_shared_starting_capital(self):
        dates = pd.date_range("2024-01-01", periods=6, freq="D")
        prices = pd.DataFrame(
            {"SPY": [100, 101, 102, 103, 104, 105], "QQQ": [100, 102, 104, 106, 108, 110]},
            index=dates,
        )
        series = app.simulate_portfolio(prices, {"SPY": 50, "QQQ": 50}, 10_000, "None")
        metrics = app.calculate_metrics(series, 10_000)
        self.assertAlmostEqual(series.iloc[0], 10_000)
        self.assertGreater(metrics["ending_balance"], 10_000)
        self.assertLessEqual(metrics["max_drawdown"], 0)
        self.assertEqual(metrics["cumulative_dividends"], 0)

    def test_strategy_rows_update_names_and_visibility(self):
        visible = app.update_strategy_rows(
            "predefined:Classic 60/40",
            "user:Custom",
        )
        self.assertEqual(visible[0], "Portfolio 1 · Classic 60/40")
        self.assertEqual(visible[1], "Portfolio 2 · Custom")
        self.assertEqual(visible[2], {})

        hidden = app.update_strategy_rows("predefined:Classic 60/40", "")
        self.assertEqual(hidden[2], {"display": "none"})

    def test_layout_has_independent_strategy_controls(self):
        layout_text = str(app.app.layout)
        for component_id in [
            "portfolio-1-rebalance-freq",
            "portfolio-1-dividend-mode",
            "portfolio-2-rebalance-freq",
            "portfolio-2-dividend-mode",
            "portfolio-2-strategy-row",
        ]:
            self.assertIn(component_id, layout_text)
        self.assertNotIn("Copy P1", layout_text)
        self.assertIn("Annual rebalance · Reinvest dividends", layout_text)

    def test_cash_dividends_increase_value_without_reinvestment(self):
        dates = pd.date_range("2024-01-01", periods=6, freq="D")
        prices = pd.DataFrame({"SPY": [100] * 6}, index=dates)
        dividends = pd.DataFrame({"SPY": [0, 1, 0, 1, 0, 0]}, index=dates)
        result = app.simulate_portfolio_with_dividends(
            prices, dividends, {"SPY": 100}, 10_000, "None"
        )
        self.assertAlmostEqual(result["dividends"].sum(), 200)
        self.assertAlmostEqual(result["cumulative_dividends"].iloc[-1], 200)
        self.assertAlmostEqual(result["value"].iloc[-1], 10_200)

    def test_reinvest_dividends_purchases_fractional_shares(self):
        dates = pd.date_range("2024-01-01", periods=3, freq="W-FRI")
        prices = pd.DataFrame({"SPY": [100, 110, 120]}, index=dates)
        dividends = pd.DataFrame({"SPY": [0, 1, 0]}, index=dates)
        cash_result = app.simulate_portfolio_with_dividends(
            prices, dividends, {"SPY": 100}, 10_000, "None", "cash"
        )
        reinvest_result = app.simulate_portfolio_with_dividends(
            prices, dividends, {"SPY": 100}, 10_000, "None", "reinvest"
        )
        self.assertAlmostEqual(
            reinvest_result["cumulative_dividends"].iloc[-1],
            cash_result["cumulative_dividends"].iloc[-1],
        )
        self.assertGreater(reinvest_result["value"].iloc[-1], cash_result["value"].iloc[-1])

    def test_rebalance_uses_dividend_cash_and_preserves_reported_total(self):
        dates = pd.to_datetime(
            ["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02", "2024-02-03"]
        )
        prices = pd.DataFrame({"SPY": [100] * 5}, index=dates)
        dividends = pd.DataFrame({"SPY": [0, 1, 0, 0, 0]}, index=dates)
        result = app.simulate_portfolio_with_dividends(
            prices, dividends, {"SPY": 100}, 10_000, "Month"
        )
        self.assertAlmostEqual(result["cumulative_dividends"].iloc[-1], 100)
        self.assertAlmostEqual(result["value"].iloc[-1], 10_100)

    def test_dividend_metrics_across_partial_years(self):
        dates = pd.to_datetime(
            ["2023-12-30", "2023-12-31", "2024-01-01", "2024-01-02", "2024-01-03"]
        )
        values = pd.Series([10_000] * 5, index=dates)
        dividends = pd.Series([0, 100, 0, 200, 0], index=dates)
        metrics = app.calculate_metrics(values, 10_000, dividends)
        self.assertEqual(metrics["cumulative_dividends"], 300)
        self.assertEqual(metrics["average_yearly_dividends"], 150)
        self.assertAlmostEqual(metrics["average_yearly_dividend_yield"], 0.015)

    def test_market_data_extractor_reads_close_and_dividends(self):
        dates = pd.date_range("2024-01-01", periods=2, freq="D")
        columns = pd.MultiIndex.from_product([["Close", "Dividends"], ["SPY", "QQQ"]])
        data = pd.DataFrame(
            [[100, 200, 0, 0], [101, 202, 1, 2]],
            index=dates,
            columns=columns,
        )
        prices, dividends = app.extract_market_data(data, ["SPY", "QQQ"])
        self.assertEqual(prices.loc[dates[1], "SPY"], 101)
        self.assertEqual(dividends.loc[dates[1], "QQQ"], 2)

    def test_market_data_extractor_handles_single_ticker(self):
        dates = pd.date_range("2024-01-01", periods=2, freq="D")
        data = pd.DataFrame(
            {"Close": [100, 101], "Dividends": [0, 1]},
            index=dates,
        )
        prices, dividends = app.extract_market_data(data, ["SPY"])
        self.assertEqual(list(prices.columns), ["SPY"])
        self.assertEqual(dividends.loc[dates[1], "SPY"], 1)

    def test_daily_market_data_resamples_to_weekly_close_and_dividends(self):
        dates = pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC")
        data = pd.DataFrame(
            {
                "Close": np.arange(100, 110),
                "Dividends": [0, 0.2, 0, 0.3, 0, 0, 0, 0.5, 0, 0],
            },
            index=dates,
        )
        weekly = app.to_weekly_market_data(data, "SPY")
        self.assertEqual(weekly.index.tz, None)
        self.assertEqual(weekly.iloc[0]["Close"], 104)
        self.assertAlmostEqual(weekly.iloc[0]["Dividends"], 0.5)
        self.assertAlmostEqual(weekly.iloc[1]["Dividends"], 0.5)

    def test_fill_limited_history_backfills_and_forward_fills_with_warning(self):
        index = pd.date_range("2024-01-05", periods=4, freq="W-FRI")
        prices = pd.DataFrame(
            {"SPCX": [np.nan, 100.0, 110.0, np.nan], "SPY": [90, 95, 100, 105]},
            index=index,
        )
        dividends = pd.DataFrame(
            {"SPCX": [np.nan, 1.0, 0.0, np.nan], "SPY": [0, 0, 0, 0]},
            index=index,
        )
        filled, filled_dividends, warnings = app.fill_limited_history(
            prices, dividends, ["SPCX", "SPY"]
        )
        self.assertEqual(filled["SPCX"].tolist(), [100.0, 100.0, 110.0, 110.0])
        self.assertEqual(filled_dividends["SPCX"].tolist(), [0.0, 1.0, 0.0, 0.0])
        self.assertIn("SPCX has limited history", warnings[0])
        self.assertIn("backfilled", warnings[0])
        self.assertIn("forward-filled", warnings[0])
        self.assertFalse(any("SPY has limited history" in warning for warning in warnings))

        target_index = pd.date_range("2024-01-01", periods=6, freq="W-FRI")
        extended, _, extended_warnings = app.fill_limited_history(
            prices.iloc[1:3], dividends.iloc[1:3], ["SPCX"], target_index=target_index
        )
        self.assertEqual(extended.index.min(), target_index.min())
        self.assertEqual(extended.index.max(), target_index.max())
        self.assertEqual(len(extended_warnings), 1)

    def test_fill_limited_history_leaves_unavailable_ticker_for_validation(self):
        index = pd.date_range("2024-01-05", periods=2, freq="W-FRI")
        prices = pd.DataFrame({"SPCX": [np.nan, np.nan]}, index=index)
        filled, _, warnings = app.fill_limited_history(
            prices, pd.DataFrame(index=index, columns=["SPCX"]), ["SPCX"]
        )
        self.assertTrue(filled["SPCX"].isna().all())
        self.assertEqual(warnings, [])

    def test_cached_market_data_avoids_repeated_download(self):
        dates = pd.date_range("2024-01-01", periods=12, freq="D")
        history = pd.DataFrame(
            {"Close": np.arange(100, 112), "Dividends": [0] * 12},
            index=dates,
        )
        with tempfile.TemporaryDirectory() as directory:
            cache_path = str(Path(directory) / "market.db")
            with patch.object(app.yf, "download", return_value=history) as download:
                first_prices, _ = app.load_cached_market_data(
                    ["SPY"], "2024-01-01", "2024-01-10", cache_path
                )
                second_prices, _ = app.load_cached_market_data(
                    ["SPY"], "2024-01-01", "2024-01-10", cache_path
                )
            self.assertEqual(download.call_count, 1)
            self.assertTrue(first_prices.equals(second_prices))

    def test_empty_download_does_not_advance_cache_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_path = str(Path(directory) / "market.db")
            with patch.object(
                app,
                "download_ticker_weekly",
                return_value=pd.DataFrame(columns=["Close", "Dividends"]),
            ):
                prices, dividends = app.load_cached_market_data(
                    ["MISSING"], "2024-01-01", "2024-01-31", cache_path
                )
            self.assertTrue(prices.empty)
            self.assertTrue(dividends.empty)
            from db_cache import DbCache

            with DbCache(cache_path) as cache:
                self.assertEqual(cache.get_coverage("MISSING"), (None, None))
                self.assertEqual(cache.latest_fetch("MISSING")["status"], "empty")

    def test_simulation_supports_flows_costs_and_real_values(self):
        dates = pd.date_range("2024-01-05", periods=5, freq="W-FRI")
        prices = pd.DataFrame({"SPY": [100, 110, 90, 100, 105]}, index=dates)
        dividends = pd.DataFrame({"SPY": 0.0}, index=dates)
        result = app.simulate_portfolio_with_dividends(
            prices,
            dividends,
            {"SPY": 100},
            10_000,
            "Threshold",
            recurring_flow=100,
            flow_frequency="Month",
            transaction_cost_fixed=1,
            inflation_rate=0.03,
        )
        self.assertIn("external_flows", result)
        self.assertIn("transaction_costs", result)
        self.assertIn("real_value", result)
        self.assertLessEqual(result["real_value"].iloc[-1], result["value"].iloc[-1])

    def test_cached_market_data_downloads_only_extension(self):
        dates = pd.date_range("2024-01-01", periods=25, freq="D")

        def history(ticker, start, end, **kwargs):
            mask = (dates >= pd.Timestamp(start)) & (dates < pd.Timestamp(end))
            selected = dates[mask]
            return pd.DataFrame(
                {"Close": np.arange(len(selected)) + 100, "Dividends": 0},
                index=selected,
            )

        with tempfile.TemporaryDirectory() as directory:
            cache_path = str(Path(directory) / "market.db")
            with patch.object(app.yf, "download", side_effect=history) as download:
                app.load_cached_market_data(["SPY"], "2024-01-05", "2024-01-15", cache_path)
                app.load_cached_market_data(["SPY"], "2024-01-01", "2024-01-20", cache_path)
            self.assertEqual(download.call_count, 3)
            starts = [call.kwargs["start"] for call in download.call_args_list]
            self.assertIn("2024-01-01", starts)
            self.assertNotEqual(download.call_args_list[-1].kwargs["start"], "2024-01-05")

    def test_growth_summary_formats_initial_investment_and_entities(self):
        summary = app.build_growth_summary(
            1_000_000,
            [
                ("Portfolio 1 — Custom", 1_250_000, 0.25, 0.08),
                ("S&P 500", 1_150_000, 0.15, 0.05),
            ],
        )
        summary_text = str(summary)
        self.assertIn("Initial Investment:", summary_text)
        self.assertIn("$1,000,000.00", summary_text)
        self.assertIn("Portfolio 1 — Custom", summary_text)
        self.assertIn("$1,250,000.00", summary_text)
        self.assertIn("25.00%", summary_text)
        self.assertIn("8.00%", summary_text)
        self.assertIn("S&P 500", summary_text)
        for column in ["Name", "Value", "Growth", "CAGR"]:
            self.assertIn(f"children='{column}'", summary_text)

    def test_growth_summary_supports_optional_second_portfolio(self):
        summary = app.build_growth_summary(
            10_000,
            [
                ("Portfolio 1", 11_000, 0.10, 0.04),
                ("Portfolio 2", 12_000, 0.20, 0.07),
                ("Benchmark", 10_500, 0.05, 0.02),
            ],
        )
        self.assertEqual(str(summary).count("Portfolio"), 2)
        self.assertIn("Benchmark", str(summary))

    def test_breakdown_panel_has_sortable_metrics_and_holdings(self):
        metrics = {
            "ending_balance": 12000,
            "cumulative_dividends": 300,
            "average_yearly_dividends": 150,
            "average_yearly_dividend_yield": 0.015,
            "total_return": 0.2,
            "cagr": 0.1,
        }
        panel = app.build_breakdown_panel(
            [
                {
                    "key": "portfolio-1",
                    "name": "Portfolio 1",
                    "allocation": {"SPY": 60, "BND": 40},
                    "metrics": metrics,
                    "holding_results": {
                        "SPY": {
                            "start_value": 6000,
                            "end_value": 7200,
                            "total_growth": 0.2,
                            "cagr": 0.1,
                        },
                        "BND": {
                            "start_value": 4000,
                            "end_value": 4800,
                            "total_growth": 0.2,
                            "cagr": 0.1,
                        },
                    },
                },
                {
                    "key": "benchmark",
                    "name": "S&P 500",
                    "allocation": {"SPY": 100},
                    "metrics": metrics,
                    "holding_results": {
                        "SPY": {
                            "start_value": 10000,
                            "end_value": 12000,
                            "total_growth": 0.2,
                            "cagr": 0.1,
                        }
                    },
                },
            ]
        )
        panel_text = str(panel)
        for heading in [
            "End Value",
            "Total Dividends",
            "Yearly Dividends",
            "Dividend Yield",
            "Total Growth",
            "CAGR",
            "Holding",
            "Allocation",
        ]:
            self.assertIn(heading, panel_text)
        self.assertIn("SPY", panel_text)
        self.assertIn("60.00%", panel_text)
        for heading in ["Start Value", "End Value", "Total Growth", "CAGR"]:
            self.assertIn(heading, panel_text)
        self.assertIn("$6,000.00", panel_text)
        self.assertIn("$7,200.00", panel_text)
        self.assertIn("sort_action='native'", panel_text)

    def test_breakdown_tab_is_in_layout(self):
        layout_text = str(app.app.layout)
        self.assertIn("subtab-breakdown", layout_text)
        self.assertIn("breakdown-container", layout_text)

    def test_simulation_returns_per_holding_values(self):
        dates = pd.date_range("2024-01-05", periods=3, freq="W-FRI")
        prices = pd.DataFrame({"SPY": [100, 110, 120]}, index=dates)
        result = app.simulate_portfolio_with_dividends(
            prices,
            pd.DataFrame({"SPY": [0, 0, 0]}, index=dates),
            {"SPY": 100},
            10_000,
            "None",
        )
        self.assertEqual(result["holding_results"]["SPY"]["start_value"], 10_000)
        self.assertEqual(result["holding_results"]["SPY"]["end_value"], 12_000)
        self.assertAlmostEqual(result["holding_results"]["SPY"]["total_growth"], 0.2)
        self.assertGreater(result["holding_results"]["SPY"]["cagr"], 0)

    def test_synthetic_portfolio_benchmark_comparison(self):
        dates = pd.date_range("2024-01-01", periods=8, freq="D")
        prices = pd.DataFrame(
            {
                "SPY": [100, 101, 102, 103, 104, 105, 106, 107],
                "QQQ": [100, 103, 106, 109, 112, 115, 118, 121],
            },
            index=dates,
        )
        portfolio = app.simulate_portfolio(prices, {"QQQ": 100}, 10_000, "None")
        benchmark = app.simulate_portfolio(prices, {"SPY": 100}, 10_000, "None")
        comparison = app.build_comparison(portfolio, benchmark, 10_000)

        self.assertEqual(len(comparison["index"]), 8)
        self.assertAlmostEqual(comparison["portfolio_series"].iloc[0], 10_000)
        self.assertAlmostEqual(comparison["benchmark_series"].iloc[0], 10_000)
        self.assertGreater(comparison["excess_balance"], 0)
        self.assertGreater(comparison["excess_return"], 0)
        self.assertEqual(comparison["metric_rows"][1][0], "Ending Balance")
        self.assertIn("portfolio_1", comparison["metric_rows"][1][1])
        self.assertIn("benchmark", comparison["metric_rows"][1][1])

    def test_three_way_comparison_aligns_all_series(self):
        dates = pd.date_range("2024-01-01", periods=8, freq="D")
        portfolio_1 = pd.Series(np.arange(8) * 100 + 10_000, index=dates)
        portfolio_2 = pd.Series(np.arange(7) * 120 + 10_000, index=dates[1:])
        benchmark = pd.Series(np.arange(8) * 80 + 10_000, index=dates)

        comparison = app.build_comparison(
            portfolio_1,
            benchmark,
            10_000,
            portfolio_2,
        )

        self.assertEqual(len(comparison["index"]), 7)
        self.assertIsNotNone(comparison["second_portfolio_series"])
        self.assertIn("portfolio_2", comparison["metrics"])
        self.assertIn("portfolio_2", comparison["metric_rows"][1][1])

    def test_duplicate_portfolios_are_supported(self):
        dates = pd.date_range("2024-01-01", periods=6, freq="D")
        series = pd.Series(np.arange(6) * 100 + 10_000, index=dates)
        comparison = app.build_comparison(series, series, 10_000, series.copy())
        self.assertTrue(
            comparison["portfolio_series"].equals(comparison["second_portfolio_series"])
        )

    def test_optional_portfolio_options_start_with_none(self):
        options = app.optional_portfolio_options({"Custom": {"SPY": 100}})
        self.assertEqual(
            options[0],
            {"label": "None — No second portfolio", "value": ""},
        )
        self.assertIn("user:Custom", [option["value"] for option in options])

    def test_dropdown_refresh_preserves_or_clears_second_selection(self):
        result = app.update_dropdowns(
            {"Custom": {"SPY": 100}},
            "user:Custom",
            "user:Custom",
            "user:Custom",
        )
        self.assertEqual(result[1], "user:Custom")
        self.assertEqual(result[3], "user:Custom")

        result = app.update_dropdowns(
            {},
            "predefined:Classic 60/40",
            "user:Custom",
            "predefined:Classic 60/40",
        )
        self.assertEqual(result[3], "")

    def test_dropdowns_preselect_first_user_portfolio(self):
        result = app.update_dropdowns(
            {"Custom": {"SPY": 100}},
            None,
            None,
            None,
        )
        self.assertEqual(result[1], "user:Custom")
        self.assertEqual(result[3], "")
        self.assertEqual(result[5], "user:Custom")
        self.assertEqual(result[0][0]["value"], "user:Custom")

    def test_dropdowns_fall_back_to_first_predefined_when_no_users(self):
        result = app.update_dropdowns({}, None, None, None)
        self.assertEqual(result[1], "predefined:Classic 60/40")
        self.assertEqual(result[5], "predefined:Classic 60/40")
        self.assertEqual(result[3], "")

    def test_second_portfolio_badge_states(self):
        self.assertEqual(
            app.update_second_portfolio_badge(""),
            ("No second portfolio", "secondary"),
        )
        self.assertEqual(
            app.update_second_portfolio_badge("user:Custom"),
            ("User portfolio", "primary"),
        )

    def test_dividend_panel_two_and_three_entities(self):
        dates = pd.date_range("2024-01-05", periods=6, freq="W-FRI")
        values = pd.Series(np.arange(6) * 100 + 10_000, index=dates)
        dividends = pd.Series([0, 10, 0, 20, 0, 30], index=dates)
        comparison = app.build_comparison(
            values,
            values,
            10_000,
            values,
            dividends,
            dividends,
            dividends,
        )
        labels = {
            "portfolio_1": "Portfolio 1",
            "portfolio_2": "Portfolio 2",
            "benchmark": "Benchmark",
        }
        colors = {
            "portfolio_1": "#3987e5",
            "portfolio_2": "#d95926",
            "benchmark": "#199e70",
        }
        summary, figure, events = app.build_dividend_panel(comparison, labels, colors)
        self.assertEqual(len(summary), 3)
        self.assertEqual(len(figure.data), 3)
        self.assertIsNotNone(events)

    def test_dividend_panel_zero_history_has_empty_state(self):
        dates = pd.date_range("2024-01-05", periods=6, freq="W-FRI")
        values = pd.Series(np.arange(6) * 100 + 10_000, index=dates)
        zeros = pd.Series(0.0, index=dates)
        comparison = app.build_comparison(
            values,
            values,
            10_000,
            portfolio_dividends=zeros,
            benchmark_dividends=zeros,
        )
        labels = {"portfolio_1": "Portfolio 1", "benchmark": "Benchmark"}
        colors = {"portfolio_1": "#3987e5", "benchmark": "#199e70"}
        summary, figure, events = app.build_dividend_panel(comparison, labels, colors)
        self.assertEqual(len(summary), 2)
        self.assertEqual(len(figure.data), 0)
        self.assertEqual(len(figure.layout.annotations), 1)

    def test_comparison_requires_enough_overlap(self):
        dates = pd.date_range("2024-01-01", periods=4, freq="D")
        series = pd.Series([10_000, 10_100, 10_200, 10_300], index=dates)
        with self.assertRaisesRegex(ValueError, "Not enough overlapping"):
            app.build_comparison(series, series, 10_000)

    def test_workbench_badge_uses_selected_saved_portfolio(self):
        self.assertEqual(
            app.update_workbench_portfolio_badge("predefined:Classic 60/40"),
            ("Predefined portfolio", "info"),
        )
        self.assertEqual(
            app.update_workbench_portfolio_badge("user:Custom"),
            ("User portfolio", "primary"),
        )

    def test_predefined_portfolio_is_read_only(self):
        result = app.load_manager_table("predefined:Classic 60/40", {})
        self.assertEqual(result[1:6], (False, False, True, True, True))

    def test_user_portfolio_is_editable(self):
        result = app.load_manager_table("user:Custom", {"Custom": {"SPY": 100}})
        self.assertEqual(result[1:6], (True, True, False, False, False))


if __name__ == "__main__":
    unittest.main()
