"""Market-data extraction helpers independent of the Dash layout."""

from __future__ import annotations

import pandas as pd


def extract_market_data(data, tickers):
    if data.empty:
        return pd.DataFrame(), pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        fields = data.columns.get_level_values(0)
        if "Close" not in fields:
            return pd.DataFrame(), pd.DataFrame()
        prices = data["Close"].copy()
        dividends = (
            data["Dividends"].copy()
            if "Dividends" in fields
            else pd.DataFrame(0.0, index=data.index, columns=prices.columns)
        )
    elif "Close" in data.columns and len(tickers) == 1:
        prices = data[["Close"]].copy()
        prices.columns = [tickers[0]]
        dividends = (
            data[["Dividends"]].copy()
            if "Dividends" in data.columns
            else pd.DataFrame(0.0, index=data.index, columns=tickers)
        )
        dividends.columns = [tickers[0]]
    else:
        return pd.DataFrame(), pd.DataFrame()
    if isinstance(prices, pd.Series):
        prices = prices.to_frame(name=tickers[0])
    if isinstance(dividends, pd.Series):
        dividends = dividends.to_frame(name=tickers[0])
    return prices, dividends.reindex(
        index=prices.index, columns=prices.columns, fill_value=0.0
    ).fillna(0.0)


def to_weekly_market_data(data, ticker):
    prices, dividends = extract_market_data(data, [ticker])
    if prices.empty:
        return pd.DataFrame(columns=["Close", "Dividends"])
    index = pd.to_datetime(prices.index)
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    daily = pd.DataFrame(
        {"Close": prices[ticker].values, "Dividends": dividends[ticker].fillna(0.0).values},
        index=index,
    ).sort_index()
    return pd.DataFrame(
        {
            "Close": daily["Close"].resample("W-FRI").last(),
            "Dividends": daily["Dividends"].resample("W-FRI").sum(),
        }
    ).dropna(subset=["Close"])
