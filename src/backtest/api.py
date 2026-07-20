from datetime import datetime
from typing import Final

import altair as alt
import pandas as pd

from .backtest import Log, download_portfolio_history, rebalance_portfolio, shares_in_portfolio
from .holding import Portfolio, default_benchmark_portfolios, default_portfolios
from .reporting import plot_results


class Backtest:
    # Class Static
    DEFAULT_BENCHMARK_PORTFOLIOS: Final = default_benchmark_portfolios
    DEFAULT_PORTFOLIOS: Final = default_portfolios
    DEFAULT_INITIAL_INVESTMENT: Final = 1_000_000.00
    DEFAULT_USD_CAD: Final = 1.3

    @staticmethod
    def run(
        portfolios: list[Portfolio | None],
        benchmark_portfolio: Portfolio,
        start: datetime,
        end: datetime,
        initial_investment=DEFAULT_INITIAL_INVESTMENT,
        usd_cad=DEFAULT_USD_CAD,
    ):
        # Baseline benchmark
        if not benchmark_portfolio:
            benchmark_portfolio = default_benchmark_portfolios[0]
        benchmark_data = download_portfolio_history(benchmark_portfolio, start, end, initial_investment, usd_cad)
        benchmark_num_shares = shares_in_portfolio(
            benchmark_portfolio, benchmark_data, start, end, initial_investment, usd_cad
        )

        pportfolios = [p for p in portfolios if p is not None]  # filter out Nones
        for portfolio in pportfolios[0:1]:
            portfolio_data = download_portfolio_history(portfolio, start, end, initial_investment, usd_cad)
            portfolio_num_shares = shares_in_portfolio(
                portfolio, portfolio_data, start, end, initial_investment, usd_cad
            )
            rebalanced_num_shares = rebalance_portfolio(portfolio, portfolio_data, portfolio_num_shares, start, end)

            plot_results(
                portfolio,
                portfolio_data,
                portfolio_num_shares,
                rebalanced_num_shares,
                benchmark_portfolio,
                benchmark_data,
                benchmark_num_shares,
                start,
                end,
                initial_investment,
            )

    @staticmethod
    def log(msg: str) -> None:
        Log.log(msg)

    @staticmethod
    def download_history(
        portfolio: Portfolio,
        start: datetime,
        end: datetime,
        initial_investment=DEFAULT_INITIAL_INVESTMENT,
        usd_cad=DEFAULT_USD_CAD,
    ) -> pd.DataFrame:
        return download_portfolio_history(portfolio, start, end, initial_investment, usd_cad)

    @staticmethod
    def initial_share_allocation(
        portfolio: Portfolio,
        portfolio_data: pd.DataFrame,
        start: datetime,
        end: datetime,
        initial_investment=DEFAULT_INITIAL_INVESTMENT,
        usd_cad=DEFAULT_USD_CAD,
    ) -> pd.DataFrame:
        return shares_in_portfolio(portfolio, portfolio_data, start, end, initial_investment, usd_cad)

    @staticmethod
    def rebalance(
        portfolio: Portfolio,
        portfolio_data: pd.DataFrame,
        portfolio_num_shares: pd.DataFrame,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        return rebalance_portfolio(portfolio, portfolio_data, portfolio_num_shares, start, end)

    @staticmethod
    def display_results(
        portfolio: Portfolio,
        portfolio_data: pd.DataFrame,
        portfolio_num_shares: pd.DataFrame,
        rebalanced_num_shares: pd.DataFrame,
        benchmark_portfolio: Portfolio,
        benchmark_data: pd.DataFrame,
        benchmark_num_shares: pd.DataFrame,
        start: datetime,
        end: datetime,
        initial_investment: float,
    ) -> alt.Chart:
        return plot_results(
            portfolio,
            portfolio_data,
            portfolio_num_shares,
            rebalanced_num_shares,
            benchmark_portfolio,
            benchmark_data,
            benchmark_num_shares,
            start,
            end,
            initial_investment,
        )
