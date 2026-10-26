"""Core Backtesting Functions and Classes

This module provides core functionality for backtesting portfolio performance,
including data downloading, portfolio rebalancing, and result calculations.
Classes
-------
Log : Simple logging class
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
from dateutil import rrule

from .db_cache import DbCache
from .holding import Portfolio


class Log:
    @staticmethod
    def log(msg: str) -> None:
        """Print a message to the console.

        Args:
            msg: Message string to print.
        """
        print(msg)

    @staticmethod
    def print_df(df: pd.DataFrame) -> None:
        """Print a DataFrame to the console.
        Args:
            df: DataFrame to print.
        """
        with pd.option_context("display.max_rows", None, "display.max_columns", None):
            print(df)


def datetime_nyc(dt: datetime | date) -> datetime:
    if isinstance(dt, datetime):
        return dt.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
    else:
        return datetime.combine(dt, time.min, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)


def get_numshares_column(ticker: str) -> str:
    return f"{ticker}#num_shares"


def get_numrebalancedshares_column(ticker: str) -> str:
    return f"{ticker}#num__rebalanced_shares"


def _get_df_column_value(df: pd.DataFrame, at_date, column: str, default=0.0) -> float:
    # Ensure index is a sorted DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        df = df.copy()
        df.index = pd.to_datetime(df.index)

    if not df.index.is_monotonic_increasing:
        df = df.sort_index()

    # Forward-fill non-None values
    # Reindex to closest date using 'nearest'
    # Handle cases where target is outside bounds or no valid value exists
    try:
        filled_series = df[column].ffill()

        # If all values are NaN/None, return default
        if filled_series.dropna().empty:
            return default

        # Find value at nearest date in the past
        position = filled_series.index.searchsorted(pd.Timestamp(at_date), side="right") - 1
        if position < 0:
            position = 0  # Target precedes the first valid value
        return filled_series.iloc[position]

    except (IndexError, KeyError, ValueError):
        return default


def _set_df_column_value(df: pd.DataFrame, column_name: str, date_value: datetime, value: float) -> None:
    """Set a value at the specified date_value index position, or closest. Create the column if it doesn't exist"""
    date_value = pd.to_datetime(date_value)
    if column_name not in df.columns:
        # Ensure the column exists
        df[column_name] = None

    # Find the integer position of the nearest index
    nearest_pos = df.index.get_indexer([date_value], method="nearest")[0]
    # The actual index label using that position
    closest_index = df.index[nearest_pos]
    # Assign the value
    df.at[closest_index, column_name] = value


# ---------------------------------------------------------------------------
# Portfolio math helpers (used by both backtest.py and reporting internals)
# ---------------------------------------------------------------------------
def portfolio_value(
    portfolio: Portfolio,
    portfolio_data: pd.DataFrame,
    rebalanced: bool,
    at_date: datetime,
    ticker: str | None = None,
) -> tuple[float, float]:
    """Calculate the total investment value and share count for a portfolio at a given date.

    Args:
        portfolio: Portfolio object containing holdings information.
        portfolio_data: DataFrame with portfolio asset prices by date.
        portfolio_num_shares: DataFrame with portfolio share counts by date.
        at_date: Target date for value calculation (nearest date in DataFrames is used).
        ticker: Optional ticker symbol. If provided, calculates value for this specific
            holding only. If None, sums value across all holdings.

    Returns:
        tuple[float, float]: A tuple containing:
            - value: Total dollar value of the portfolio (or single ticker) at at_date.
            - num_shares: Total number of shares across all holdings (or single ticker) at at_date.
    """

    value = 0.0
    num_shares = 0.0
    if ticker:
        ticker_value = _get_df_column_value(portfolio_data, at_date, ticker, 0.0)

        column_name = get_numrebalancedshares_column(ticker) if rebalanced else get_numshares_column(ticker)
        ticker_num_shares = _get_df_column_value(portfolio_data, at_date, column_name, 0.0)
        value = ticker_value * ticker_num_shares
        num_shares = ticker_num_shares
    else:
        for fund in portfolio.holdings:
            ticker_value = _get_df_column_value(portfolio_data, at_date, fund.ticker, 0.0)

            column_name = get_numrebalancedshares_column(fund.ticker) if rebalanced else get_numshares_column(fund.ticker)
            ticker_num_shares = _get_df_column_value(portfolio_data, at_date, column_name, 0.0)
            value += ticker_value * ticker_num_shares
            num_shares += ticker_num_shares

    return (value, num_shares)


def get_annualized_return(initial_value: float, final_value: float, start_date: datetime, end_date: datetime) -> float:
    """Calculate the annualized rate of return from an initial to final value over a time period.

    Uses monthly compounding for more realistic results.

    Args:
        initial_value: Starting portfolio value.
        final_value: Ending portfolio value.
        start_date: Date when the portfolio had the initial value.
        end_date: Date when the portfolio had the final value.

    Returns:
        float: Annualized rate of return as a fraction (not a percentage).
            For example, 0.12 represents 12% annualized return.

    Examples:
        >>> get_annualized_return(1000, 1200, datetime(2026, 1, 1), datetime(2027, 1, 1))
        0.19999999999999996
    """

    # Calculate difference in days and convert to years
    days_diff = (end_date - start_date).days
    years_diff = days_diff / 365.0

    if years_diff <= 0:
        return 0.0

    # Calculate Absolute Return
    # total_return = (final_value - initial_value) / initial_value

    # Calculate Annualized Return
    if initial_value != 0.0 and years_diff != 0.0:
        annualized_return = (final_value / initial_value) ** (1 / years_diff) - 1
    else:
        annualized_return = 0.0
    return annualized_return


def _download_yahoo_finance_data(ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Download historical data from Yahoo Finance for a single ticker.

    Returns a DataFrame with columns: Open, High, Low, Close, Volume, Dividends,
    Stock Splits, Ticker.  Index is UTC-aware DatetimeIndex.
    """
    yfticker = yf.Ticker(ticker)
    # Ticker.history normally truncates data to inception if start_date is too early
    df = yfticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
    # Double check if the returned DataFrame is completely empty (e.g., severe API lag)
    if df.empty:
        Log.log(f"\u2757 -> No data returned. Inspecting metadata for {ticker}...")

        # Fallback: Extract the exact listing date from metadata
        epoch_time = yfticker.info.get("firstTradeDateEpochUtc")

        if epoch_time:
            actual_start = datetime.fromtimestamp(epoch_time).strftime("%Y-%m-%d")
            Log.log(f"\u2757 -> Listing date detected: {actual_start}. Retrying...")
            df = yfticker.history(start=actual_start, end=end.strftime("%Y-%m-%d"))
        else:
            Log.log(f"\u2757 -> Warning: Could not find listing date metadata for {ticker}.")

    # Keep data in UTC to avoid problems with loading data later
    df.index = pd.to_datetime(df.index, utc=True)

    # Add ticker symbol into DataFrame
    df["Ticker"] = ticker

    return df


def _download_portfolio_history(
    portfolio: Portfolio,
    start: datetime,
    end: datetime,
    portfolio_data: pd.DataFrame,
) -> pd.DataFrame:
    """Download historical data for all holdings in a portfolio.

    Downloads weekly (Friday) closing prices for each holding, filling gaps
    from a local SQLite cache where possible.

    Returns:
        (portfolio_data, portfolio_num_shares)
        - portfolio_data: weekly closing prices (1 column per ticker)
        - portfolio_num_shares: initial share allocation per holding
    """
    db = DbCache()

    # For each fund, read the raw data and prepare weekly summaries
    weekly_data: list[pd.DataFrame] = []
    for fund in portfolio.holdings:
        min_date, max_date = db.get_min_max_dates(fund.ticker)

        if min_date and max_date:
            if start < min_date and (min_date - start).days > 3:
                # Update missing data. Use fuzz of 3 because no data on holidays/weekends
                df = _download_yahoo_finance_data(fund.ticker, start, min_date)
                db.cache_data(df)
            if end > max_date and (end - max_date).days > 3:
                df = _download_yahoo_finance_data(fund.ticker, max_date, end)
                db.cache_data(df)
            # Read from cache
            df = db.get_cache_data(fund.ticker, start, end)
        else:
            # No historical data cached
            df = _download_yahoo_finance_data(fund.ticker, start, end)
            db.cache_data(df)

        # Get weekly data (Friday closing)
        weekly = df.asfreq("W-FRI", method="pad")
        weekly = weekly[["Close"]].copy()
        weekly.columns = [fund.ticker if x == "Close" else x for x in weekly.columns]
        weekly_data.append(weekly)

    # Concatenate to single dataframe. Index by time, one column per ticker.
    portfolio_data = pd.concat([portfolio_data] + weekly_data, axis=1)
    # Sort the index so operations like "nearest" work
    portfolio_data = portfolio_data.sort_index()
    # Fill in missing data: Propagates the last valid row value downward and upward
    portfolio_data = portfolio_data.ffill().bfill()

    return portfolio_data


def _normalize_percentage(portfolio: Portfolio, ticker: str) -> float:
    """Normalize a holding's percentage so all holdings sum to 100."""
    total = 0

    val = 0
    for fund in portfolio.holdings:
        total += fund.value
        if fund.ticker == ticker:
            val = fund.value
    return val * 100.0 / total


def _allocate_shares_in_portfolio(
    portfolio: Portfolio,
    portfolio_data: pd.DataFrame,
    start: datetime,
    _end: datetime,
    initial_investment: float,
    _usd_cad: float,
) -> pd.DataFrame:
    """Calculate initial share allocation for each holding in a portfolio.

    Computes the number of shares to hold for each ticker based on the
    initial investment and its percentage in the portfolio. The calculation
    is performed at the given start date using the closing price of that
    date.

    Args:
        portfolio: Portfolio object containing holdings.
        portfolio_data: DataFrame with historical price data (weekly closing
            prices, UTC DatetimeIndex, one column per ticker).
        start: Start date for the calculation.
        _end: End date (not used in calculation but kept for interface
            compatibility).
        initial_investment: Total initial investment amount in USD.
        _usd_cad: CAD/USD exchange rate (not used, kept for compatibility).

    Returns:
        DataFrame with one row (at start date) containing the number of shares
        for each holding. Index is UTC-aware DatetimeIndex with weekly frequency.
    """

    # Calculate the number of shares per holding based on
    # their book value + percentage in the portfolio + total initial investment
    for fund in portfolio.holdings:
        share_price = _get_df_column_value(portfolio_data, start, fund.ticker, 0.0)
        if share_price == 0.0:
            num = 0.0
        else:
            num = initial_investment * _normalize_percentage(portfolio, fund.ticker) / 100
            num = num / share_price

        # Add column for num_shares per ticker; set initial value at start time.
        column_name = get_numshares_column(fund.ticker)
        _set_df_column_value(portfolio_data, column_name, start, num)

    # Fill in missing data: Propagates the last valid row value downward and upward
    portfolio_data = portfolio_data.ffill().bfill()
    return portfolio_data


def _rebalance_portfolio(
    portfolio: Portfolio,
    portfolio_data: pd.DataFrame,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Rebalance holdings annually at year-end.

    Returns a copy of portfolio_num_shares with additional rows for each
    rebalance date.
    """

    ## Initialize rebalanced number of shares to the initial allocation
    for fund in portfolio.holdings:
        column_name = get_numrebalancedshares_column(fund.ticker)
        column_name_numshares = get_numshares_column(fund.ticker)
        num_shares = _get_df_column_value(portfolio_data, start, column_name_numshares, 0.0)
        # Initialize the rebalanced share count with the initial allocation.
        _set_df_column_value(portfolio_data, column_name, start, num_shares)

    for dt in rrule.rrule(rrule.YEARLY, dtstart=start, until=end):
        year_end = datetime_nyc(datetime(dt.year, 12, 31))
        if year_end > end:
            break

        # Rebalance current investment
        current_investment, _ = portfolio_value(portfolio, portfolio_data, rebalanced=True, at_date=year_end)
        for fund in portfolio.holdings:
            share_price = _get_df_column_value(portfolio_data, year_end, fund.ticker, 0.0)
            num = current_investment * _normalize_percentage(portfolio, fund.ticker) / 100
            num = num / share_price if share_price != 0.0 else 0.0
            column_name = get_numrebalancedshares_column(fund.ticker)
            # Set the year-end rebalanced count.
            _set_df_column_value(portfolio_data, column_name, year_end, num)

    # Fill in missing data: Propagates the last valid row value downward and upward
    portfolio_data = portfolio_data.ffill().bfill()
    return portfolio_data


def download_portfolio(
    portfolio: Portfolio,
    start: datetime,
    end: datetime,
    initial_investment: float = Portfolio.DEFAULT_INITIAL_INVESTMENT,
    usd_cad: float = Portfolio.DEFAULT_USD_CAD,
) -> pd.DataFrame:
    # Download historical data
    portfolio_data = _download_portfolio_history(portfolio, start, end, pd.DataFrame())

    # Allocate shares per ticker
    portfolio_data = _allocate_shares_in_portfolio(portfolio, portfolio_data, start, end, initial_investment, usd_cad)

    # Run a yearly rebalancing
    portfolio_data = _rebalance_portfolio(portfolio, portfolio_data, start, end)

    return portfolio_data

"""
def portfolio_summary(
    portfolio: Portfolio,
    portfolio_data: pd.DataFrame,
    start: datetime,
    end: datetime,
    initial_investment: float,
) -> None:
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

def portfolio_summary(
    portfolio: Portfolio,
    portfolio_data: pd.DataFrame,
    start: datetime,
    end: datetime,
    initial_investment: float,
) -> None:
    ""Print a detailed holdings breakdown table comparing original and rebalanced portfolios.

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
    ""
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
"""
