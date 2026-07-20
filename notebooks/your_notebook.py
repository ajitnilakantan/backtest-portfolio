import marimo

__generated_with = "0.23.10"
app = marimo.App()


@app.cell
def _():
    # Show matplotlib graphs
    # %matplotlib inline
    # '%matplotlib ipympl' command supported automatically in marimo

    # Enable tab autocomplete
    # magic command not supported in marimo; please file an issue to add support
    # %config IPCompleter.greedy=True
    # Autoload changed files
    # magic command not supported in marimo; please file an issue to add support
    # %load_ext autoreload
    # Configure to reload all modules before executing code
    # '%autoreload 2' command supported automatically in marimo

    # imports
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from backtest import Holding, download_portfolio_history, plot_results, rebalance_portfolio

    # Dollars initially invested
    initial_investment = 100000

    # USD to CAD exchange rate
    usd_cad = 1.3

    # Collect data for this time period
    start = datetime(2021, 1, 1).replace(tzinfo=ZoneInfo("America/New_York"))
    end = datetime(2025, 5, 1).replace(tzinfo=ZoneInfo("America/New_York"))

    # Baseline benchmark
    benchmark_portfolio = {"name": "S&P 500 Benchmark", "holdings": [Holding("^GSPC", 100, "S&P 500")]}
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
            "name": "TFSA",
            "holdings": [
                Holding("QQQ", 25, "Nasdaq"),
                Holding("SPY", 15, "S&P 500"),
                Holding("AAPL", 7.5, ""),
                Holding("AMZN", 7.5, ""),
                Holding("GOOGL", 7.5, ""),
                Holding("TSLA", 7.5, ""),
                Holding("MSFT", 7.5, ""),
                Holding("BRK-B", 7.5, ""),
                Holding("BAC", 7.5, ""),
                Holding("JPM", 7.5, ""),
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
    return


if __name__ == "__main__":
    app.run()
