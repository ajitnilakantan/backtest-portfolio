from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import altair as alt
import pytest

from backtest.backtest import get_numrebalancedshares_column, portfolio_value
from backtest.reporting import (
    _format_stats,
    _print_holdings_table,
    _print_stats,
    get_annualized_return,
    plot_results,
)

EST = ZoneInfo("America/New_York")


class TestPortfolioValue:
    """Tests for portfolio value calculations."""

    def test_all_holdings(self, sample_portfolio, sample_portfolio_data, sample_dates):
        _, end = sample_dates
        value, shares = portfolio_value(sample_portfolio, sample_portfolio_data, rebalanced=False, at_date=end)

        assert value > 0
        assert shares == pytest.approx(600.0)

    def test_single_tickers_sum_to_total(self, sample_portfolio, sample_portfolio_data, sample_dates):
        _, end = sample_dates
        aapl_value, aapl_shares = portfolio_value(
            sample_portfolio,
            sample_portfolio_data,
            rebalanced=False,
            at_date=end,
            ticker="AAPL",
        )
        msft_value, msft_shares = portfolio_value(
            sample_portfolio,
            sample_portfolio_data,
            rebalanced=False,
            at_date=end,
            ticker="MSFT",
        )
        total_value, _ = portfolio_value(sample_portfolio, sample_portfolio_data, rebalanced=False, at_date=end)

        assert aapl_shares == pytest.approx(400.0)
        assert msft_shares == pytest.approx(200.0)
        assert aapl_value + msft_value == pytest.approx(total_value)

    def test_rebalanced_uses_rebalanced_share_column(self, sample_portfolio, sample_portfolio_data, sample_dates):
        _, end = sample_dates
        data = sample_portfolio_data.copy()
        data[get_numrebalancedshares_column("AAPL")] = 100.0

        original_value, original_shares = portfolio_value(sample_portfolio, data, rebalanced=False, at_date=end, ticker="AAPL")
        rebalanced_value, rebalanced_shares = portfolio_value(sample_portfolio, data, rebalanced=True, at_date=end, ticker="AAPL")

        assert original_shares == pytest.approx(400.0)
        assert rebalanced_shares == pytest.approx(100.0)
        assert rebalanced_value == pytest.approx(original_value / 4)


class TestAnnualizedReturn:
    """Tests for annualized return calculations."""

    def test_flat_return(self):
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2021, 1, 1, tzinfo=EST)
        assert get_annualized_return(100.0, 100.0, start, end) == pytest.approx(0.0, abs=1e-10)

    def test_positive_return(self):
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2021, 1, 1, tzinfo=EST)
        assert get_annualized_return(100.0, 110.0, start, end) == pytest.approx(0.10, abs=0.01)

    def test_loss_return(self):
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2021, 1, 1, tzinfo=EST)
        assert get_annualized_return(100.0, 90.0, start, end) < 0

    def test_multi_year_return(self):
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2023, 1, 1, tzinfo=EST)
        result = get_annualized_return(100.0, 200.0, start, end)
        assert 0.20 < result < 0.30

    def test_short_period(self):
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2020, 2, 1, tzinfo=EST)
        result = get_annualized_return(100.0, 101.0, start, end)
        assert 0.05 < result < 0.20


class TestFormatStats:
    """Tests for formatted performance statistics."""

    def test_format_includes_key_elements(self):
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2021, 1, 1, tzinfo=EST)
        result = _format_stats(100.0, 110.0, start, end)

        assert "+" in result
        assert "$" in result
        assert "%" in result
        assert "annualized" in result

    def test_print_stats_outputs_value(self, capsys):
        start = datetime(2020, 1, 1, tzinfo=EST)
        end = datetime(2021, 1, 1, tzinfo=EST)

        _print_stats(100.0, 110.0, start, end)

        assert "$" in capsys.readouterr().out


class TestPrintHoldingsTable:
    """Smoke tests for the holdings table."""

    def test_prints_each_ticker(self, sample_portfolio, sample_portfolio_data, sample_dates, capsys):
        start, end = sample_dates

        _print_holdings_table(sample_portfolio, sample_portfolio_data, start, end, initial_investment=100_000.0)

        output = capsys.readouterr().out
        assert "AAPL" in output
        assert "MSFT" in output


class TestPlotResults:
    """Smoke tests for portfolio charts."""

    def test_returns_chart_and_prints_names(
        self,
        sample_portfolio,
        sample_portfolio_data,
        benchmark_portfolio,
        sample_benchmark_data,
        sample_dates,
        capsys,
    ):
        start, end = sample_dates

        chart = plot_results(
            sample_portfolio,
            sample_portfolio_data,
            benchmark_portfolio,
            sample_benchmark_data,
            start,
            end,
            initial_investment=100_000.0,
        )

        output = capsys.readouterr().out
        assert "Test Portfolio" in output
        assert "S&P 500 Benchmark" in output
        assert isinstance(chart, alt.Chart)
