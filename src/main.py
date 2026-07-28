"""Backtesting Portfolio Management - Main Entry Point

This module provides the main entry point for running backtesting simulations
for a portfolio management system. It allows users to select portfolios,
download historical data, perform rebalancing calculations, and display
results compared to a default benchmark portfolio.
"""

from datetime import datetime

from InquirerPy import inquirer
from InquirerPy.base.control import Choice

# from backtest.backtest import download_portfolio_history, rebalance_portfolio
# from backtest.holding import default_benchmark_portfolio, default_portfolios
# from backtest.reporting import plot_results
# from backtest import default_benchmark_portfolio, default_portfolios, download_portfolio_history, plot_results, rebalance_portfolio
from backtest import Backtest, Portfolio


def main():
    """Run a backtesting portfolio simulation.

    This function orchestrates a complete backtesting workflow:
    - Downloads historical price data for a default benchmark portfolio
    - Displays a list of available portfolios and prompts the user to select one
    - Downloads historical data for the selected portfolio
    - Calculates initial share allocations based on the available capital
    - Simulates portfolio rebalancing over the specified time period
    - Displays comprehensive performance results comparing the selected portfolio
      against the benchmark portfolio

    Args:
        None: This function takes no parameters. It executes a complete
            backtesting simulation with hardcoded configuration values.

    Returns:
        None: The function performs all operations internally and displays
            results to the console. No value is returned.

    Raises:
        None: No exceptions are explicitly raised by this function. Exceptions
            that may occur include:
            - Network errors when downloading portfolio data
            - InquirerPy errors for user selection
            - Any exceptions raised by the Backtest class methods

    Side Effects:
        - Displays interactive prompts for portfolio selection
        - Creates console output showing performance metrics and visualizations
        - Potentially generates or displays plot results (depending on implementation)
    """
    initial_investment = 1_000_000.0

    # Collect data for this time period
    start = datetime(2021, 1, 1)
    end = datetime(2025, 5, 1)

    # Baseline benchmark
    default_benchmark_portfolio = Backtest.DEFAULT_BENCHMARK_PORTFOLIOS[0]

    # Choose portfolio
    portfolios = [
        Portfolio("test", "BRKA 100"),
    ] + Backtest.DEFAULT_PORTFOLIOS
    choices = [Choice(name=portfolio.name, value=index) for index, portfolio in enumerate(portfolios)]
    selected_index = inquirer.select(message="Choose portfolio:", choices=choices).execute()
    portfolio = portfolios[selected_index]

    # Run the backtest
    Backtest.run([portfolio], default_benchmark_portfolio, start, end, initial_investment)


if __name__ == "__main__":
    main()
