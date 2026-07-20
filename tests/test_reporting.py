from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from backtest.reporting import (
    _format_stats,
    _portfolio_value,
    _print_holdings_table,
    get_annualized_return,
    plot_results,
    print_stats,
)

EST = ZoneInfo("America/New_York")


class TestPortfolioValue:
    """Tests for _portfolio_value."""

    def test_all_holdings(self, sample_portfolio, sample_prices_df, sample_num_shares, sample_dates):
        """Sums all holding values correctly."""
        start, end = sample_dates
        value, shares = _portfolio_value(sample_portfolio, sample_prices_df, sample_num_shares, at_date=end)
        assert value > 0
        assert shares > 0

    def test_single_ticker(self, sample_portfolio, sample_prices_df, sample_num_shares, sample_dates):
        """Returns value for a single specified ticker."""
        start, end = sample_dates
        aapl_value, aapl_shares = _portfolio_value(
            sample_portfolio, sample_prices_df, sample_num_shares, at_date=end, ticker="AAPL"
        )
        msft_value, msft_shares = _portfolio_value(
            sample_portfolio, sample_prices_df, sample_num_shares, at_date=end, ticker="MSFT"
        )

        # AAPL: 400 shares, MSFT: 200 shares
        assert aapl_shares == pytest.approx(400.0)
        assert msft_shares == pytest.approx(200.0)
        assert aapl_value > 0
        assert msft_value > 0

        # Sum should match all_holdings test
        total_value, _ = _portfolio_value(sample_portfolio, sample_prices_df, sample_num_shares, at_date=end)
        assert aapl_value + msft_value == pytest.approx(total_value)


class TestAnnualizedReturn:
    """Tests for get_annualized_return."""

    def test_flat_return(self):
        """Same start and end value returns 0."""
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2021, 1, 1, tzinfo=EST)
        r = get_annualized_return(100.0, 100.0, start, end)
        assert r == pytest.approx(0.0, abs=1e-10)

    def test_positive_return(self):
        """10% gain over 1 year."""
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2021, 1, 1, tzinfo=EST)
        r = get_annualized_return(100.0, 110.0, start, end)
        assert r == pytest.approx(0.10, abs=0.01)

    def test_loss_return(self):
        """Negative return for a loss."""
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2021, 1, 1, tzinfo=EST)
        r = get_annualized_return(100.0, 90.0, start, end)
        assert r < 0

    def test_multi_year_return(self):
        """Computes annualized return over multiple years."""
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2023, 1, 1, tzinfo=EST)
        # Doubling over 3 years → annualized ~26%
        r = get_annualized_return(100.0, 200.0, start, end)
        assert r > 0.20
        assert r < 0.30

    def test_short_period(self):
        """Works for periods shorter than a year."""
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2020, 2, 1, tzinfo=EST)
        r = get_annualized_return(100.0, 101.0, start, end)
        # ~1% gain over ~1 month → annualized ~12.7%
        assert r > 0.05
        assert r < 0.20


class TestFormatStats:
    """Tests for _format_stats."""

    def test_format_includes_key_elements(self):
        """String contains dollar amount, percent, and annualized labels."""
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2021, 1, 1, tzinfo=EST)
        result = _format_stats(100.0, 110.0, start, end)
        assert "+" in result
        assert "$" in result
        assert "%" in result
        assert "annualized" in result

    def test_print_stats_does_not_raise(self, capsys):
        """print_stats runs without error and prints something."""
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2021, 1, 1, tzinfo=EST)
        print_stats(100.0, 110.0, start, end)
        captured = capsys.readouterr()
        assert "$" in captured.out


class TestPrintHoldingsTable:
    """Smoke tests for _print_holdings_table."""

    def test_does_not_raise(
        self,
        sample_portfolio,
        sample_prices_df,
        sample_num_shares,
        sample_dates,
        capsys,
    ):
        """Prints the holdings table without error."""
        start, end = sample_dates
        _print_holdings_table(
            sample_portfolio,
            sample_prices_df,
            sample_num_shares,
            sample_num_shares,  # same as un-rebalanced for this test
            start,
            end,
            initial_investment=100_000.0,
        )
        captured = capsys.readouterr()
        # Should print both ticker names
        assert "AAPL" in captured.out
        assert "MSFT" in captured.out


class TestPlotResults:
    """Smoke tests for plot_results."""

    def test_plot_results_does_not_raise(
        self,
        sample_portfolio,
        sample_prices_df,
        sample_num_shares,
        benchmark_portfolio,
        sample_dates,
        capsys,
    ):
        """plot_results runs without error and returns an altair Chart."""
        start, end = sample_dates

        # Create benchmark data matching the same index
        benchmark_df = pd.DataFrame(
            {"^GSPC": [4000.0 + i * 2 for i in range(len(sample_prices_df))]},
            index=sample_prices_df.index,
        )
        # Create benchmark shares DataFrame with matching index
        benchmark_shares = pd.DataFrame(index=sample_num_shares.index, columns=["^GSPC"])
        benchmark_shares.iloc[0] = [25.0]  # 100000 / 4000 = 25

        chart = plot_results(
            sample_portfolio,
            sample_prices_df,
            sample_num_shares,
            sample_num_shares,  # rebalanced = same as original
            benchmark_portfolio,
            benchmark_df,
            benchmark_shares,
            start,
            end,
            initial_investment=100_000.0,
        )
        captured = capsys.readouterr()
        assert "Test Portfolio" in captured.out
        assert "S&P 500 Benchmark" in captured.out
        assert chart is not None
