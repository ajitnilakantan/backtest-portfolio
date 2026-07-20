from datetime import datetime
from zoneinfo import ZoneInfo

from InquirerPy import inquirer
from InquirerPy.base.control import Choice

# from backtest.backtest import download_portfolio_history, rebalance_portfolio
# from backtest.holding import default_benchmark_portfolio, default_portfolios
# from backtest.reporting import plot_results
# from backtest import default_benchmark_portfolio, default_portfolios, download_portfolio_history, plot_results, rebalance_portfolio
from backtest import Backtest


def main():
    # Dollars initially invested
    initial_investment = 1_000_000.0
    # USD to CAD exchange rate
    usd_cad = 1.3

    # Collect data for this time period
    start = datetime(2021, 1, 1).replace(tzinfo=ZoneInfo("America/New_York"))
    end = datetime(2025, 5, 1).replace(tzinfo=ZoneInfo("America/New_York"))

    # Baseline benchmark
    default_benchmark_portfolio = Backtest.DEFAULT_BENCHMARK_PORTFOLIOS[0]
    benchmark_data = Backtest.download_history(default_benchmark_portfolio, start, end, initial_investment, usd_cad)
    benchmark_num_shares = Backtest.initial_share_allocation(
        default_benchmark_portfolio, benchmark_data, start, end, initial_investment, usd_cad
    )

    # Choose portfolio
    portfolios = Backtest.DEFAULT_PORTFOLIOS
    choices = [Choice(name=portfolio.name, value=index) for index, portfolio in enumerate(portfolios)]
    selected_index = inquirer.select(message="Choose portfolio:", choices=choices).execute()
    portfolio = portfolios[selected_index]

    portfolio_data = Backtest.download_history(portfolio, start, end, initial_investment, usd_cad)
    portfolio_num_shares = Backtest.initial_share_allocation(
        portfolio, portfolio_data, start, end, initial_investment, usd_cad
    )
    rebalanced_num_shares = Backtest.rebalance(portfolio, portfolio_data, portfolio_num_shares, start, end)

    Backtest.display_results(
        portfolio,
        portfolio_data,
        portfolio_num_shares,
        rebalanced_num_shares,
        default_benchmark_portfolio,
        benchmark_data,
        benchmark_num_shares,
        start,
        end,
        initial_investment,
    )


if __name__ == "__main__":
    main()
