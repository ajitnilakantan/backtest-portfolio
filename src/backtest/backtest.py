from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
from dateutil import rrule

from .db_cache import DbCache
from .holding import Portfolio
from .reporting import _portfolio_value


class Log:
    @staticmethod
    def log(msg: str) -> None:
        print(msg)


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


def _normalize_percentage(portfolio: Portfolio, ticker: str) -> float:
    """Normalize a holding's percentage so all holdings sum to 100."""
    total = 0
    val = 0
    for fund in portfolio.holdings:
        total += fund.value
        if fund.ticker == ticker:
            val = fund.value
    return val * 100.0 / total


def download_portfolio_history(
    portfolio: Portfolio,
    start: datetime,
    end: datetime,
    _initial_investment: float,
    _usd_cad: float,
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
    portfolio_data = pd.concat(weekly_data, axis=1)
    # Fill in missing data: Propagates the last valid row value downward and upward
    portfolio_data = portfolio_data.ffill().bfill()

    return portfolio_data


def shares_in_portfolio(
    portfolio: Portfolio,
    portfolio_data: pd.DataFrame,
    start: datetime,
    _end: datetime,
    initial_investment: float,
    _usd_cad: float,
) -> pd.DataFrame:
    # Create dataframe to hold number of shares of each holding.
    index = pd.date_range(datetime.now().date(), periods=0, freq="W")
    columns = [fund.ticker for fund in portfolio.holdings]
    portfolio_num_shares = pd.DataFrame(index=index, columns=columns)

    # Calculate the number of shares per holding based on
    # their book value + percentage in the portfolio + total initial investment
    num_shares = []
    for fund in portfolio.holdings:
        idx = portfolio_data.index.get_indexer([start], method="nearest")
        share_price = portfolio_data.iloc[idx][fund.ticker].item()
        num = initial_investment * _normalize_percentage(portfolio, fund.ticker) / 100
        num = num / share_price
        num_shares.append(num)

    portfolio_num_shares.loc[start] = num_shares

    return portfolio_num_shares


def rebalance_portfolio(
    portfolio: Portfolio,
    portfolio_data: pd.DataFrame,
    portfolio_num_shares: pd.DataFrame,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Rebalance holdings annually at year-end.

    Returns a copy of portfolio_num_shares with additional rows for each
    rebalance date.
    """
    rebalanced_num_shares = portfolio_num_shares.copy()

    for dt in rrule.rrule(rrule.YEARLY, dtstart=start, until=end):
        year_end = datetime(dt.year, 12, 31).replace(tzinfo=ZoneInfo("America/New_York"))
        if year_end > end:
            break

        # Rebalance current investment
        current_investment, _ = _portfolio_value(portfolio, portfolio_data, rebalanced_num_shares, at_date=year_end)
        data_index = portfolio_data.index.get_indexer([year_end], method="nearest")
        num_shares = []
        for fund in portfolio.holdings:
            share_price = portfolio_data.iloc[data_index][fund.ticker].item()
            num = current_investment * _normalize_percentage(portfolio, fund.ticker) / 100
            num = num / share_price
            num_shares.append(num)

        rebalanced_num_shares.loc[year_end] = num_shares

    return rebalanced_num_shares
