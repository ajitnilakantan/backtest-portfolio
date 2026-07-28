from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from backtest.backtest import (
    _allocate_shares_in_portfolio,
    _download_yahoo_finance_data,
    _normalize_percentage,
    _rebalance_portfolio,
    download_portfolio,
    get_numrebalancedshares_column,
    get_numshares_column,
    portfolio_value,
)
from backtest.holding import Holding, Portfolio, PortfolioType

EST = ZoneInfo("America/New_York")


class TestHolding:
    """Tests for the Holding dataclass."""

    def test_holding_fields(self):
        h = Holding("AAPL", 60)
        assert h.ticker == "AAPL"
        assert h.value == 60

    def test_holding_equality(self):
        assert Holding("AAPL", 60) == Holding("AAPL", 60)

    def test_holding_inequality(self):
        assert Holding("AAPL", 60) != Holding("MSFT", 40)


class TestNormalizePercentage:
    """Tests for percentage normalization."""

    @pytest.mark.parametrize(
        ("values", "expected_aapl"),
        [
            ((60, 40), 60.0),
            ((80, 40), 80 * 100 / 120),
            ((30, 20), 60.0),
        ],
    )
    def test_normalizes_holdings_to_100(self, values, expected_aapl):
        portfolio = Portfolio(
            name="Normalization Test",
            type=PortfolioType.PERCENT,
            holdings=[Holding("AAPL", values[0]), Holding("MSFT", values[1])],
        )

        aapl = _normalize_percentage(portfolio, "AAPL")
        msft = _normalize_percentage(portfolio, "MSFT")

        assert aapl == pytest.approx(expected_aapl)
        assert aapl + msft == pytest.approx(100.0)


class TestDownloadYahooFinanceData:
    """Tests for the Yahoo Finance boundary."""

    def test_returns_dataframe_with_ticker_column(self):
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2020, 1, 10, tzinfo=EST)

        with patch("backtest.backtest.yf.Ticker") as mock_ticker:
            mock_instance = MagicMock()
            index = pd.date_range("2020-01-02", periods=5, freq="B", tz="UTC")
            mock_instance.history.return_value = pd.DataFrame(
                {
                    "Open": [150.0] * 5,
                    "High": [152.0] * 5,
                    "Low": [149.0] * 5,
                    "Close": [151.0] * 5,
                    "Volume": [1_000_000] * 5,
                },
                index=index,
            )
            mock_ticker.return_value = mock_instance

            result = _download_yahoo_finance_data("AAPL", start, end)

        mock_ticker.assert_called_once_with("AAPL")
        assert not result.empty
        assert (result["Ticker"] == "AAPL").all()
        assert str(result.index.tz) == "UTC"


class TestDownloadPortfolio:
    """Tests for the integrated portfolio download pipeline."""

    @staticmethod
    def _history(ticker, start, end):
        index = pd.date_range(pd.Timestamp(start).tz_convert("UTC"), pd.Timestamp(end).tz_convert("UTC"), freq="D")
        close = 150.0 if ticker == "AAPL" else 200.0
        return pd.DataFrame(
            {
                "Open": close,
                "High": close,
                "Low": close,
                "Close": close,
                "Volume": 1_000_000,
                "Ticker": ticker,
            },
            index=index,
        )

    def test_returns_integrated_portfolio_data(self, sample_portfolio, sample_dates):
        start, end = sample_dates

        with (
            patch("backtest.backtest.DbCache") as cache_class,
            patch("backtest.backtest._download_yahoo_finance_data") as download,
        ):
            cache = cache_class.return_value
            cache.get_min_max_dates.return_value = (None, None)
            download.side_effect = lambda ticker, first, last: self._history(ticker, first, last)

            result = download_portfolio(sample_portfolio, start, end, initial_investment=100_000)

        required_columns = {
            "AAPL",
            "MSFT",
            get_numshares_column("AAPL"),
            get_numshares_column("MSFT"),
            get_numrebalancedshares_column("AAPL"),
            get_numrebalancedshares_column("MSFT"),
        }
        assert required_columns <= set(result.columns)
        assert result.index.is_monotonic_increasing
        assert not result[sorted(required_columns)].isna().any().any()
        assert result[get_numshares_column("AAPL")].iloc[0] == pytest.approx(400.0)
        assert result[get_numshares_column("MSFT")].iloc[0] == pytest.approx(200.0)
        assert download.call_count == 2
        assert cache.cache_data.call_count == 2


class TestAllocateSharesInPortfolio:
    """Tests for initial share allocation in integrated data."""

    def test_adds_and_fills_share_columns(self, sample_portfolio, sample_dates):
        start, end = sample_dates
        index = pd.date_range(start, end, freq="W-FRI")
        prices = pd.DataFrame({"AAPL": 150.0, "MSFT": 200.0}, index=index)

        result = _allocate_shares_in_portfolio(sample_portfolio, prices, start, end, 100_000, 1.3)

        assert list(result[["AAPL", "MSFT"]].columns) == ["AAPL", "MSFT"]
        assert (result[get_numshares_column("AAPL")] == pytest.approx(400.0)).all()
        assert (result[get_numshares_column("MSFT")] == pytest.approx(200.0)).all()


class TestRebalancePortfolio:
    """Tests for annual rebalancing in integrated data."""

    @staticmethod
    def _portfolio_data(start, end, aapl_prices, msft_prices, aapl_shares=400.0, msft_shares=200.0):
        index = pd.date_range(start, end, freq="W-FRI")
        data = pd.DataFrame(
            {
                "AAPL": aapl_prices(index),
                "MSFT": msft_prices(index),
                get_numshares_column("AAPL"): aapl_shares,
                get_numshares_column("MSFT"): msft_shares,
            },
            index=index,
        )
        return data

    def test_rebalances_to_target_weights_without_adding_rows(self, sample_portfolio):
        start = datetime(2020, 6, 1, tzinfo=EST)
        end = datetime(2021, 6, 1, tzinfo=EST)
        data = self._portfolio_data(
            start,
            end,
            lambda index: [150.0 + i * 2 for i in range(len(index))],
            lambda index: [200.0] * len(index),
        )
        original_index = data.index.copy()

        result = _rebalance_portfolio(sample_portfolio, data, start, end)

        pd.testing.assert_index_equal(result.index, original_index)
        year_end = datetime(2020, 12, 31, tzinfo=EST)
        rebalance_date = result.index[result.index.get_indexer([year_end], method="nearest")[0]]
        aapl_value, _ = portfolio_value(sample_portfolio, result, True, rebalance_date, "AAPL")
        msft_value, _ = portfolio_value(sample_portfolio, result, True, rebalance_date, "MSFT")
        assert aapl_value / (aapl_value + msft_value) == pytest.approx(0.6, abs=0.005)
        assert msft_value / (aapl_value + msft_value) == pytest.approx(0.4, abs=0.005)

    def test_short_period_keeps_initial_allocation(self, sample_portfolio):
        start = datetime(2020, 6, 1, tzinfo=EST)
        end = datetime(2020, 11, 1, tzinfo=EST)
        data = self._portfolio_data(start, end, lambda index: [150.0] * len(index), lambda index: [200.0] * len(index))

        result = _rebalance_portfolio(sample_portfolio, data, start, end)

        assert (result[get_numrebalancedshares_column("AAPL")] == result[get_numshares_column("AAPL")]).all()
        assert (result[get_numrebalancedshares_column("MSFT")] == result[get_numshares_column("MSFT")]).all()

    def test_preserves_original_share_columns(self, sample_portfolio):
        start = datetime(2020, 6, 1, tzinfo=EST)
        end = datetime(2021, 6, 1, tzinfo=EST)
        data = self._portfolio_data(start, end, lambda index: [150.0] * len(index), lambda index: [200.0] * len(index))
        original_aapl = data[get_numshares_column("AAPL")].copy()
        original_msft = data[get_numshares_column("MSFT")].copy()

        result = _rebalance_portfolio(sample_portfolio, data, start, end)

        pd.testing.assert_series_equal(result[get_numshares_column("AAPL")], original_aapl)
        pd.testing.assert_series_equal(result[get_numshares_column("MSFT")], original_msft)

    def test_single_holding_remains_fully_invested(self):
        start = datetime(2020, 6, 1, tzinfo=EST)
        end = datetime(2021, 6, 1, tzinfo=EST)
        portfolio = Portfolio(name="QQQ Only", type=PortfolioType.PERCENT, holdings=[Holding("QQQ", 100)])
        index = pd.date_range(start, end, freq="W-FRI")
        data = pd.DataFrame({"QQQ": 300.0, get_numshares_column("QQQ"): 333.333}, index=index)

        result = _rebalance_portfolio(portfolio, data, start, end)

        pd.testing.assert_index_equal(result.index, index)
        assert (result[get_numrebalancedshares_column("QQQ")] == pytest.approx(333.333)).all()
