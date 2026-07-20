from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from backtest.backtest import (
    _download_yahoo_finance_data,
    _normalize_percentage,
    download_portfolio_history,
    rebalance_portfolio,
    shares_in_portfolio,
)
from backtest.holding import Holding, Portfolio, PortfolioType

EST = ZoneInfo("America/New_York")


class TestHolding:
    """Tests for the Holding dataclass."""

    def test_holding_fields(self):
        """Holding has ticker and value fields."""
        h = Holding("AAPL", 60)
        assert h.ticker == "AAPL"
        assert h.value == 60

    def test_holding_equality(self):
        """Two Holdings with same fields are equal."""
        h1 = Holding("AAPL", 60)
        h2 = Holding("AAPL", 60)
        assert h1 == h2

    def test_holding_inequality(self):
        """Holdings with different fields are not equal."""
        h1 = Holding("AAPL", 60)
        h2 = Holding("MSFT", 40)
        assert h1 != h2


class TestNormalizePercentage:
    """Tests for _normalize_percentage."""

    @pytest.fixture
    def portfolio_100(self):
        """Portfolio with percentages summing to 100."""
        return Portfolio(
            type=PortfolioType.PERCENT,
            holdings=[
                Holding("AAPL", 60),
                Holding("MSFT", 40),
            ],
        )

    @pytest.fixture
    def portfolio_over_100(self):
        """Portfolio with percentages summing to more than 100."""
        return Portfolio(
            type=PortfolioType.PERCENT,
            holdings=[
                Holding("AAPL", 80),
                Holding("MSFT", 40),
            ],
        )

    @pytest.fixture
    def portfolio_under_100(self):
        """Portfolio with percentages summing to less than 100."""
        return Portfolio(
            type=PortfolioType.PERCENT,
            holdings=[
                Holding("AAPL", 30),
                Holding("MSFT", 20),
            ],
        )

    def test_exact_100(self, portfolio_100):
        """Normalized values equal raw percentages when total is 100."""
        assert _normalize_percentage(portfolio_100, "AAPL") == pytest.approx(60.0)
        assert _normalize_percentage(portfolio_100, "MSFT") == pytest.approx(40.0)

    def test_over_100(self, portfolio_over_100):
        """Normalized values sum to 100 when raw total exceeds 100."""
        aapl = _normalize_percentage(portfolio_over_100, "AAPL")
        msft = _normalize_percentage(portfolio_over_100, "MSFT")
        assert aapl + msft == pytest.approx(100.0)
        assert aapl == pytest.approx(80 * 100 / 120)

    def test_under_100(self, portfolio_under_100):
        """Normalized values sum to 100 when raw total is below 100."""
        aapl = _normalize_percentage(portfolio_under_100, "AAPL")
        msft = _normalize_percentage(portfolio_under_100, "MSFT")
        assert aapl + msft == pytest.approx(100.0)


class TestDownloadYahooFinanceData:
    """Tests for _download_yahoo_finance_data (mocked)."""

    def test_returns_dataframe_with_ticker_column(self):
        """Returns a DataFrame with required columns."""
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2020, 1, 10, tzinfo=EST)

        with patch("backtest.backtest.yf.Ticker") as mock_ticker:
            mock_instance = MagicMock()
            idx = pd.date_range("2020-01-02", periods=5, freq="B", tz="UTC")
            mock_instance.history.return_value = pd.DataFrame(
                {
                    "Open": [150.0] * 5,
                    "High": [152.0] * 5,
                    "Low": [149.0] * 5,
                    "Close": [151.0] * 5,
                    "Volume": [1000000] * 5,
                    "Dividends": [0.0] * 5,
                    "Stock Splits": [0.0] * 5,
                },
                index=idx,
            )
            mock_ticker.return_value = mock_instance

            df = _download_yahoo_finance_data("AAPL", start, end)

        assert "Ticker" in df.columns
        assert (df["Ticker"] == "AAPL").all()
        assert not df.empty


class TestDownloadPortfolioHistory:
    """Tests for download_portfolio_history (mocked yfinance)."""

    def _make_mock_history(self, ticker, start, end):
        """Create a mock yfinance history DataFrame."""
        dates = pd.date_range(start, end, freq="B", tz="UTC")
        df = pd.DataFrame(
            {
                "Open": [100.0 + i for i in range(len(dates))],
                "High": [102.0 + i for i in range(len(dates))],
                "Low": [99.0 + i for i in range(len(dates))],
                "Close": [101.0 + i for i in range(len(dates))],
                "Volume": [1000000] * len(dates),
                "Dividends": [0.0] * len(dates),
                "Stock Splits": [0.0] * len(dates),
            },
            index=dates,
        )
        return df

    def test_returns_portfolio_data(self, sample_portfolio, sample_dates):
        """Returns a DataFrame with one column per ticker."""
        start, end = sample_dates

        with patch("backtest.backtest.yf.Ticker") as mock_ticker:
            mock_instance = MagicMock()
            mock_instance.history.side_effect = lambda start, end: self._make_mock_history("AAPL", start, end)
            mock_ticker.return_value = mock_instance

            with patch("backtest.backtest.DbCache") as mock_cache_cls:
                mock_cache = MagicMock()
                mock_cache.get_min_max_dates.return_value = (None, None)
                mock_cache.get_cache_data.side_effect = lambda ticker, s, e: self._make_mock_history(ticker, s, e)
                mock_cache.cache_data.return_value = True
                mock_cache_cls.return_value = mock_cache

                data = download_portfolio_history(
                    sample_portfolio, start, end, _initial_investment=100_000, _usd_cad=1.3
                )

        # Should have one column per ticker
        assert list(data.columns) == ["AAPL", "MSFT"]
        assert len(data) > 0


class TestSharesInPortfolio:
    """Tests for shares_in_portfolio."""

    def test_returns_shares_dataframe(self, sample_portfolio, sample_dates):
        """Returns a DataFrame with initial share allocation."""
        start, end = sample_dates

        # Build a simple prices DataFrame
        idx = pd.date_range(start, end, freq="W-FRI")
        data = pd.DataFrame(
            {"AAPL": [150.0] * len(idx), "MSFT": [200.0] * len(idx)},
            index=idx,
        )

        shares = shares_in_portfolio(
            sample_portfolio, data, start, end, initial_investment=100_000, _usd_cad=1.3
        )

        assert list(shares.columns) == ["AAPL", "MSFT"]
        assert start in shares.index
        # 60% of 100000 / 150 = 400 shares AAPL
        assert shares.loc[start, "AAPL"] == pytest.approx(400.0)
        # 40% of 100000 / 200 = 200 shares MSFT
        assert shares.loc[start, "MSFT"] == pytest.approx(200.0)


class TestRebalancePortfolio:
    """Tests for rebalance_portfolio."""

    def _make_simple_prices(self, dates, tickers, base_prices):
        """Build a prices DataFrame."""
        idx = pd.date_range(dates[0], dates[-1], freq="W-FRI")
        data = {}
        for i, ticker in enumerate(tickers):
            data[ticker] = [base_prices[i]] * len(idx)
        return pd.DataFrame(data, index=idx)

    def _make_simple_shares(self, tickers, date, shares):
        """Build a shares DataFrame with one row."""
        index = pd.date_range(datetime.now().date(), periods=0, freq="W")
        df = pd.DataFrame(index=index, columns=tickers)
        df.loc[date] = shares
        return df

    def test_adds_yearly_rows(self):
        """Rebalancing adds a row for each year-end."""
        start = datetime(2020, 6, 1, tzinfo=EST)
        end = datetime(2022, 6, 1, tzinfo=EST)

        portfolio = Portfolio(
            type=PortfolioType.PERCENT,
            holdings=[Holding("AAPL", 60), Holding("MSFT", 40)],
        )
        prices = self._make_simple_prices([start, end], ["AAPL", "MSFT"], [150.0, 200.0])
        shares = self._make_simple_shares(["AAPL", "MSFT"], start, [400.0, 200.0])

        result = rebalance_portfolio(portfolio, prices, shares, start, end)

        # Should have original row + 2 year-end rows (2020-12-31, 2021-12-31)
        assert len(result) >= 3  # original + 2 year-ends
        # Year-end rows should exist
        year_end_2020 = datetime(2020, 12, 31, tzinfo=EST)
        year_end_2021 = datetime(2021, 12, 31, tzinfo=EST)
        assert year_end_2020 in result.index
        assert year_end_2021 in result.index

    def test_no_rebalance_short_period(self):
        """No rebalance rows added when period is less than a year."""
        start = datetime(2020, 6, 1, tzinfo=EST)
        end = datetime(2020, 11, 1, tzinfo=EST)  # < 1 year

        portfolio = Portfolio(
            type=PortfolioType.PERCENT,
            holdings=[Holding("AAPL", 100)],
        )
        prices = self._make_simple_prices([start, end], ["AAPL"], [150.0])
        shares = self._make_simple_shares(["AAPL"], start, [100.0])

        result = rebalance_portfolio(portfolio, prices, shares, start, end)

        # Only the original row should exist
        assert len(result) == 1

    def test_preserves_original_shares(self):
        """Original share allocation is unchanged in rebalanced result."""
        start = datetime(2020, 6, 1, tzinfo=EST)
        end = datetime(2021, 6, 1, tzinfo=EST)

        portfolio = Portfolio(
            type=PortfolioType.PERCENT,
            holdings=[Holding("AAPL", 100)],
        )
        prices = self._make_simple_prices([start, end], ["AAPL"], [150.0])
        shares = self._make_simple_shares(["AAPL"], start, [666.666])

        result = rebalance_portfolio(portfolio, prices, shares, start, end)

        # Original shares at start should be unchanged
        assert result.loc[start, "AAPL"] == pytest.approx(666.666)

    def test_rebalance_single_holding_all_in(self):
        """Single holding at 100% keeps same ratio after rebalance."""
        start = datetime(2020, 6, 1, tzinfo=EST)
        end = datetime(2021, 6, 1, tzinfo=EST)

        portfolio = Portfolio(
            type=PortfolioType.PERCENT,
            holdings=[Holding("QQQ", 100)],
        )
        prices = self._make_simple_prices([start, end], ["QQQ"], [300.0])
        shares = self._make_simple_shares(["QQQ"], start, [333.333])

        result = rebalance_portfolio(portfolio, prices, shares, start, end)

        assert "QQQ" in result.columns
        assert len(result) > 1