# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "altair>=6.2.2",
#     "backtest>=0.1.0",
#     "inquirerpy>=0.3.4",
#     "ipython>=9.15.0",
#     "ipywidgets>=8.1.8",
#     "itables>=2.9.1",
#     "marimo>=0.23.15",
#     "numpy>=2.5.1",
#     "pandas>=3.0.2",
#     "python-dateutil>=2.9.0.post0",
#     "tabulate>=0.10.0",
#     "yfinance>=1.5.2",
# ]
# [tool.uv.sources]
# ///
import marimo
import altair

# backtest = { path = "public/wheels/backtest-0.1.0-py3-none-any.whl" }
__generated_with = "0.23.15"
app = marimo.App()


@app.cell
def _():
    from datetime import datetime

    import marimo as mo
    from dateutil.relativedelta import relativedelta

    from backtest import Backtest, Portfolio

    return Backtest, Portfolio, datetime, mo, relativedelta


@app.cell
def _(Backtest, Portfolio, datetime, relativedelta):
    initial_investment = 1_000_000.0

    my_portfolios = [
        Portfolio("test", "BRKA 100"),
        Portfolio(name="Sell", holdings="AAPL 4.9, BRKA 1.9, GOOG 5.5, AMZN 2.5, TSLA 0.8;"),
        Portfolio(
            name="To Buy",
            holdings="MSFT, 8.51; AAPL, 8.81; TSLA, 7.78; BAC, 8.15;"
            + "NVDA, 8.25; GOOGL, 7.52; QQQ, 7.49; VOO, 7.32; BRK-B, 6.54; JPM, 6.82;"
            + "MU, 5.66; AMZN, 6.63; SHOP, 6.63; DRAM, 3.87;",
        ),
    ]

    end = datetime.now().date()
    start = end - relativedelta(years=3)
    portfolios = my_portfolios + Backtest.DEFAULT_PORTFOLIOS
    benchmarks = Backtest.DEFAULT_BENCHMARK_PORTFOLIOS
    return benchmarks, end, initial_investment, portfolios, start


@app.cell
def _(benchmarks, end, mo, portfolios, start):
    portfolio_options = {portfolio.name: portfolio for portfolio in portfolios}
    secondary_portfolio_options = {"-- Select Portfolio --": None, **portfolio_options}
    benchmark_options = {portfolio.name: portfolio for portfolio in benchmarks}

    start_date_picker = mo.ui.date(value=start, label="Start Date:")
    end_date_picker = mo.ui.date(value=end, label="End Date:")
    portfolio1_dropdown = mo.ui.dropdown(
        options=portfolio_options,
        value=portfolios[0].name,
        label="Portfolio1:",
    )
    portfolio2_dropdown = mo.ui.dropdown(
        options=secondary_portfolio_options,
        value="-- Select Portfolio --",
        label="Portfolio2:",
    )
    benchmark_dropdown = mo.ui.dropdown(
        options=benchmark_options,
        value=benchmarks[0].name,
        label="Benchmark:",
    )
    run_button = mo.ui.run_button(label="Run Backtest", kind="success")
    exit_button = mo.ui.run_button(label="Shutdown Server", kind="danger")

    controls = mo.vstack(
        [
            mo.hstack([start_date_picker, end_date_picker], justify="start"),
            mo.hstack([portfolio1_dropdown, portfolio2_dropdown], justify="start"),
            mo.hstack([benchmark_dropdown, run_button], justify="start"),
            mo.hstack([exit_button], justify="start"),
        ]
    )
    controls  # noqa: B018 - final expression is the cell output
    return (
        benchmark_dropdown,
        end_date_picker,
        portfolio1_dropdown,
        portfolio2_dropdown,
        run_button,
        exit_button,
        start_date_picker,
    )


@app.cell
def _(
    Backtest,
    benchmark_dropdown,
    end_date_picker,
    initial_investment,
    mo,
    portfolio1_dropdown,
    portfolio2_dropdown,
    run_button,
    start_date_picker,
):
    mo.stop(not run_button.value)
    Backtest.run(
        [portfolio1_dropdown.value, portfolio2_dropdown.value],
        benchmark_dropdown.value,
        start_date_picker.value,
        end_date_picker.value,
        initial_investment,
    )
    return


@app.cell
def _(exit_button, mo):
    # This cell will run when the button is clicked
    import os
    if exit_button.value:
        os._exit(0)


if __name__ == "__main__":
    app.run()
