from __future__ import annotations

import collections
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from dateutil import rrule
from pandas.errors import DatabaseError

__all__ = ["Holding", "download_portfolio_history", "rebalance_portfolio", "plot_results"]

Holding = collections.namedtuple("Holding", "ticker percent description")


def is_tzoffset_aware(dt: datetime) -> bool:
    """
    Checks if a datetime object has a timezone attached.
    >>> is_tzoffset_aware(now())
    False
    >>> is_tzoffset_aware(datetime.now(timezone.utc))
    True
    """
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None


class DbCache:
    _instance: DbCache | None = None
    _conn: sqlite3.Connection | None = None
    _cursor: sqlite3.Cursor | None = None

    def __init__(self):
        raise RuntimeError("Call DbCache.instance() instead")

    @classmethod
    def instance(cls):
        if cls._instance is None:
            # Creating new instance
            cls._instance = cls.__new__(cls)
            # Put any initialization here.
            # Open database
            cls._instance._conn = sqlite3.connect("finance-data.db")
            if not cls._instance._create_sql_tables():
                cls._instance._conn = None
        return cls._instance

    def _create_sql_tables(self) -> bool:
        if not self._conn:
            return False

        cursor = self._conn.cursor()
        # Create table
        try:
            cursor.execute(
                "SELECT count(name) FROM sqlite_master WHERE type='table' AND name='yahoo_daily'"
            )
            if cursor.fetchone()[0] == 0:
                cursor.execute("pragma encoding=UTF8")
                cursor.execute("""CREATE TABLE IF NOT EXISTS yahoo_daily
                    (Date TEXT,
                     Ticker TEXT,
                     High NUMERIC,
                     Low NUMERIC,
                     Open NUMERIC,
                     Close NUMERIC,
                     Volume NUMERIC,
                     PRIMARY KEY(Date, Ticker))""")
                # Create secondary indices
                cursor.execute("CREATE INDEX index_Date ON yahoo_daily(Date)")
                cursor.execute("CREATE INDEX index_Ticker ON yahoo_daily(Ticker)")
            else:
                pass
            return True
        except sqlite3.DatabaseError:
            return False

    def get_cache_data(self, ticker: str, min_date: datetime, max_date: datetime) -> pd.DataFrame:
        query = f"""SELECT Date, Ticker, High, Low, Open, Close, Volume
                   FROM yahoo_daily
                   WHERE Ticker='{ticker}'
                   AND
                   Date BETWEEN '{min_date}' AND '{max_date}'
                   ORDER BY DATE(Date) ASC"""
        df = pd.read_sql_query(
            query, con=self._conn, index_col="Date", parse_dates={"Date": "%Y-%m-%dT%H:%M:%S%z"}
        )
        return df

    def cache_data(self, df: pd.DataFrame) -> bool:
        if not self._conn:
            return False
        # Upload DataFrame as Table into SQL Database
        try:
            zip_rows = zip(
                df.index, df["Ticker"], df["High"], df["Low"], df["Open"], df["Close"], df["Volume"],
                strict=True
            )
            rows = [
                (
                    row[0].isoformat(),  # Convert from pandas.Timestamp to ISO 8601 format
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                )
                for row in zip_rows
            ]

            # insert multiple records in a single query
            query = "INSERT OR REPLACE INTO yahoo_daily (Date, Ticker, High, Low, Open, Close, Volume) VALUES(?,?,?,?,?,?,?);"
            self._conn.executemany(query, rows)
            self._conn.commit()
        except DatabaseError:
            # db is probably locked by someone else
            self._conn = None
            return False
        return True

    def get_min_max_dates(self, ticker: str) -> tuple[datetime | None, datetime | None]:
        if not self._conn:
            return (None, None)
        query = "SELECT Min(Date),Max(Date) from yahoo_daily where Ticker=?"
        args = (ticker,)
        a = self._conn.cursor().execute(query, args).fetchall()
        min_date = None
        max_date = None
        if a and a[0] and a[0][0]:
            min_date = datetime.strptime(a[0][0], "%Y-%m-%dT%H:%M:%S%z")
        if a and a[0] and a[0][1]:
            max_date = datetime.strptime(a[0][1], "%Y-%m-%dT%H:%M:%S%z")
        return (min_date, max_date)


# Download data from finance.yahoo.com
def _download_yahoo_finance_data(ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
    # Dataframe columns:
    #                                   Open         High          Low        Close      Volume  Dividends  Stock Splits
    # Date
    # 2021-01-04 00:00:00-05:00  3764.610107  3769.989990  3662.709961  3700.649902  5015000000        0.0           0.0
    # 2021-01-05 00:00:00-05:00  3698.020020  3737.830078  3695.070068  3726.860107  4591020000        0.0           0.0
    # yfinance by default returns pandas.Timestamp for the index timestamps
    yfticker = yf.Ticker(ticker)
    df = yfticker.history(
        start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d")
    )  # Get raw data
    # Keep data in UTC to avoid problems with loading data later
    df.index = pd.to_datetime(df.index, utc=True)

    # Add ticker symbol into DataFrame (str)
    df["Ticker"] = ticker

    return df


# Normalize the percentage of the funds. Make sure all add up to 100
def _normalize_percentage(portfolio, ticker: str) -> float:
    total = 0
    val = 0
    for fund in portfolio["holdings"]:
        total += fund.percent
        if fund.ticker == ticker:
            val = fund.percent
    return val * 100.0 / total


# Download the history of the portfolio.  Downsample as weekly data.
# Also create the initial share allocation for the portfolio at the start date
# Return a tuple of:
#  - dataframe with a time index + 1 column per ticker (named the ticker symbol)
#  - dataframe of number of shares per holding
def download_portfolio_history(
    portfolio, start: datetime, end: datetime, initial_investment: float, usd_cad: float
):

    # Create table
    db = DbCache.instance()

    # For each fund, read the raw data and prepare weekly summaries
    weekly_data = []
    for fund in portfolio["holdings"]:
        min_date, max_date = db.get_min_max_dates(fund.ticker)

        if min_date and max_date:
            if start < min_date and (min_date - start).days > 3:
                # Update missing data. Use fuzz of 3 because no data on holidays/weekends
                df = _download_yahoo_finance_data(fund.ticker, start, min_date)
                db.cache_data(df)
            if end > max_date and (end - max_date).days > 3:
                # Update missing data. Use fuzz of 3 because no data on holidays/weekends
                df = _download_yahoo_finance_data(fund.ticker, max_date, end)
                db.cache_data(df)
            # Read from cache
            df = db.get_cache_data(fund.ticker, start, end)
        else:
            # No historical data cached
            df = _download_yahoo_finance_data(fund.ticker, start, end)

            # Cache data
            db.cache_data(df)

        # Get weekly data
        weekly = df.asfreq("W-FRI", method="pad")  # Get weekly summary
        weekly = weekly[["Close"]].copy()  # Just keep the 'Close' column
        weekly.columns = [
            fund.ticker if x == "Close" else x for x in weekly.columns
        ]  # Rename 'Close' to fund_name
        weekly_data.append(weekly)

    # Concatenate to single dataframe. Index by time, one column per ticker.
    portfolio_data = pd.concat(weekly_data, axis=1)
    # Fill in missing data: Propagates the last valid row value downward and upward
    portfolio_data = portfolio_data.ffill().bfill()

    # Create dataframe to hold number of shares of each holding. Column name is the ticker symbol
    index = pd.date_range(datetime.now().date(), periods=0, freq="W")
    columns = [fund.ticker for fund in portfolio["holdings"]]
    portfolio_num_shares = pd.DataFrame(index=index, columns=columns)

    # Calculate the number of shares per holding based on
    # their book value + percentage in the portfolio + total initial investment
    num_shares = []
    for fund in portfolio["holdings"]:
        index = portfolio_data.index.get_indexer([start], method="nearest")
        share_price = portfolio_data.iloc[index][fund.ticker].item()
        # num = initial_investment * fund.percent / 100
        num = initial_investment * _normalize_percentage(portfolio, fund.ticker) / 100
        num = num / share_price
        num_shares.append(num)

    # Add row to dataframe
    portfolio_num_shares.loc[start] = num_shares

    return (portfolio_data, portfolio_num_shares)


# Rebalance holdings yearly
def rebalance_portfolio(portfolio, portfolio_data, portfolio_num_shares, start, end):
    rebalanced_num_shares = portfolio_num_shares.copy()

    # Rebalance holding at year end
    for dt in rrule.rrule(rrule.YEARLY, dtstart=start, until=end):
        year_end = datetime(dt.year, 12, 31).replace(tzinfo=ZoneInfo("America/New_York"))
        if year_end > end:
            break

        # Rebalance current investment
        current_investment, _ = _portfolio_value(
            portfolio, portfolio_data, rebalanced_num_shares, at_date=year_end
        )
        # num_shares_index =  rebalanced_num_shares.index.get_indexer([year_end], method='nearest') # both shoud be pad
        data_index = portfolio_data.index.get_indexer([year_end], method="nearest")
        num_shares = []
        for fund in portfolio["holdings"]:
            share_price = portfolio_data.iloc[data_index][fund.ticker].item()
            # num = current_investment * fund.percent / 100
            num = current_investment * _normalize_percentage(portfolio, fund.ticker) / 100
            num = num / share_price
            num_shares.append(num)

        # Add row to dataframe
        # rebalanced_num_shares.iloc[num_shares_index] = num_shares
        rebalanced_num_shares.loc[year_end] = num_shares

    # portfolio_num_shares.to_csv("port.csv")
    # rebalanced_num_shares.to_csv("port-rb.csv")
    return rebalanced_num_shares


# Calculate total investment value at given date
# Return tuple(value, num_shares)
def _portfolio_value(
    portfolio, portfolio_data, portfolio_num_shares, at_date, ticker=None
) -> tuple[float, float]:
    # Sum all the portfolios
    index = portfolio_data.index.get_indexer([at_date], method="nearest")
    index_num_shares = portfolio_num_shares.index.get_indexer([at_date], method="nearest")
    if not ticker:
        # Get total of all holdings
        value = 0
        num_shares = 0
        for fund in portfolio["holdings"]:
            ticker_value = portfolio_data.iloc[index][fund.ticker].item()
            ticker_num_shares = portfolio_num_shares.iloc[index_num_shares][fund.ticker].item()
            value += ticker_value * ticker_num_shares
            num_shares += portfolio_num_shares.iloc[index_num_shares][fund.ticker].item()
    else:
        # Get for the specified ticker
        ticker_value = portfolio_data.iloc[index][ticker].item()
        ticker_num_shares = portfolio_num_shares.iloc[index_num_shares][ticker].item()
        value = ticker_value * ticker_num_shares
        num_shares = portfolio_num_shares.iloc[index_num_shares][ticker].item()

    return (value, num_shares)


# Calculated the annualized rate of return (as a fraction)
def get_annualized_return(initial: float, final: float, start: datetime, end: datetime) -> float:
    # See https://www.calculatorsoup.com/calculators/financial/compound-interest-calculator.php
    n = 12  # Compounded monthly
    t = round((end - start) / timedelta(365, 5, 49, 12), 2)
    A = final
    P = initial
    r = n * ((A / P) ** (1 / (n * t)) - 1)
    return r


# Summarize the performance
def print_stats(initial, final, start, end):
    percent = (final - initial) / initial * 100
    r = get_annualized_return(initial, final, start, end)

    print(
        f" = {final - initial:+10,.2f}$ = {percent:+6.2f}% (total) = {r * 100:+6.2f}% (annualized)"
    )


def plot_results(
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
):

    # Sum all the portfolios
    portfolio_result_total, _ = _portfolio_value(
        portfolio, portfolio_data, portfolio_num_shares, at_date=end
    )
    rebalanced_result_total, _ = _portfolio_value(
        portfolio, portfolio_data, rebalanced_num_shares, at_date=end
    )
    benchmark_result_total, _ = _portfolio_value(
        benchmark_portfolio, benchmark_data, benchmark_num_shares, at_date=end
    )

    # Print out stats on the portfolio performance
    print(f"===Portfolio: {portfolio['name']}===")
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

    print(
        "                      Book           Percent       Current           Annualized Rebalanced           Annualized"
    )
    print(
        "    Holding          Value   #Shares Portfolio       Value   #Shares Return%        Yearly   #Shares Return%"
    )
    for fund in portfolio["holdings"]:
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

    print("\n")

    # Calculated the sum of the portfolio holdings (weighted by the number of shares per holding)
    portfolio_total = pd.DataFrame(index=portfolio_data.index)
    portfolio_total["Total"] = portfolio_data.mul(
        portfolio_num_shares.reindex(portfolio_data.index, method="pad")
    ).sum(axis=1)
    rebalanced_total = pd.DataFrame(index=portfolio_data.index)
    rebalanced_total["Total"] = portfolio_data.mul(
        rebalanced_num_shares.reindex(portfolio_data.index, method="pad")
    ).sum(axis=1)
    benchmark_total = pd.DataFrame(index=benchmark_data.index)
    benchmark_total["Total"] = benchmark_data.mul(
        benchmark_num_shares.reindex(benchmark_data.index, method="pad")
    ).sum(axis=1)

    # Plot the portfolio
    ax = portfolio_total.plot(y="Total", kind="line", figsize=(15, 8))

    # Add the rebalanced portfolio to the graph
    _bx = rebalanced_total.plot(y="Total", kind="line", ax=ax)

    # Add the benchmark to the graph
    _bx = benchmark_total.plot(y="Total", kind="line", ax=ax)

    # Add labels
    ax.legend(["Portfolio", "Rebalanced", f"{benchmark_portfolio['name']}"])
    plt.title(f"Portfolio: {portfolio['name']}")
    plt.show()

    print("\n\n")


if __name__ == "__main__":
    # Dollars initially invested
    initial_investment = 100000
    # USD to CAD exchange rate
    usd_cad = 1.3

    # Collect data for this time period
    start = datetime(2015, 6, 19).replace(tzinfo=ZoneInfo("America/New_York"))
    end = datetime(2021, 5, 1).replace(tzinfo=ZoneInfo("America/New_York"))

    # Baseline benchmark
    benchmark_portfolio = {
        "name": "S&P 500 Benchmark",
        "holdings": [Holding("^GSPC", 100, "S&P 500")],
    }
    benchmark_data, benchmark_num_shares = download_portfolio_history(
        benchmark_portfolio, start, end, initial_investment, usd_cad
    )

    # Portfolio: Ticker, percentage of holdings, description
    portfolios = [
        {
            "name": "Vanguard Canadian",
            "holdings": [
                Holding("VGRO.TO", 80, "Vanguard Growth ETF Portfolio (CAD)"),
                Holding("XGRO.TO", 10, "iShares Core Growth ETF Portfolio (CAD)"),
                Holding("VEQT.TO", 10, "Vanguard All-Equity ETF Portfolio (CAD)"),
            ],
        },
        {
            "name": "Tech Stocks",
            "holdings": [
                Holding("AAPL", 20, ""),
                Holding("AMZN", 20, ""),
                Holding("NFLX", 20, ""),
                Holding("META", 20, ""),
                Holding("BRK-B", 20, ""),
            ],
        },
        {
            "name": "Nasdaq QQQ",
            "holdings": [
                Holding("QQQ", 100, ""),
            ],
        },
        {
            # See: https://www.holdingschannel.com/13f/cascade-investment-advisors-inc-top-holdings/
            "name": "BillG",
            "holdings": [
                Holding("AAPL", 4077, ""),
                Holding("MSFT", 3303, ""),
                Holding("INTC", 2953, ""),
                Holding("AMAT", 2405, ""),
                Holding("FDX", 2217, ""),
                Holding("FFIV", 2096, ""),
                Holding("DIS", 2036, ""),
                Holding("NTR", 1999, ""),
                Holding("TGT", 1993, ""),
                Holding("WSM", 1989, ""),
                Holding("USB", 1979, ""),
                Holding("AMGN", 1961, ""),
                Holding("META", 1906, ""),
                Holding("AMZN", 1872, ""),
                Holding("SCHW", 1863, ""),
                Holding("NVS", 1850, ""),
                Holding("EMR", 1817, ""),
                Holding("INFY", 1790, ""),
                Holding("RJF", 1790, ""),
                Holding("MET", 1788, ""),
                Holding("JLL", 1757, ""),
            ],
        },
    ]

    for portfolio in portfolios:
        portfolio_data, portfolio_num_shares = download_portfolio_history(
            portfolio, start, end, initial_investment, usd_cad
        )
        rebalanced_num_shares = rebalance_portfolio(
            portfolio, portfolio_data, portfolio_num_shares, start, end
        )

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
