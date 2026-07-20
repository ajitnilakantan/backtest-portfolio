from __future__ import annotations

from datetime import datetime, timedelta

import altair as alt
import pandas as pd
from IPython.display import display

from .holding import Portfolio


def detect_environment():
    """Return 'jupyter', 'marimo', or 'cli'."""
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


def format_columns(df, formats):
    """
    Apply formatting to columns.
    formats: dict like {"price": "${:,.2f}", "pct": "{:.1%}"}
    """
    styler = df.style
    for col, fmt in formats.items():
        styler = styler.format({col: fmt})
    return styler


def add_footer(df, footer_dict):
    """
    footer_dict: {"colname": value, ...}
    Adds a footer row at the bottom.
    """
    if footer_dict is None:
        return df

    footer = {col: footer_dict.get(col, "") for col in df.columns}
    footer_df = pd.DataFrame([footer])
    footer_df.index = ["Total"]

    return pd.concat([df, footer_df])


def styled_table(df, formats=None, footer=None, header_style=None, footer_style=None, grid=True, precision=2):
    env = detect_environment()
    df2 = add_footer(df, footer)

    if env == "cli":
        with pd.option_context("display.precision", precision):
            print(df2.to_string())
        return df2

    # Build styler
    styler = df2.style

    if formats:
        for col, fmt in formats.items():
            styler = styler.format({col: fmt})

    if grid:
        styler = styler.set_table_styles(
            [
                {"selector": "table", "props": "border-collapse: collapse;"},
                {"selector": "th, td", "props": "border: 1px solid #ccc; padding: 4px;"},
            ]
        )

    if header_style:
        styler = styler.set_table_styles([{"selector": "th", "props": header_style}], overwrite=False)

    if footer and footer_style:
        styler = styler.set_table_styles([{"selector": "tr#Total", "props": footer_style}], overwrite=False)

    # Jupyter sortable table
    if env == "jupyter":
        styler = styler.set_table_attributes('class="sortable"')

    # The key fix
    display(styler)

    return styler


# ---------------------------------------------------------------------------
# Portfolio math helpers (used by both backtest.py and reporting internals)
# ---------------------------------------------------------------------------


def _portfolio_value(
    portfolio: Portfolio,
    portfolio_data: pd.DataFrame,
    portfolio_num_shares: pd.DataFrame,
    at_date: datetime,
    ticker: str | None = None,
) -> tuple[float, float]:
    """Calculate total investment value at a given date.

    If ticker is None, sums all holdings.  Otherwise returns value for
    the specified ticker only.

    Returns:
        (value, num_shares)
    """
    index = portfolio_data.index.get_indexer([at_date], method="nearest")
    index_num_shares = portfolio_num_shares.index.get_indexer([at_date], method="nearest")
    if not ticker:
        value = 0.0
        num_shares = 0.0
        for fund in portfolio.holdings:
            ticker_value = portfolio_data.iloc[index][fund.ticker].item()
            ticker_num_shares = portfolio_num_shares.iloc[index_num_shares][fund.ticker].item()
            value += ticker_value * ticker_num_shares
            num_shares += portfolio_num_shares.iloc[index_num_shares][fund.ticker].item()
    else:
        ticker_value = portfolio_data.iloc[index][ticker].item()
        ticker_num_shares = portfolio_num_shares.iloc[index_num_shares][ticker].item()
        value = ticker_value * ticker_num_shares
        num_shares = portfolio_num_shares.iloc[index_num_shares][ticker].item()

    return (value, num_shares)


def get_annualized_return(initial: float, final: float, start: datetime, end: datetime) -> float:
    """Calculate the annualized rate of return (as a fraction).

    Uses monthly compounding.  See:
    https://www.calculatorsoup.com/calculators/financial/compound-interest-calculator.php
    """
    n = 12  # Compounded monthly
    t = round((end - start) / timedelta(365, 5, 49, 12), 2)
    A = final
    P = initial
    r = n * ((A / P) ** (1 / (n * t)) - 1)
    return r


# ---------------------------------------------------------------------------
# Reporting / plotting
# ---------------------------------------------------------------------------


def _format_stats(initial: float, final: float, start: datetime, end: datetime) -> str:
    """Return a formatted stats string for a portfolio result."""
    percent = (final - initial) / initial * 100
    r = get_annualized_return(initial, final, start, end)
    return f" = {final - initial:+10,.2f}$ = {percent:+6.2f}% (total) = {r * 100:+6.2f}% (annualized)"


def print_stats(initial: float, final: float, start: datetime, end: datetime) -> None:
    """Print portfolio performance stats."""
    print(_format_stats(initial, final, start, end))


def _print_holdings_table(
    portfolio: Portfolio,
    portfolio_data: pd.DataFrame,
    portfolio_num_shares: pd.DataFrame,
    rebalanced_num_shares: pd.DataFrame,
    start: datetime,
    end: datetime,
    initial_investment: float,
) -> None:
    """Print a detailed holdings breakdown table."""
    print(
        "                      Book           Percent       Current           Annualized Rebalanced           Annualized"
    )
    print(
        "    Holding          Value   #Shares Portfolio       Value   #Shares Return%        Yearly   #Shares Return%"
    )
    for fund in portfolio.holdings:
        book_value, book_num_share = _portfolio_value(
            portfolio, portfolio_data, portfolio_num_shares, start, fund.ticker
        )
        current_value, current_num_share = _portfolio_value(
            portfolio, portfolio_data, portfolio_num_shares, end, fund.ticker
        )
        current_rb_value, current_rb_num_share = _portfolio_value(
            portfolio, portfolio_data, rebalanced_num_shares, end, fund.ticker
        )
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
    portfolio_num_shares: pd.DataFrame,
    rebalanced_num_shares: pd.DataFrame,
    benchmark_portfolio: Portfolio,
    benchmark_data: pd.DataFrame,
    benchmark_num_shares: pd.DataFrame,
    start: datetime,
    end: datetime,
    initial_investment: float,
) -> alt.Chart:
    """Print performance summary, holdings table, and plot portfolio value over time.

    Returns the altair Chart object for further customization or saving.
    """

    # Compute totals
    portfolio_result_total, _ = _portfolio_value(portfolio, portfolio_data, portfolio_num_shares, at_date=end)
    rebalanced_result_total, _ = _portfolio_value(portfolio, portfolio_data, rebalanced_num_shares, at_date=end)
    benchmark_result_total, _ = _portfolio_value(benchmark_portfolio, benchmark_data, benchmark_num_shares, at_date=end)

    # Print summary stats
    print(f"===Portfolio: {portfolio.name}===")
    print(f"From {start.date()} to {end.date()}")
    print("")

    print(f"Initial Investment         = ${initial_investment:10,.2f}")
    print(f"Total S&P 500 Benchmark    = ${benchmark_result_total:10,.2f}", end="")
    print_stats(initial_investment, benchmark_result_total, start, end)
    print(f"Total Portfolio            = ${portfolio_result_total:10,.2f}", end="")
    print_stats(initial_investment, portfolio_result_total, start, end)
    print(f"Total Portfolio Rebalanced = ${rebalanced_result_total:10,.2f}", end="")
    print_stats(initial_investment, rebalanced_result_total, start, end)
    print("Holdings:")

    # Print holdings table
    _print_holdings_table(
        portfolio,
        portfolio_data,
        portfolio_num_shares,
        rebalanced_num_shares,
        start,
        end,
        initial_investment,
    )

    print("\n")

    # Calculated the sum of the portfolio holdings (weighted by the number of shares per holding)
    portfolio_total = pd.DataFrame(index=portfolio_data.index)
    portfolio_total["Total"] = portfolio_data.mul(portfolio_num_shares.reindex(portfolio_data.index, method="pad")).sum(
        axis=1
    )
    portfolio_total["Series"] = "Portfolio"  # Add an explicit distinguishing tracking label to each

    rebalanced_total = pd.DataFrame(index=portfolio_data.index)
    rebalanced_total["Total"] = portfolio_data.mul(
        rebalanced_num_shares.reindex(portfolio_data.index, method="pad")
    ).sum(axis=1)
    rebalanced_total["Series"] = "Rebalanced"  # Add an explicit distinguishing tracking label to each

    benchmark_total = pd.DataFrame(index=benchmark_data.index)
    benchmark_total["Total"] = benchmark_data.mul(benchmark_num_shares.reindex(benchmark_data.index, method="pad")).sum(
        axis=1
    )
    benchmark_total["Series"] = benchmark_portfolio.name  # Add an explicit distinguishing tracking label to each

    # Plot with altair

    # Concatenate them row-wise into one unified DataFrame
    # Run .reset_index() to make the index an accessible column
    # By default, pandas names the index column "index", but we have chosen "Date" above.
    combined = pd.concat([portfolio_total, rebalanced_total, benchmark_total]).reset_index()

    # Map the domain categories to your custom visual configurations
    def first_value(df, column):
        return df[column].loc[df[column].first_valid_index()]

    custom_domain = [
        first_value(portfolio_total, "Series"),
        first_value(rebalanced_total, "Series"),
        first_value(benchmark_total, "Series"),
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
                scale=alt.Scale(domain=custom_domain, range=["#1f77b4", "#ff7f0e", "#2ca02c"]),
                legend=alt.Legend(title="Portfolios"),
            ),
            # Custom Line Patterns ([] = solid, [4,4] = dashed, [1,3] = dotted)
            strokeDash=alt.StrokeDash("Series:N", scale=alt.Scale(domain=custom_domain, range=[[], [4, 4], [1, 3]])),
            # Custom Thickness per line
            strokeWidth=alt.StrokeWidth("Series:N", scale=alt.Scale(domain=custom_domain, range=[4, 2.5, 1.5])),
            # Custom Opacity per line
            opacity=alt.Opacity("Series:N", scale=alt.Scale(domain=custom_domain, range=[0.8, 0.6, 0.5])),
        )
        .properties(
            title=f"Portfolio: {portfolio.name}",
            width=640,
            height=480,
        )
    )

    env = detect_environment()
    if env in ("jupyter", "marimo"):
        display(chart)
    else:
        alt.renderers.enable("browser")
        chart.show()

    return chart
