"""
Portfolio reporting and plotting utilities.

This module provides functions for generating comprehensive portfolio performance
reports, including formatted tables, statistics, and interactive Altair visualizations.

Key features:
- Environment-aware table styling (Jupyter, Marimo, CLI)
- Performance statistics calculation with annualized returns
- Detailed holdings breakdown tables
- Interactive portfolio value plots with benchmark comparison

The module is designed to work seamlessly across different execution contexts,
automatically switching between interactive notebooks and command-line interfaces.
"""

from __future__ import annotations

import os
from datetime import datetime

import altair as alt
import pandas as pd
from IPython.display import display

from .backtest import get_annualized_return, get_numrebalancedshares_column, get_numshares_column, portfolio_value
from .holding import Portfolio


def detect_environment():
    """Detect and return the current execution environment.

    Checks for 'pytest', 'marimo', then 'jupyter', then falls back to 'cli'.

    Returns:
        str: 'pytest', 'jupyter', 'marimo', or 'cli' indicating the execution context.
    """
    if "PYTEST_CURRENT_TEST" in os.environ:
        return "pytest"

    try:
        import marimo as mo

        if mo.running_in_notebook():
            # if os.environ.get("MARIMO_RUNNING") == "1":
            return "marimo"
    except Exception:
        pass

    try:
        from IPython import get_ipython

        shell = get_ipython()
        if shell and "ipykernel" in str(type(shell)):
            return "jupyter"
    except Exception:
        pass

    return "cli"


# ---------------------------------------------------------------------------
# Reporting / plotting
# ---------------------------------------------------------------------------


def _format_stats(initial: float, final: float, start: datetime, end: datetime) -> str:
    """Format portfolio performance statistics into a readable string.

    Args:
        initial: Starting portfolio value.
        final: Ending portfolio value.
        start: Start date of the period.
        end: End date of the period.

    Returns:
        str: Formatted string containing total change, total percent change,
            and annualized percent change (all as a single formatted string).
    """
    percent = (final - initial) / initial * 100
    r = get_annualized_return(initial, final, start, end)
    return f" = {final - initial:+10,.2f}$ = {percent:+6.2f}% (total) = {r * 100:+6.2f}% (annualized)"


def _print_stats(initial: float, final: float, start: datetime, end: datetime) -> None:
    """Print formatted portfolio performance statistics.

    Args:
        initial: Starting portfolio value.
        final: Ending portfolio value.
        start: Start date of the period.
        end: End date of the period.

    Returns:
        None
    """
    print(_format_stats(initial, final, start, end))


def _print_holdings_table(
    portfolio: Portfolio,
    portfolio_data: pd.DataFrame,
    start: datetime,
    end: datetime,
    initial_investment: float,
) -> None:
    """Print a detailed holdings breakdown table comparing original and rebalanced portfolios.

    Args:
        portfolio: Portfolio object containing holdings information.
        portfolio_data: DataFrame with portfolio asset prices by date.
        portfolio_num_shares: DataFrame with portfolio share counts by date.
        rebalanced_num_shares: DataFrame with rebalanced share counts by date.
        start: Start date for the report period.
        end: End date for the report period.
        initial_investment: Initial investment amount used for percentage calculations.

    Returns:
        None
    """
    print("                      Book           Percent       Current           Annualized Rebalanced           Annualized")
    print("    Holding          Value   #Shares Portfolio       Value   #Shares Return%        Yearly   #Shares Return%")
    for fund in portfolio.holdings:
        book_value, book_num_share = portfolio_value(portfolio, portfolio_data, rebalanced=False, at_date=start, ticker=fund.ticker)
        current_value, current_num_share = portfolio_value(portfolio, portfolio_data, rebalanced=False, at_date=end, ticker=fund.ticker)
        current_rb_value, current_rb_num_share = portfolio_value(portfolio, portfolio_data, rebalanced=True, at_date=end, ticker=fund.ticker)
        book_str = "{:13,.2f}$ {:9.1f}".format(book_value, book_num_share)
        current_str = "{:13,.2f}$ {:9.1f}".format(current_value, current_num_share)
        current_rb_str = "{:13,.2f}$ {:9.1f}".format(current_rb_value, current_rb_num_share)
        book_percent = book_value / initial_investment * 100
        current_change = 100 * get_annualized_return(book_value, current_value, start, end)
        current_rb_change = 100 * get_annualized_return(book_value, current_rb_value, start, end)
        print(
            "{:>11} {:s} {:>5.1f}% {:s} {:>5.1f}% {:s} {:>5.1f}%".format(
                fund.ticker,
                book_str,
                book_percent,
                current_str,
                current_change,
                current_rb_str,
                current_rb_change,
            )
        )


def plot_results(
    portfolio: Portfolio,
    portfolio_data: pd.DataFrame,
    benchmark_portfolio: Portfolio,
    benchmark_data: pd.DataFrame,
    start: datetime,
    end: datetime,
    initial_investment: float,
) -> alt.Chart:
    """Generate a comprehensive portfolio performance report with plots.

    This function prints performance summary statistics, displays a detailed
    holdings breakdown table comparing original vs rebalanced portfolios,
    and renders an interactive line chart of portfolio value over time.

    Args:
        portfolio: Original portfolio object.
        portfolio_data: DataFrame with portfolio asset prices by date.
        benchmark_portfolio: Benchmark portfolio object (e.g., S&P 500 index).
        benchmark_data: DataFrame with benchmark asset prices by date.
        start: Start date for the report period.
        end: End date for the report period.
        initial_investment: Initial investment amount used for percentage calculations.

    Returns:
        altair.Chart: An interactive Altair Chart object that can be further
            customized or saved for display in Jupyter/Marimo environments.

    Side effects:
        Prints portfolio performance summary to stdout.
        Displays interactive chart in Jupyter/Marimo environments.
        Shows chart using browser renderer in CLI environments.
    """

    # Compute totals
    portfolio_result_total, _ = portfolio_value(portfolio, portfolio_data, rebalanced=False, at_date=end)
    rebalanced_result_total, _ = portfolio_value(portfolio, portfolio_data, rebalanced=True, at_date=end)
    benchmark_result_total, _ = portfolio_value(benchmark_portfolio, benchmark_data, rebalanced=False, at_date=end)

    # Print summary stats
    print(f"===Portfolio: {portfolio.name}===")
    print(f"From {start.date()} to {end.date()}")
    print("")

    print(f"Initial Investment         = ${initial_investment:10,.2f}")
    print(f"Total S&P 500 Benchmark    = ${benchmark_result_total:10,.2f}", end="")
    _print_stats(initial_investment, benchmark_result_total, start, end)
    print(f"Total Portfolio            = ${portfolio_result_total:10,.2f}", end="")
    _print_stats(initial_investment, portfolio_result_total, start, end)
    print(f"Total Portfolio Rebalanced = ${rebalanced_result_total:10,.2f}", end="")
    _print_stats(initial_investment, rebalanced_result_total, start, end)
    print("Holdings:")

    # Print holdings table
    _print_holdings_table(
        portfolio,
        portfolio_data,
        start,
        end,
        initial_investment,
    )

    print("\n")

    # Calculated the sum of the portfolio holdings (weighted by the number of shares per holding)
    ticker_cols = [fund.ticker for fund in portfolio.holdings]
    num_cols = [get_numshares_column(ticker) for ticker in ticker_cols]
    # -- Create dataframes for total, rebalanced, and benchmark
    # Forward fill columns individually, multiply them, then sum
    df_left = portfolio_data[ticker_cols].ffill().fillna(0)
    df_right = portfolio_data[num_cols].ffill().fillna(0)
    total_portfolio = pd.DataFrame(index=portfolio_data.index)
    total_portfolio["Total"] = (df_left.values * df_right.values).sum(axis=1)
    total_portfolio["Series"] = portfolio.name  # Add an explicit distinguishing tracking label to each

    # Calculated the sum of the portfolio holdings (rebalanced yearly)
    ticker_cols = [fund.ticker for fund in portfolio.holdings]
    num_cols = [get_numrebalancedshares_column(ticker) for ticker in ticker_cols]
    df_left = portfolio_data[ticker_cols].ffill().fillna(0)
    df_right = portfolio_data[num_cols].ffill().fillna(0)
    total_rebalanced = pd.DataFrame(index=portfolio_data.index)
    total_rebalanced["Total"] = (df_left.values * df_right.values).sum(axis=1)
    total_rebalanced["Series"] = portfolio.name + ": Rebalanced"  # Add an explicit distinguishing tracking label to each

    # Calculated the sum of the benchmark portfolio holdings
    ticker_cols = [fund.ticker for fund in benchmark_portfolio.holdings]
    num_cols = [get_numshares_column(ticker) for ticker in ticker_cols]
    df_left = benchmark_data[ticker_cols].ffill().fillna(0)
    df_right = benchmark_data[num_cols].ffill().fillna(0)
    total_benchmark = pd.DataFrame(index=benchmark_data.index)
    total_benchmark["Total"] = (df_left.values * df_right.values).sum(axis=1)
    total_benchmark["Series"] = "Benchmark: " + benchmark_portfolio.name  # Add an explicit distinguishing tracking label to each

    # Plot with altair

    # Concatenate them row-wise into one unified DataFrame
    # Run .reset_index() to make the index an accessible column
    # By default, pandas names the index column "index", but we have chosen "Date" above.
    combined = pd.concat([total_portfolio, total_rebalanced, total_benchmark]).reset_index()

    # Map the domain categories to your custom visual configurations
    def first_value(df, column):
        if df[column].empty:
            return None
        else:
            return df[column].loc[df[column].first_valid_index()]

    custom_domain = [
        first_value(total_benchmark, "Series"),
        first_value(total_portfolio, "Series"),
        first_value(total_rebalanced, "Series"),
    ]

    chart = (
        alt.Chart(combined)
        .mark_line()
        .encode(
            x=alt.X("Date:T", title="Date", axis=alt.Axis(format="%b '%y", title="Timeline")),
            y=alt.Y(
                "Total:Q",
                title="Portfolio Value ($)",
                scale=alt.Scale(zero=False),
                axis=alt.Axis(format="$.2f", title="Value"),
            ),
            # Custom Colors
            color=alt.Color(
                "Series:N",
                # scale=alt.Scale(domain=custom_domain, range=["#1f77b4", "#ff7f0e", "#2ca02c"]),
                # Yellow, BrightBlue, Blue, BrightGreen, Green
                scale=alt.Scale(domain=custom_domain, range=["#C19C00", "#3B78FF", "#0037DA", "#16C60C", "#13A10E"]),
                legend=alt.Legend(title="Portfolios"),
            ),
            # Custom Line Patterns ([] = solid, [4,4] = dashed, [1,3] = dotted)
            strokeDash=alt.StrokeDash("Series:N", scale=alt.Scale(domain=custom_domain, range=[[], [], [1, 3], [], [1, 3]])),
            # Custom Thickness per line
            strokeWidth=alt.StrokeWidth("Series:N", scale=alt.Scale(domain=custom_domain, range=[1, 2.5, 1.5, 2.5, 1.5])),
            # Custom Opacity per line
            opacity=alt.Opacity("Series:N", scale=alt.Scale(domain=custom_domain, range=[0.8, 0.5, 0.5, 0.5, 0.5])),
        )
        .properties(
            title=f"Portfolio: {portfolio.name}",
            width=640,
            height=480,
        )
    )

    env = detect_environment()
    if env in ("pytest"):
        pass
    elif env in ("jupyter", "marimo"):
        display(chart)
    else:
        alt.renderers.enable("browser")
        chart.show()

    return chart
