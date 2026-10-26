# Backtest Portfolio (Python Dash)

A modern, interactive portfolio backtesting and financial research workbench built with **Dash**, **Plotly**, and **yfinance**.

## Architecture and standalone library

The project is distributed as `backtest-dash`, organized into a reusable `testfolio_dash` library and a thin Dash launcher. The `testfolio_dash` import namespace is retained for compatibility. The library contains domain modules for portfolios, market data, SQLite caching, simulation, analytics, validation, and sharing; `testfolio_dash.gui` contains the Dash layout and callbacks. The root `app.py` and `db_cache.py` files are compatibility launchers/import shims.

The public library interface is exported from `testfolio_dash` and does not require importing Dash for core calculations:

```python
from testfolio_dash import (
    calculate_metrics,
    normalize_allocation,
    simulate_portfolio_with_dividends,
)

allocation = normalize_allocation({"SPY": 60, "BND": 40})
metrics = calculate_metrics(series, capital=1_000_000)
result = simulate_portfolio_with_dividends(prices, dividends, allocation, 1_000_000, "Year")
```

Use `uv run python app.py` for the development Dash server or `uv run python serve.py` for the Waitress server. Tests live under `tests/` and can be run with `uv run python -m unittest discover -s tests`.

## Features

- **Two portfolio types:**
  - Fixed, read-only predefined portfolios.
  - User-defined portfolios that can be created, edited, saved, and deleted in the Portfolio Manager.
- **Local persistence:** User-defined portfolios are stored in browser local storage and remain available after a reload. Portfolio selectors list user-defined portfolios first (then predefined), and the workbench and manager preselect the first available portfolio while the second-portfolio selector starts empty.
- **Flexible backtests:** Configure dates, initial capital (defaults to $1,000,000), and buy-and-hold, annual, or monthly rebalancing.
- **Fixed benchmark comparison:** Compare the selected portfolio with:
  - **S&P 500:** 100% SPY
  - **Nasdaq:** 100% QQQ
  - **60/40 Nasdaq/S&P Mix:** 60% QQQ and 40% SPY
- **Optional second portfolio:** Select another predefined or user-defined portfolio for a three-way comparison, or leave it empty for the standard portfolio-versus-benchmark view.
- **Comparative analytics:** Growth, drawdown, ending value, return, CAGR, volatility, Sharpe ratio, maximum drawdown, and dividend income are shown for every active portfolio and the benchmark.
- **Interactive visualizations:** Two- or three-series growth and drawdown charts plus a Portfolio 1 asset-correlation heatmap.

All active portfolios and the benchmark use the same unadjusted closing-price history, overlapping date range, and initial capital. Portfolio 1 and optional Portfolio 2 each have independent rebalancing and dividend-treatment controls in the compact **Portfolio Strategies** section. The benchmark always uses annual rebalancing with automatic dividend reinvestment. Portfolio allocations are viewed and edited only in Portfolio Manager; the workbench uses each selected saved allocation directly. Selector badges identify whether each portfolio is predefined or user-defined and mark benchmarks as fixed.

## Dividend methodology

The workbench offers two dividend treatments:

- **Hold as Cash:** each distribution credits `shares held × dividend per share` to portfolio cash. Cash is included in total value and is allocated back to target weights at the next scheduled rebalance.
- **Automatically Reinvest:** each ticker's weekly distribution purchases fractional shares of that same ticker at the end-of-week close. Scheduled portfolio rebalancing still applies normally.

Both modes preserve a gross dividend ledger, so dividend reports show distributions received even when those distributions were reinvested.

The Performance Metrics report includes:

- **Cumulative Dividends:** all dividend cash received during the common reporting period.
- **Average Yearly Dividends:** the mean of observed calendar-year dividend totals, including partial first and last years.
- **Average Yearly Dividend %:** the mean of each calendar year's dividend cash divided by that year's average daily total portfolio value.

Unadjusted closes are used so separately credited or reinvested dividends are not double counted. The **Dividends** result tab shows gross weekly distributions as a sparse grouped bar chart, entity summary cards, and up to 100 recent non-zero events with cumulative totals.

## Weekly Yahoo Finance cache

Yahoo Finance responses are stored in a local SQLite cache as end-of-week observations. Each cached row contains the last valid close in its `W-FRI` week and the sum of all per-share dividend events during that week. Shortened holiday weeks are retained using their last available close.

The default cache is `backtest-dash-weekly-v1.db` in the operating-system temporary directory. Override it with:

```bash
TESTFOLIO_CACHE_PATH=/path/to/market-data.db uv run python app.py
```

On a repeated backtest, fully covered ticker/date windows are read entirely from SQLite. Extending the requested dates downloads only the missing leading or trailing window, with a one-week overlap so an incomplete boundary week can be recomputed and upserted. Delete the SQLite file to force a complete refresh.

Portfolio 1, optional Portfolio 2, and benchmarks share the same ticker cache. Annualized volatility uses weekly returns (`sqrt(52)`); CAGR continues to use elapsed calendar time.

## Optional second portfolio

Use **Compare with Second Portfolio (Optional)** in the workbench to select any saved predefined or user-defined portfolio. Selecting one adds Portfolio 2 to the growth chart, drawdown chart, summary cards, and metrics table. Choose **None — No second portfolio** or clear the selector to return to the Portfolio 1 and benchmark view.

Portfolio 2 uses its saved allocation. Both portfolio allocations are managed on the Portfolio Manager tab rather than through workbench ticker fields. The correlation matrix remains scoped to Portfolio 1 assets. Selecting the same portfolio twice is allowed and produces explicitly labeled Portfolio 1 and Portfolio 2 traces.

## Benchmark registry

Fixed benchmarks are stored in [`benchmarks.json`](benchmarks.json). To add one, add a named JSON object whose keys are valid ticker symbols and whose values are positive finite weights:

```json
{
  "Example 50/50": {
    "SPY": 50,
    "BND": 50
  }
}
```

Weights are normalized automatically, so they do not have to total exactly 100. The registry must remain a non-empty JSON object and must include the default `S&P 500` benchmark. Benchmarks are source-controlled and read-only in the application; they are never written to browser storage.

## Setup with `uv`

1. Install the project dependencies:

   ```bash
   uv sync
   ```

2. Run the Dash application:

   ```bash
   uv run python app.py
   ```

3. Open [http://127.0.0.1:8050](http://127.0.0.1:8050).

## Methodology and assumptions

- Market observations are weekly and use unadjusted Yahoo Finance closing prices so separately credited dividends are not double counted.
- Fractional shares are supported. Within each observation, cash yield and recurring flows are applied, dividends are credited or reinvested, and then calendar or drift-threshold rebalancing and configured trading costs are applied.
- CAGR uses exact elapsed calendar time. Volatility and Sharpe use weekly returns annualized over 52 periods. Sharpe uses an annual risk-free-rate assumption that defaults to 2% and can be changed in the workbench.
- Short histories remain usable but display warnings when annualized metrics have less than one year or fewer than 26 weekly returns. For newer listings with partial coverage, missing prices before the first observation or after the last observation are carried backward/forward at the nearest available price; the analysis status identifies each ticker where this approximation is used.
- Taxes, bid/ask spread, and security-specific tax treatment are not modeled. Results are constrained by ticker availability, inception dates, and the common overlapping reporting period.

## Production

The normal command starts Dash using `TESTFOLIO_HOST`, `TESTFOLIO_PORT`, and `TESTFOLIO_DEBUG` (debug defaults off):

```bash
uv run python app.py
```

The package distribution is named `backtest-dash`; after installation, the optional launcher command is:

```bash
backtest-dash
```

For a production WSGI server that works on Windows and Linux:

```bash
uv run python serve.py
```

Recent market-data windows expire after 12 hours by default. Override this with `TESTFOLIO_CACHE_TTL_HOURS`. The workbench also offers an explicit refresh checkbox.

## Quality checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run coverage run -m unittest discover
uv run coverage report
uv build
```

## Tests

Run the deterministic helper tests without downloading market data:

```bash
uv run python -m unittest discover
```

## Browser QA checklist

1. Confirm the workbench badge changes between **Predefined portfolio** and **User portfolio** as selections change.
2. Confirm benchmark options are prefixed **Benchmark —** and the selector displays a **Fixed benchmark** badge.
3. In Portfolio Manager, verify predefined portfolios cannot be edited, saved, or deleted.
4. Create a user portfolio, edit and save it, reload the page, and confirm it persists; then delete it.
5. With no second portfolio selected, confirm the charts contain Portfolio 1 and the benchmark and the table contains one benchmark-difference column.
6. Select both predefined and user-defined Portfolio 2 options; confirm three growth/drawdown traces, Portfolio 2 cards, and P1/P2 benchmark-difference columns.
7. Give Portfolio 1 and Portfolio 2 different rebalance/dividend settings and confirm both strategies apply independently; confirm the benchmark remains fixed to annual/reinvest.
8. Clear Portfolio 2 and confirm its strategy row hides and the dashboard returns to two-series behavior. Delete a selected user Portfolio 2 and confirm the selector clears safely.
9. Run a comparison against each fixed benchmark and confirm the cards, charts, and metrics table update together.
10. Confirm the metrics table includes cumulative dividends, average yearly dividends, and average yearly dividend percentage for every active entity.
11. Run identical periods in **Hold as Cash** and **Automatically Reinvest** modes; confirm the mode badge and growth results update while gross dividend totals remain visible.
12. Open the Dividends tab and verify entity summary cards, sparse weekly bars, cumulative hover values, and newest-first event rows; also verify the no-dividend empty state.
13. Confirm every active chart series has a visible legend and unified hover values.
14. Check desktop and narrow browser widths for clipped selectors, legends, or horizontally scrolling tables.
15. Confirm the compact theme keeps controls, tabs, summary cards, manager grid, and dividend panel legible at desktop, tablet, and mobile widths without unnecessary color accents.
