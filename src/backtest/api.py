"""
API for running backtests on investment portfolios.

This module provides a static utility class `Backtest` that wraps core
backtesting functionality, including downloading portfolio history,
calculating share allocations, rebalancing portfolios, and visualizing
results against benchmark portfolios.
"""

from datetime import datetime
from typing import Final

import altair as alt
import pandas as pd

from .backtest import Log, datetime_nyc, download_portfolio
from .holding import Portfolio, default_benchmark_portfolios, default_portfolios
from .reporting import plot_results


class Backtest:
    """Static utility class for backtesting operations.

    Provides high-level methods for running backtests, downloading portfolio
    history, calculating initial share allocations, rebalancing holdings,
    and visualizing performance against benchmarks.
    """

    # Class Static
    DEFAULT_BENCHMARK_PORTFOLIOS: Final[list[Portfolio]] = default_benchmark_portfolios
    DEFAULT_PORTFOLIOS: Final[list[Portfolio]] = default_portfolios
    DEFAULT_INITIAL_INVESTMENT: Final[float] = Portfolio.DEFAULT_INITIAL_INVESTMENT
    DEFAULT_USD_CAD: Final[float] = Portfolio.DEFAULT_USD_CAD

    @staticmethod
    def log(msg: str) -> None:
        """Log a message to the console.

        Args:
            msg: Message to log.
        """
        Log.log(msg)

    @staticmethod
    def run(
        portfolios: list[Portfolio | None],
        benchmark_portfolio: Portfolio,
        start: datetime,
        end: datetime,
        initial_investment=DEFAULT_INITIAL_INVESTMENT,
        usd_cad=DEFAULT_USD_CAD,
    ):
        """Run a backtest for the provided portfolios.

        Downloads history for the main portfolios and a benchmark, calculates
        initial and rebalanced share allocations, and generates performance
        plots.

        Args:
            portfolios: List of Portfolio objects to backtest. None entries
                are filtered out.
            benchmark_portfolio: Benchmark Portfolio for comparison.
                If None, the first default benchmark portfolio is used.
            start: Backtest start datetime.
            end: Backtest end datetime.
            initial_investment: Initial investment amount (default: 1_000_000.00).
            usd_cad: USD to CAD exchange rate (default: 1.3).

        Side effects:
            Generates Altair charts for portfolio performance vs benchmark.
        """
        start = datetime_nyc(start)
        end = datetime_nyc(end)
        # Baseline benchmark
        if not benchmark_portfolio:
            benchmark_portfolio = default_benchmark_portfolios[0]
        portfolios: list[Portfolio] = [p for p in portfolios if p is not None]  # filter out Nones
        portfolio = portfolios[0]

        # Download data
        portfolio_data = Backtest.download_portfolio(portfolio, start, end, initial_investment, usd_cad)
        benchmark_data = Backtest.download_portfolio(benchmark_portfolio, start, end, initial_investment, usd_cad)

        # Display results and chart
        Backtest.display_results(
            portfolio,
            portfolio_data,
            benchmark_portfolio,
            benchmark_data,
            start,
            end,
            initial_investment,
        )


    @staticmethod
    def download_portfolio(
        portfolio: Portfolio,
        start: datetime,
        end: datetime,
        initial_investment: float = Portfolio.DEFAULT_INITIAL_INVESTMENT,
        usd_cad: float = Portfolio.DEFAULT_USD_CAD,
    ) -> pd.DataFrame:
        """Download historical portfolio data for a given period.

        Retrieves price data for all holdings in the portfolio and returns
        a DataFrame with adjusted close prices and timestamps.

        Args:
            portfolio: Portfolio containing holdings to download data for.
            start: Start datetime for the historical data.
            end: End datetime for the historical data.
            initial_investment: Initial investment amount (default: 1_000_000.00).
            usd_cad: USD to CAD exchange rate (default: 1.3).

        Returns:
            DataFrame with columns: Date, Close, Ticker, and adjusted close prices.
        """
        start = datetime_nyc(start)
        end = datetime_nyc(end)
        return download_portfolio(portfolio, start, end, initial_investment, usd_cad)

    @staticmethod
    def display_results(
        portfolio: Portfolio,
        portfolio_data: pd.DataFrame,
        benchmark_portfolio: Portfolio,
        benchmark_data: pd.DataFrame,
        start: datetime,
        end: datetime,
        initial_investment: float,
    ) -> alt.Chart:
        """Generate visualization of portfolio performance metrics.

        Creates Altair charts comparing portfolio and benchmark performance
        including value growth, share allocations, and rebalancing actions.

        Args:
            portfolio: Portfolio being analyzed.
            portfolio_data: Historical portfolio price data.
            portfolio_num_shares: Initial share allocation series.
            rebalanced_num_shares: Post-rebalancing share allocation series.
            benchmark_portfolio: Benchmark portfolio for comparison.
            benchmark_data: Historical benchmark price data.
            benchmark_num_shares: Benchmark share allocation series.
            start: Analysis period start.
            end: Analysis period end.
            initial_investment: Starting investment value.

        Returns:
            Configured Altair Chart object ready for rendering.

        Note:
            Visualizations include multiple comparative charts showing
            value trajectories, holdings, and rebalancing frequency.
        """
        start = datetime_nyc(start)
        end = datetime_nyc(end)
        return plot_results(
            portfolio,
            portfolio_data,
            benchmark_portfolio,
            benchmark_data,
            start,
            end,
            initial_investment,
        )
