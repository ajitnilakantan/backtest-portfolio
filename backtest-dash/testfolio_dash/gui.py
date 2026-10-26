import base64
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
from dash import Input, Output, State, ctx, dash_table, dcc, html

from testfolio_dash.analytics import (
    benchmark_relative_metrics,
)
from testfolio_dash.analytics import (
    calculate_metrics as calculate_portfolio_metrics,
)
from testfolio_dash.config import CONFIG
from testfolio_dash.portfolios import (
    export_portfolios_json,
    import_portfolios_json,
    normalize_rows,
    portfolio_display_name,
    validate_allocation_rows,
)
from testfolio_dash.validation import validate_backtest_request

from .db_cache import DbCache

logger = logging.getLogger(__name__)

# Initialize Dash app with a local, dependency-free visual identity.
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.index_string = """
<!DOCTYPE html>
<html lang="en">
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""
server = app.server
app.title = "Backtest Portfolio"

# Fixed portfolios are application-defined and cannot be edited by users.
PREDEFINED_PORTFOLIOS = {
    "Classic 60/40": {"SPY": 60.0, "BND": 40.0},
    "All-Weather": {"SPY": 30.0, "TLT": 40.0, "IEF": 15.0, "GLD": 7.5, "DBC": 7.5},
    "Golden Butterfly": {"VTI": 20.0, "TLT": 20.0, "SHY": 20.0, "GLD": 20.0, "QQQ": 20.0},
    "S&P 500 Only": {"SPY": 100.0},
}

DEFAULT_BENCHMARK = "S&P 500"
BENCHMARKS_PATH = Path(__file__).with_name("benchmarks.json")

PREDEFINED_PREFIX = "predefined:"
USER_PREFIX = "user:"


def portfolio_value(portfolio_type, name):
    return f"{portfolio_type}:{name}"


def parse_portfolio_value(value):
    if not value or ":" not in value:
        return None, None
    return value.split(":", 1)


def get_portfolio(selected_value, user_portfolios):
    portfolio_type, name = parse_portfolio_value(selected_value)
    if portfolio_type == "predefined":
        return PREDEFINED_PORTFOLIOS.get(name, {})
    if portfolio_type == "user":
        return (user_portfolios or {}).get(name, {})
    return {}


def validate_benchmark_registry(registry):
    if not isinstance(registry, dict) or not registry:
        raise ValueError("Benchmark registry must be a non-empty JSON object.")

    validated = {}
    for name, allocation in registry.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Every benchmark must have a non-empty name.")
        if not isinstance(allocation, dict) or not allocation:
            raise ValueError(f"Benchmark '{name}' must have a non-empty allocation object.")
        normalized = normalize_allocation(allocation)
        if not normalized:
            raise ValueError(f"Benchmark '{name}' must contain positive finite weights.")
        validated[name.strip()] = {ticker: weight * 100.0 for ticker, weight in normalized.items()}

    if DEFAULT_BENCHMARK not in validated:
        raise ValueError(f"Benchmark registry must include the default '{DEFAULT_BENCHMARK}'.")
    return validated


def load_benchmark_registry(path=BENCHMARKS_PATH):
    try:
        with Path(path).open(encoding="utf-8") as registry_file:
            registry = json.load(registry_file)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Unable to load benchmark registry '{path}': {error}") from error
    return validate_benchmark_registry(registry)


def portfolio_options(user_portfolios):
    user_options = [
        {
            "label": f"User — {name}",
            "value": portfolio_value("user", name),
        }
        for name in sorted((user_portfolios or {}), key=str.casefold)
    ]
    predefined_options = [
        {
            "label": f"Predefined — {name}",
            "value": portfolio_value("predefined", name),
        }
        for name in PREDEFINED_PORTFOLIOS
    ]
    return [*user_options, *predefined_options]


def first_portfolio_value(options):
    """Return the first available portfolio value for a default selector."""
    return options[0]["value"] if options else None


def optional_portfolio_options(user_portfolios):
    return [
        {"label": "None — No second portfolio", "value": ""},
        *portfolio_options(user_portfolios),
    ]


def format_strategy_label(rebalance_freq, dividend_mode):
    rebalance_text = {
        "None": "Buy & Hold",
        "Year": "Annual",
        "Month": "Monthly",
    }.get(rebalance_freq, "Annual")
    dividend_text = {
        "cash": "Hold as cash",
        "reinvest": "Reinvest",
    }.get(dividend_mode, "Hold as cash")
    return f"{rebalance_text} · {dividend_text}"


def clean_allocation_rows(rows):
    allocation = {}
    for row in rows or []:
        asset = str(row.get("asset", "")).strip().upper()
        try:
            weight = float(row.get("weight", 0))
        except (TypeError, ValueError):
            continue
        if asset and np.isfinite(weight) and weight > 0:
            allocation[asset] = allocation.get(asset, 0.0) + weight
    return allocation


def normalize_allocation(allocation):
    valid = {}
    for ticker, raw_weight in (allocation or {}).items():
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            continue
        ticker = str(ticker).strip().upper()
        if ticker and np.isfinite(weight) and weight > 0:
            valid[ticker] = valid.get(ticker, 0.0) + weight

    total_weight = sum(valid.values())
    if total_weight <= 0:
        return {}
    return {ticker: weight / total_weight for ticker, weight in valid.items()}


BENCHMARK_PORTFOLIOS = load_benchmark_registry()


def portfolio_type_label(selected_value):
    portfolio_type, _ = parse_portfolio_value(selected_value)
    return "User portfolio" if portfolio_type == "user" else "Predefined portfolio"


def benchmark_options():
    return [{"label": f"Benchmark — {name}", "value": name} for name in BENCHMARK_PORTFOLIOS]


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
        if "Dividends" in data.columns:
            dividends = data[["Dividends"]].copy()
            dividends.columns = [tickers[0]]
        else:
            dividends = pd.DataFrame(0.0, index=data.index, columns=tickers)
    else:
        return pd.DataFrame(), pd.DataFrame()

    if isinstance(prices, pd.Series):
        prices = prices.to_frame(name=tickers[0])
    if isinstance(dividends, pd.Series):
        dividends = dividends.to_frame(name=tickers[0])
    dividends = dividends.reindex(
        index=prices.index,
        columns=prices.columns,
        fill_value=0.0,
    ).fillna(0.0)
    return prices, dividends


def extract_close_prices(data, tickers):
    prices, _ = extract_market_data(data, tickers)
    return prices


def to_weekly_market_data(data, ticker):
    prices, dividends = extract_market_data(data, [ticker])
    if prices.empty:
        return pd.DataFrame(columns=["Close", "Dividends"])

    index = pd.to_datetime(prices.index)
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    prices = prices.copy()
    dividends = dividends.copy()
    prices.index = index
    dividends.index = index

    daily = pd.DataFrame(
        {
            "Close": prices[ticker],
            "Dividends": dividends[ticker].fillna(0.0),
        }
    ).sort_index()
    weekly = pd.DataFrame(
        {
            "Close": daily["Close"].resample("W-FRI").last(),
            "Dividends": daily["Dividends"].resample("W-FRI").sum(),
        }
    )
    return weekly.dropna(subset=["Close"])


def download_ticker_weekly(ticker, start, end):
    start = pd.Timestamp(start).normalize()
    end = pd.Timestamp(end).normalize()
    data = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=False,
        actions=True,
    )
    return to_weekly_market_data(data, ticker)


def load_cached_market_data(
    tickers,
    start,
    end,
    cache_path=None,
    *,
    force_refresh=False,
    include_provenance=False,
):
    start = pd.Timestamp(start).normalize()
    end = pd.Timestamp(end).normalize()
    close_frames = []
    dividend_frames = []
    provenance = {
        "provider": "Yahoo Finance",
        "tickers": {},
        "downloaded_windows": [],
        "cache_hits": [],
        "warnings": [],
    }
    now = pd.Timestamp.now(tz="UTC")
    recent_boundary = now.tz_localize(None).normalize() - pd.Timedelta(days=14)

    with DbCache(cache_path) as cache:
        for ticker in tickers:
            if force_refresh:
                cache.invalidate_coverage(ticker)
            coverage_start, coverage_end = cache.get_coverage(ticker)
            fetched_at = cache.get_fetch_time(ticker)
            stale_recent = False
            if end >= recent_boundary and fetched_at is not None:
                fetched_at = (
                    fetched_at.tz_localize("UTC")
                    if fetched_at.tzinfo is None
                    else fetched_at.tz_convert("UTC")
                )
                stale_recent = now - fetched_at > pd.Timedelta(hours=CONFIG.recent_cache_ttl_hours)
            gaps = []
            if coverage_start is None or coverage_end is None:
                gaps.append((start, end))
            else:
                if start < coverage_start:
                    gaps.append((start, min(end, coverage_start + pd.Timedelta(days=7))))
                if end > coverage_end or stale_recent:
                    gaps.append((max(start, coverage_end - pd.Timedelta(days=7)), end))

            downloaded = False
            for gap_start, gap_end in gaps:
                if gap_start > gap_end:
                    continue
                try:
                    weekly = download_ticker_weekly(ticker, gap_start, gap_end)
                except Exception as error:
                    cache.log_fetch(
                        ticker,
                        gap_start,
                        gap_end,
                        status="error",
                        error_category=type(error).__name__,
                    )
                    raise
                if cache.cache_data(ticker, weekly):
                    actual_start = pd.Timestamp(weekly.index.min()).normalize()
                    actual_end = pd.Timestamp(weekly.index.max()).normalize()
                    # A non-empty response confirms the requested window was checked;
                    # observations themselves remain bounded to actual weekly rows.
                    cache.extend_coverage(ticker, gap_start, gap_end)
                    cache.log_fetch(ticker, gap_start, gap_end, status="success", frame=weekly)
                    provenance["downloaded_windows"].append(
                        {
                            "ticker": ticker,
                            "start": str(actual_start.date()),
                            "end": str(actual_end.date()),
                        }
                    )
                    downloaded = True
                else:
                    cache.log_fetch(ticker, gap_start, gap_end, status="empty", frame=weekly)
                    provenance["warnings"].append(
                        f"{ticker} returned no data for a requested window."
                    )

            cached = cache.get_cache_data(
                ticker,
                start,
                end + pd.Timedelta(days=6),
            )
            if cached.empty:
                continue
            if not downloaded:
                provenance["cache_hits"].append(ticker)
            latest_fetch = cache.latest_fetch(ticker)
            provenance["tickers"][ticker] = {
                "source": "network" if downloaded else "cache",
                "first_date": str(cached.index.min().date()),
                "last_date": str(cached.index.max().date()),
                "last_fetch": latest_fetch["fetched_at"] if latest_fetch else None,
            }
            close_frames.append(cached[["Close"]].rename(columns={"Close": ticker}))
            dividend_frames.append(cached[["Dividends"]].rename(columns={"Dividends": ticker}))

    prices = pd.concat(close_frames, axis=1).sort_index() if close_frames else pd.DataFrame()
    dividends = (
        pd.concat(dividend_frames, axis=1).sort_index().fillna(0.0)
        if dividend_frames
        else pd.DataFrame()
    )
    if include_provenance:
        return prices, dividends, provenance
    return prices, dividends


def fill_limited_history(prices, dividends, tickers, warnings=None, target_index=None):
    """Fill gaps for tickers with shorter histories while preserving real data."""
    if target_index is not None:
        target_index = pd.DatetimeIndex(target_index)
        prices = prices.reindex(prices.index.union(target_index))
    prices = prices.reindex(columns=tickers).sort_index()
    dividends = dividends.reindex(index=prices.index, columns=tickers).fillna(0.0)
    warnings = warnings if warnings is not None else []

    for ticker in tickers:
        observed = prices[ticker].dropna()
        if observed.empty:
            continue
        first_observed = observed.index.min()
        last_observed = observed.index.max()
        backfilled = first_observed > prices.index.min()
        forwardfilled = last_observed < prices.index.max()
        prices[ticker] = prices[ticker].bfill().ffill()
        if backfilled or forwardfilled:
            directions = []
            if backfilled:
                directions.append(f"backfilled before {first_observed.date()}")
            if forwardfilled:
                directions.append(f"forward-filled after {last_observed.date()}")
            warnings.append(
                f"{ticker} has limited history; prices were {' and '.join(directions)}."
            )

    return prices, dividends, warnings


def simulate_portfolio_with_dividends(
    prices,
    dividends,
    allocation,
    capital,
    rebalance_frequency,
    dividend_mode="cash",
    recurring_flow=0.0,
    flow_frequency="None",
    transaction_cost_percent=0.0,
    transaction_cost_fixed=0.0,
    cash_yield=0.0,
    rebalance_threshold=0.05,
    inflation_rate=0.0,
):
    normalized = normalize_allocation(allocation)
    tickers = list(normalized)
    if not tickers or any(ticker not in prices.columns for ticker in tickers):
        empty = pd.Series(dtype=float)
        return {"value": empty, "dividends": empty, "cumulative_dividends": empty}

    portfolio_prices = prices[tickers].dropna()
    if len(portfolio_prices) < 2:
        empty = pd.Series(dtype=float)
        return {"value": empty, "dividends": empty, "cumulative_dividends": empty}

    portfolio_dividends = dividends.reindex(
        index=portfolio_prices.index,
        columns=tickers,
        fill_value=0.0,
    ).fillna(0.0)
    weights = np.array([normalized[ticker] for ticker in tickers])
    shares = (capital * weights) / portfolio_prices.iloc[0].values
    starting_values = shares * portfolio_prices.iloc[0].values
    cash = 0.0
    cumulative_dividends = 0.0
    values = []
    real_values = []
    dividend_cash_values = []
    cumulative_dividend_values = []
    flow_values = []
    cost_values = []

    if rebalance_frequency == "Year":
        periods = portfolio_prices.index.to_period("Y")
    elif rebalance_frequency == "Month":
        periods = portfolio_prices.index.to_period("M")
    else:
        periods = None
    flow_periods = (
        portfolio_prices.index.to_period("M")
        if flow_frequency == "Month"
        else portfolio_prices.index.to_period("Y")
        if flow_frequency == "Year"
        else None
    )

    previous_period = periods[0] if periods is not None else None
    previous_flow_period = flow_periods[0] if flow_periods is not None else None
    previous_date = portfolio_prices.index[0]
    for position, (date, row) in enumerate(portfolio_prices.iterrows()):
        current_period = periods[position] if periods is not None else None
        current_flow_period = flow_periods[position] if flow_periods is not None else None
        elapsed_days = max((date - previous_date).days, 0)
        if cash and cash_yield and elapsed_days:
            cash *= (1 + cash_yield) ** (elapsed_days / 365.25)

        external_flow = 0.0
        if flow_periods is not None and current_flow_period != previous_flow_period:
            external_flow = float(recurring_flow)
            cash += external_flow

        dividends_per_share = portfolio_dividends.loc[date].values
        dividend_cash_by_ticker = shares * dividends_per_share
        dividend_cash = float(dividend_cash_by_ticker.sum())
        cumulative_dividends += dividend_cash
        if dividend_mode == "reinvest":
            shares = shares + np.divide(
                dividend_cash_by_ticker,
                row.values,
                out=np.zeros_like(dividend_cash_by_ticker),
                where=row.values != 0,
            )
        else:
            cash += dividend_cash

        total_before_rebalance = float((shares * row.values).sum()) + cash
        current_weights = (
            shares * row.values / total_before_rebalance if total_before_rebalance > 0 else weights
        )
        calendar_rebalance = periods is not None and current_period != previous_period
        threshold_rebalance = (
            rebalance_frequency == "Threshold"
            and np.max(np.abs(current_weights - weights)) >= rebalance_threshold
        )
        cost = 0.0
        if calendar_rebalance or threshold_rebalance:
            target_values = total_before_rebalance * weights
            traded = float(np.abs(target_values - shares * row.values).sum())
            cost = float(transaction_cost_fixed) + traded * float(transaction_cost_percent) / 100.0
            investable = max(total_before_rebalance - cost, 0.0)
            shares = np.divide(
                investable * weights,
                row.values,
                out=np.zeros_like(weights),
                where=row.values != 0,
            )
            cash = 0.0

        value = float((shares * row.values).sum()) + cash
        years_elapsed = max((date - portfolio_prices.index[0]).days / 365.25, 0)
        inflation_factor = (1 + inflation_rate) ** years_elapsed if inflation_rate > -1 else 1.0
        values.append(value)
        real_values.append(value / inflation_factor)
        dividend_cash_values.append(dividend_cash)
        cumulative_dividend_values.append(cumulative_dividends)
        flow_values.append(external_flow)
        cost_values.append(cost)
        previous_period = current_period
        previous_flow_period = current_flow_period
        previous_date = date

    index = portfolio_prices.index
    ending_values = shares * portfolio_prices.iloc[-1].values
    elapsed_years = max((index[-1] - index[0]).days / 365.25, 0.0)
    holding_results = {}
    for ticker, start_value, end_value in zip(tickers, starting_values, ending_values):
        growth = end_value / start_value - 1 if start_value > 0 else float("nan")
        cagr = (
            (end_value / start_value) ** (1 / elapsed_years) - 1
            if elapsed_years > 0 and start_value > 0 and end_value > 0
            else float("nan")
        )
        holding_results[ticker] = {
            "start_value": float(start_value),
            "end_value": float(end_value),
            "total_growth": float(growth),
            "cagr": float(cagr),
        }
    return {
        "value": pd.Series(values, index=index, dtype=float),
        "real_value": pd.Series(real_values, index=index, dtype=float),
        "dividends": pd.Series(dividend_cash_values, index=index, dtype=float),
        "cumulative_dividends": pd.Series(cumulative_dividend_values, index=index, dtype=float),
        "external_flows": pd.Series(flow_values, index=index, dtype=float),
        "transaction_costs": pd.Series(cost_values, index=index, dtype=float),
        "holding_results": holding_results,
    }


def simulate_portfolio(prices, allocation, capital, rebalance_frequency):
    zero_dividends = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    return simulate_portfolio_with_dividends(
        prices,
        zero_dividends,
        allocation,
        capital,
        rebalance_frequency,
    )["value"]


def calculate_metrics(series, capital, dividends=None, risk_free_rate=0.02):
    """Compatibility wrapper around the tested weekly analytics implementation."""
    return calculate_portfolio_metrics(series, capital, dividends, risk_free_rate)


def build_named_comparison(
    series_by_name,
    capital,
    dividends_by_name=None,
    risk_free_rate=0.02,
):
    if len(series_by_name) < 2:
        raise ValueError("At least two series are required for comparison.")

    common_index = None
    for series in series_by_name.values():
        valid_index = series.dropna().index
        common_index = (
            valid_index if common_index is None else common_index.intersection(valid_index)
        )

    if common_index is None or len(common_index) < 5:
        raise ValueError("Not enough overlapping price data for the selected comparisons.")

    aligned_series = {name: series.reindex(common_index) for name, series in series_by_name.items()}
    dividends_by_name = dividends_by_name or {}
    aligned_dividends = {
        name: (
            dividends_by_name.get(name)
            if dividends_by_name.get(name) is not None
            else pd.Series(dtype=float)
        )
        .reindex(common_index)
        .fillna(0.0)
        for name in aligned_series
    }
    metrics = {
        name: calculate_metrics(series, capital, aligned_dividends[name], risk_free_rate)
        for name, series in aligned_series.items()
    }
    return {
        "index": common_index,
        "series": aligned_series,
        "dividends": aligned_dividends,
        "metrics": metrics,
    }


def build_dividend_panel(comparison, entity_labels, entity_colors, entity_strategies=None):
    figure = go.Figure()
    event_records = []
    summary_cards = []
    entity_strategies = entity_strategies or {}

    for key in ["portfolio_1", "portfolio_2", "benchmark"]:
        if key not in comparison["dividends"]:
            continue
        label = entity_labels[key]
        color = entity_colors[key]
        dividend_series = comparison["dividends"][key]
        cumulative = dividend_series.cumsum()
        nonzero = dividend_series[dividend_series > 0]

        if not nonzero.empty:
            customdata = np.column_stack([cumulative.reindex(nonzero.index).values])
            figure.add_trace(
                go.Bar(
                    x=nonzero.index,
                    y=nonzero.values,
                    name=label,
                    marker={
                        "color": color,
                        "line": {"color": "#1a1a19", "width": 1},
                    },
                    customdata=customdata,
                    hovertemplate=(
                        "%{x|%Y-%m-%d}<br>"
                        + label
                        + "<br>Weekly dividend: $%{y:,.2f}<br>"
                        + "Cumulative: $%{customdata[0]:,.2f}<extra></extra>"
                    ),
                )
            )
            for date, value in nonzero.items():
                event_records.append(
                    {
                        "Week": date.strftime("%Y-%m-%d"),
                        "Entity": label,
                        "Weekly Dividend": f"${value:,.2f}",
                        "Cumulative Dividends": f"${cumulative.loc[date]:,.2f}",
                        "_date": date,
                    }
                )

        metrics = comparison["metrics"][key]
        strategy_text = entity_strategies.get(key, "")
        summary_cards.append(
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.Div(
                                [
                                    html.Span(
                                        "●",
                                        style={"color": color},
                                        className="me-2",
                                    ),
                                    html.Strong(label, className="text-white"),
                                ]
                            ),
                            html.Div(
                                strategy_text,
                                className="text-muted small mt-1 mb-2",
                            )
                            if strategy_text
                            else None,
                            html.Div(
                                f"Gross dividends: ${metrics['cumulative_dividends']:,.2f}",
                                className="text-light mt-1",
                            ),
                            html.Small(
                                f"Avg. yearly yield: {metrics['average_yearly_dividend_yield'] * 100:.2f}%",
                                className="text-muted",
                            ),
                        ]
                    ),
                    className="bg-black border-secondary h-100",
                ),
                md=4,
            )
        )

    figure.update_layout(
        title="Weekly Gross Dividend Income",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis_title="Week Ending",
        yaxis_title="Dividend Income ($)",
        barmode="group",
        hovermode="closest",
        legend={"orientation": "h", "y": 1.02, "x": 0, "font": {"size": 10}},
        margin={"l": 48, "r": 16, "t": 48, "b": 40},
        font={"size": 11, "color": "#c3c2b7"},
        title_font={"size": 14, "color": "#e7e8ea"},
    )

    if not event_records:
        figure.add_annotation(
            text="No dividend payments occurred during this reporting period.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"color": "#c3c2b7", "size": 15},
        )
        events_table = html.Div(
            "No weekly dividend events to display.",
            className="text-muted text-center py-3",
        )
    else:
        event_records.sort(key=lambda record: record["_date"], reverse=True)
        events_df = pd.DataFrame(event_records[:100]).drop(columns=["_date"])
        events_table = dbc.Table.from_dataframe(
            events_df,
            striped=True,
            bordered=True,
            hover=True,
            responsive=True,
            color="dark",
            className="text-center small",
        )

    return summary_cards, figure, events_table


def build_growth_summary(capital, entity_rows):
    """Build the compact value and return summary shown under the growth chart."""
    summary_rows = [
        {
            "Name": name,
            "Value": f"${value:,.2f}" if np.isfinite(value) else "N/A",
            "Growth": f"{growth * 100:.2f}%" if np.isfinite(growth) else "N/A",
            "CAGR": f"{cagr * 100:.2f}%" if np.isfinite(cagr) else "N/A",
        }
        for name, value, growth, cagr in entity_rows
    ]
    table = dbc.Table.from_dataframe(
        pd.DataFrame(summary_rows, columns=["Name", "Value", "Growth", "CAGR"]),
        striped=True,
        bordered=True,
        hover=True,
        responsive=True,
        color="dark",
        className="text-center mb-0",
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Strong("Initial Investment: "),
                    f"${capital:,.2f}",
                ],
                className="small mb-2",
            ),
            table,
        ]
    )


def _breakdown_metric(value, metric_type):
    if not np.isfinite(value):
        return "N/A"
    if metric_type == "currency":
        return f"${value:,.2f}"
    return f"{value * 100:.2f}%"


def build_breakdown_panel(entities):
    """Build sortable holdings and performance tables for active entities."""
    panels = []
    for entity in entities:
        metrics = entity["metrics"]
        holding_results = entity.get("holding_results", {})
        summary = pd.DataFrame(
            [
                {
                    "Name": entity["name"],
                    "End Value": _breakdown_metric(metrics["ending_balance"], "currency"),
                    "Total Dividends": _breakdown_metric(
                        metrics["cumulative_dividends"], "currency"
                    ),
                    "Yearly Dividends": _breakdown_metric(
                        metrics["average_yearly_dividends"], "currency"
                    ),
                    "Dividend Yield": _breakdown_metric(
                        metrics["average_yearly_dividend_yield"], "percent"
                    ),
                    "Total Growth": _breakdown_metric(metrics["total_return"], "percent"),
                    "CAGR": _breakdown_metric(metrics["cagr"], "percent"),
                }
            ]
        )
        holdings = pd.DataFrame(
            [
                {
                    "Holding": ticker,
                    "Allocation": f"{weight:.2f}%",
                    "Start Value": _breakdown_metric(
                        holding_results.get(ticker, {}).get("start_value", float("nan")),
                        "currency",
                    ),
                    "End Value": _breakdown_metric(
                        holding_results.get(ticker, {}).get("end_value", float("nan")),
                        "currency",
                    ),
                    "Total Growth": _breakdown_metric(
                        holding_results.get(ticker, {}).get("total_growth", float("nan")),
                        "percent",
                    ),
                    "CAGR": _breakdown_metric(
                        holding_results.get(ticker, {}).get("cagr", float("nan")),
                        "percent",
                    ),
                }
                for ticker, weight in entity["allocation"].items()
            ],
            columns=[
                "Holding",
                "Allocation",
                "Start Value",
                "End Value",
                "Total Growth",
                "CAGR",
            ],
        )
        panels.append(
            html.Div(
                [
                    html.H6(entity["name"], className="text-info fw-bold mb-2"),
                    dash_table.DataTable(
                        id={"type": "breakdown-summary", "entity": entity["key"]},
                        data=summary.to_dict("records"),
                        columns=[{"name": column, "id": column} for column in summary.columns],
                        sort_action="native",
                        sort_mode="multi",
                        style_table={"overflowX": "auto"},
                        style_header={
                            "backgroundColor": "#202327",
                            "color": "#a2a7ae",
                            "fontWeight": "600",
                        },
                        style_cell={
                            "backgroundColor": "#191b1e",
                            "color": "#e7e8ea",
                            "fontSize": "12px",
                            "padding": "5px 7px",
                            "textAlign": "center",
                        },
                    ),
                    html.Div(
                        dash_table.DataTable(
                            id={"type": "breakdown-holdings", "entity": entity["key"]},
                            data=holdings.to_dict("records"),
                            columns=[{"name": column, "id": column} for column in holdings.columns],
                            sort_action="native",
                            sort_mode="multi",
                            style_table={"overflowX": "auto"},
                            style_header={
                                "backgroundColor": "#202327",
                                "color": "#a2a7ae",
                                "fontWeight": "600",
                            },
                            style_cell={
                                "backgroundColor": "#191b1e",
                                "color": "#e7e8ea",
                                "fontSize": "12px",
                                "padding": "5px 7px",
                            },
                        ),
                        className="mt-2",
                    ),
                ],
                className="mb-3",
            )
        )
    return html.Div(panels)


def build_comparison(
    portfolio_series,
    benchmark_series,
    capital,
    second_portfolio_series=None,
    portfolio_dividends=None,
    benchmark_dividends=None,
    second_portfolio_dividends=None,
    risk_free_rate=0.02,
):
    series_by_name = {"portfolio_1": portfolio_series}
    if second_portfolio_series is not None:
        series_by_name["portfolio_2"] = second_portfolio_series
    series_by_name["benchmark"] = benchmark_series

    dividends_by_name = {
        "portfolio_1": portfolio_dividends,
        "benchmark": benchmark_dividends,
    }
    if second_portfolio_series is not None:
        dividends_by_name["portfolio_2"] = second_portfolio_dividends

    comparison = build_named_comparison(
        series_by_name,
        capital,
        dividends_by_name,
        risk_free_rate,
    )
    portfolio_metrics = comparison["metrics"]["portfolio_1"]
    benchmark_metrics = comparison["metrics"]["benchmark"]
    metric_names = [
        ("Initial Capital", None, "currency"),
        ("Ending Balance", "ending_balance", "currency"),
        ("Total Return", "total_return", "percent"),
        ("CAGR", "cagr", "percent"),
        ("Annualized Volatility", "volatility", "percent"),
        ("Sharpe Ratio", "sharpe", "number"),
        ("Sortino Ratio", "sortino", "number"),
        ("Calmar Ratio", "calmar", "number"),
        ("Downside Deviation", "downside_deviation", "percent"),
        ("Best Week", "best_week", "percent"),
        ("Worst Week", "worst_week", "percent"),
        ("Max Drawdown", "max_drawdown", "percent"),
        ("Cumulative Dividends", "cumulative_dividends", "currency"),
        ("Average Yearly Dividends", "average_yearly_dividends", "currency"),
        ("Average Yearly Dividend %", "average_yearly_dividend_yield", "percent"),
    ]
    metric_rows = []
    for label, key, metric_type in metric_names:
        values = {
            name: capital if key is None else entity_metrics[key]
            for name, entity_metrics in comparison["metrics"].items()
        }
        metric_rows.append((label, values, metric_type))

    return {
        **comparison,
        "portfolio_series": comparison["series"]["portfolio_1"],
        "second_portfolio_series": comparison["series"].get("portfolio_2"),
        "benchmark_series": comparison["series"]["benchmark"],
        "portfolio_metrics": portfolio_metrics,
        "second_portfolio_metrics": comparison["metrics"].get("portfolio_2"),
        "benchmark_metrics": benchmark_metrics,
        "metric_rows": metric_rows,
        "excess_balance": portfolio_metrics["ending_balance"] - benchmark_metrics["ending_balance"],
        "excess_return": portfolio_metrics["total_return"] - benchmark_metrics["total_return"],
    }


DEFAULT_INVESTMENT = 1_000_000
DEFAULT_PORTFOLIO_VALUE = portfolio_value("predefined", "Classic 60/40")

app.layout = dbc.Container(
    [
        # Only user-created portfolios are persisted in browser storage.
        dcc.Store(id="user-portfolios-store", storage_type="local", data={}),
        # Navbar
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Div(
                            [
                                html.I(className="fas fa-chart-line app-logo me-2"),
                                html.H2(
                                    "Backtest Portfolio",
                                    className="app-title text-white d-inline-block fw-semibold mb-0",
                                ),
                                html.Span(
                                    "Portfolio Backtester & Manager",
                                    className="app-subtitle text-muted ms-2",
                                ),
                            ],
                            className="app-header d-flex align-items-center",
                        )
                    ]
                )
            ]
        ),
        # Top-Level Navigation Tabs
        dbc.Tabs(
            [
                # Tab 1: Backtester Workbench
                dbc.Tab(
                    label="Backtest Workbench",
                    tab_id="tab-workbench",
                    children=[
                        dbc.Row(
                            [
                                # Left Sidebar: Controls & Configuration
                                dbc.Col(
                                    [
                                        html.Div(
                                            [
                                                html.H5(
                                                    "Portfolio Configuration",
                                                    className="mb-2 fw-semibold",
                                                ),
                                                # Preset / Portfolio Selector
                                                html.Label(
                                                    "Select Portfolio:",
                                                    className="form-label text-white-50 small",
                                                ),
                                                dcc.Dropdown(
                                                    id="preset-dropdown",
                                                    options=[],  # Populated from predefined and user portfolios
                                                    value=DEFAULT_PORTFOLIO_VALUE,
                                                    clearable=False,
                                                    className="mb-1 text-dark",
                                                ),
                                                html.Div(
                                                    dbc.Badge(
                                                        "Predefined portfolio",
                                                        id="workbench-portfolio-type-badge",
                                                        color="info",
                                                        pill=True,
                                                    ),
                                                    className="mb-3",
                                                ),
                                                html.Label(
                                                    "Compare with Second Portfolio (Optional):",
                                                    className="form-label text-white-50 small",
                                                ),
                                                dcc.Dropdown(
                                                    id="second-portfolio-dropdown",
                                                    options=optional_portfolio_options({}),
                                                    value="",
                                                    clearable=True,
                                                    placeholder="No second portfolio",
                                                    className="mb-1 text-dark",
                                                ),
                                                html.Div(
                                                    dbc.Badge(
                                                        "No second portfolio",
                                                        id="second-portfolio-type-badge",
                                                        color="secondary",
                                                        pill=True,
                                                    ),
                                                    id="second-portfolio-badge-container",
                                                    className="mb-3",
                                                ),
                                                html.P(
                                                    "Asset allocations are viewed and edited on the Portfolio Manager tab.",
                                                    className="text-muted small mb-3",
                                                ),
                                                html.Hr(className="border-secondary"),
                                                # Date Range & Investment
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            [
                                                                html.Label(
                                                                    "Start Date:",
                                                                    className="form-label text-white-50 small",
                                                                ),
                                                                dcc.DatePickerSingle(
                                                                    id="start-date-picker",
                                                                    date=(
                                                                        datetime.now()
                                                                        - timedelta(days=365 * 3)
                                                                    ).strftime("%Y-%m-%d"),
                                                                    display_format="YYYY-MM-DD",
                                                                    className="mb-2 w-100",
                                                                ),
                                                            ],
                                                            width=6,
                                                        ),
                                                        dbc.Col(
                                                            [
                                                                html.Label(
                                                                    "End Date:",
                                                                    className="form-label text-white-50 small",
                                                                ),
                                                                dcc.DatePickerSingle(
                                                                    id="end-date-picker",
                                                                    date=datetime.now().strftime(
                                                                        "%Y-%m-%d"
                                                                    ),
                                                                    display_format="YYYY-MM-DD",
                                                                    className="mb-2 w-100",
                                                                ),
                                                            ],
                                                            width=6,
                                                        ),
                                                    ]
                                                ),
                                                html.Div(
                                                    [
                                                        html.Label(
                                                            "Initial Investment ($):",
                                                            className="form-label text-white-50 small",
                                                        ),
                                                        dbc.Input(
                                                            id="initial-capital",
                                                            type="number",
                                                            value=DEFAULT_INVESTMENT,
                                                            min=0.01,
                                                            className="mb-2 bg-dark text-white border-secondary",
                                                        ),
                                                    ]
                                                ),
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            [
                                                                html.Label(
                                                                    "Risk-free rate (%)",
                                                                    className="form-label",
                                                                ),
                                                                dbc.Input(
                                                                    id="risk-free-rate",
                                                                    type="number",
                                                                    value=2.0,
                                                                    step=0.1,
                                                                    className="bg-dark text-white border-secondary",
                                                                ),
                                                            ],
                                                            md=6,
                                                        ),
                                                        dbc.Col(
                                                            [
                                                                html.Label(
                                                                    "Inflation (%)",
                                                                    className="form-label",
                                                                ),
                                                                dbc.Input(
                                                                    id="inflation-rate",
                                                                    type="number",
                                                                    value=0.0,
                                                                    step=0.1,
                                                                    className="bg-dark text-white border-secondary",
                                                                ),
                                                            ],
                                                            md=6,
                                                        ),
                                                    ],
                                                    className="g-2 mb-2",
                                                ),
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            [
                                                                html.Label(
                                                                    "Recurring flow ($)",
                                                                    className="form-label",
                                                                ),
                                                                dbc.Input(
                                                                    id="recurring-flow",
                                                                    type="number",
                                                                    value=0.0,
                                                                    className="bg-dark text-white border-secondary",
                                                                ),
                                                            ],
                                                            md=6,
                                                        ),
                                                        dbc.Col(
                                                            [
                                                                html.Label(
                                                                    "Flow frequency",
                                                                    className="form-label",
                                                                ),
                                                                dcc.Dropdown(
                                                                    id="flow-frequency",
                                                                    options=[
                                                                        {
                                                                            "label": "None",
                                                                            "value": "None",
                                                                        },
                                                                        {
                                                                            "label": "Monthly",
                                                                            "value": "Month",
                                                                        },
                                                                        {
                                                                            "label": "Annual",
                                                                            "value": "Year",
                                                                        },
                                                                    ],
                                                                    value="None",
                                                                    clearable=False,
                                                                    className="text-dark",
                                                                ),
                                                            ],
                                                            md=6,
                                                        ),
                                                    ],
                                                    className="g-2 mb-2",
                                                ),
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            [
                                                                html.Label(
                                                                    "Trading cost (%)",
                                                                    className="form-label",
                                                                ),
                                                                dbc.Input(
                                                                    id="transaction-cost-percent",
                                                                    type="number",
                                                                    value=0.0,
                                                                    min=0,
                                                                    step=0.01,
                                                                    className="bg-dark text-white border-secondary",
                                                                ),
                                                            ],
                                                            md=4,
                                                        ),
                                                        dbc.Col(
                                                            [
                                                                html.Label(
                                                                    "Fixed cost ($)",
                                                                    className="form-label",
                                                                ),
                                                                dbc.Input(
                                                                    id="transaction-cost-fixed",
                                                                    type="number",
                                                                    value=0.0,
                                                                    min=0,
                                                                    className="bg-dark text-white border-secondary",
                                                                ),
                                                            ],
                                                            md=4,
                                                        ),
                                                        dbc.Col(
                                                            [
                                                                html.Label(
                                                                    "Cash yield (%)",
                                                                    className="form-label",
                                                                ),
                                                                dbc.Input(
                                                                    id="cash-yield",
                                                                    type="number",
                                                                    value=0.0,
                                                                    step=0.1,
                                                                    className="bg-dark text-white border-secondary",
                                                                ),
                                                            ],
                                                            md=4,
                                                        ),
                                                    ],
                                                    className="g-2 mb-2",
                                                ),
                                                dbc.Checkbox(
                                                    id="force-refresh",
                                                    label="Refresh market data",
                                                    value=False,
                                                    className="mb-2",
                                                ),
                                                html.Div(
                                                    [
                                                        html.H6(
                                                            "Portfolio Strategies",
                                                            className="fw-semibold mb-2",
                                                        ),
                                                        html.Div(
                                                            [
                                                                html.Div(
                                                                    "Portfolio 1",
                                                                    id="portfolio-1-strategy-title",
                                                                    className="strategy-title",
                                                                ),
                                                                dbc.Row(
                                                                    [
                                                                        dbc.Col(
                                                                            [
                                                                                html.Label(
                                                                                    "Rebalance",
                                                                                    className="form-label",
                                                                                ),
                                                                                dcc.Dropdown(
                                                                                    id="portfolio-1-rebalance-freq",
                                                                                    options=[
                                                                                        {
                                                                                            "label": "Buy & Hold",
                                                                                            "value": "None",
                                                                                        },
                                                                                        {
                                                                                            "label": "Annual",
                                                                                            "value": "Year",
                                                                                        },
                                                                                        {
                                                                                            "label": "Monthly",
                                                                                            "value": "Month",
                                                                                        },
                                                                                        {
                                                                                            "label": "5% Drift Threshold",
                                                                                            "value": "Threshold",
                                                                                        },
                                                                                    ],
                                                                                    value="Year",
                                                                                    clearable=False,
                                                                                    className="text-dark",
                                                                                ),
                                                                            ],
                                                                            md=6,
                                                                        ),
                                                                        dbc.Col(
                                                                            [
                                                                                html.Label(
                                                                                    "Dividends",
                                                                                    className="form-label",
                                                                                ),
                                                                                dcc.Dropdown(
                                                                                    id="portfolio-1-dividend-mode",
                                                                                    options=[
                                                                                        {
                                                                                            "label": "Hold as Cash",
                                                                                            "value": "cash",
                                                                                        },
                                                                                        {
                                                                                            "label": "Reinvest",
                                                                                            "value": "reinvest",
                                                                                        },
                                                                                    ],
                                                                                    value="cash",
                                                                                    clearable=False,
                                                                                    className="text-dark",
                                                                                ),
                                                                            ],
                                                                            md=6,
                                                                        ),
                                                                    ],
                                                                    className="g-2",
                                                                ),
                                                            ],
                                                            className="strategy-row",
                                                        ),
                                                        html.Div(
                                                            [
                                                                html.Div(
                                                                    "Portfolio 2",
                                                                    id="portfolio-2-strategy-title",
                                                                    className="strategy-title",
                                                                ),
                                                                dbc.Row(
                                                                    [
                                                                        dbc.Col(
                                                                            [
                                                                                html.Label(
                                                                                    "Rebalance",
                                                                                    className="form-label",
                                                                                ),
                                                                                dcc.Dropdown(
                                                                                    id="portfolio-2-rebalance-freq",
                                                                                    options=[
                                                                                        {
                                                                                            "label": "Buy & Hold",
                                                                                            "value": "None",
                                                                                        },
                                                                                        {
                                                                                            "label": "Annual",
                                                                                            "value": "Year",
                                                                                        },
                                                                                        {
                                                                                            "label": "Monthly",
                                                                                            "value": "Month",
                                                                                        },
                                                                                        {
                                                                                            "label": "5% Drift Threshold",
                                                                                            "value": "Threshold",
                                                                                        },
                                                                                    ],
                                                                                    value="Year",
                                                                                    clearable=False,
                                                                                    className="text-dark",
                                                                                ),
                                                                            ],
                                                                            md=6,
                                                                        ),
                                                                        dbc.Col(
                                                                            [
                                                                                html.Label(
                                                                                    "Dividends",
                                                                                    className="form-label",
                                                                                ),
                                                                                dcc.Dropdown(
                                                                                    id="portfolio-2-dividend-mode",
                                                                                    options=[
                                                                                        {
                                                                                            "label": "Hold as Cash",
                                                                                            "value": "cash",
                                                                                        },
                                                                                        {
                                                                                            "label": "Reinvest",
                                                                                            "value": "reinvest",
                                                                                        },
                                                                                    ],
                                                                                    value="cash",
                                                                                    clearable=False,
                                                                                    className="text-dark",
                                                                                ),
                                                                            ],
                                                                            md=6,
                                                                        ),
                                                                    ],
                                                                    className="g-2",
                                                                ),
                                                            ],
                                                            id="portfolio-2-strategy-row",
                                                            className="strategy-row",
                                                            style={"display": "none"},
                                                        ),
                                                        html.Div(
                                                            "Benchmark: Annual rebalance · Reinvest dividends",
                                                            className="strategy-benchmark-note",
                                                        ),
                                                    ],
                                                    className="strategy-panel mb-2",
                                                ),
                                                html.Div(
                                                    [
                                                        html.Label(
                                                            "Comparison Benchmark:",
                                                            className="form-label text-white-50 small",
                                                        ),
                                                        dcc.Dropdown(
                                                            id="benchmark-dropdown",
                                                            options=benchmark_options(),
                                                            value=DEFAULT_BENCHMARK,
                                                            clearable=False,
                                                            className="mb-1 text-dark",
                                                        ),
                                                        html.Div(
                                                            dbc.Badge(
                                                                "Fixed benchmark",
                                                                id="workbench-benchmark-type-badge",
                                                                color="secondary",
                                                                pill=True,
                                                            ),
                                                            className="mb-3",
                                                        ),
                                                    ]
                                                ),
                                                dbc.Button(
                                                    "Run Backtest",
                                                    id="run-button",
                                                    color="primary",
                                                    className="w-100 py-2 fw-bold shadow-sm",
                                                ),
                                            ],
                                            className="compact-panel mt-2",
                                        )
                                    ],
                                    lg=4,
                                    md=5,
                                ),
                                # Right Content: Charts & Metrics
                                dbc.Col(
                                    [
                                        dbc.Spinner(
                                            [
                                                html.Div(
                                                    [
                                                        # Summary Metric Cards
                                                        html.Div(
                                                            id="summary-cards",
                                                            className="compact-summary row text-center",
                                                        ),
                                                        html.Div(
                                                            id="analysis-status",
                                                            className="small text-muted mb-2",
                                                        ),
                                                        dbc.Accordion(
                                                            [
                                                                dbc.AccordionItem(
                                                                    [
                                                                        html.Ul(
                                                                            [
                                                                                html.Li(
                                                                                    "Weekly, unadjusted Yahoo Finance closes; fractional shares are supported."
                                                                                ),
                                                                                html.Li(
                                                                                    "Dividends are credited before scheduled or threshold rebalancing."
                                                                                ),
                                                                                html.Li(
                                                                                    "Taxes and bid/ask spreads are excluded; configured trading costs are deducted."
                                                                                ),
                                                                                html.Li(
                                                                                    "Cash yield, inflation, recurring flows, and the risk-free rate use the selected assumptions."
                                                                                ),
                                                                                html.Li(
                                                                                    "Results are constrained by ticker history and the common overlapping date range."
                                                                                ),
                                                                            ],
                                                                            className="mb-0",
                                                                        )
                                                                    ],
                                                                    title="Methodology & assumptions",
                                                                )
                                                            ],
                                                            start_collapsed=True,
                                                            className="mb-2",
                                                        ),
                                                        # Sub-tabs for Visualizations
                                                        dbc.Tabs(
                                                            [
                                                                dbc.Tab(
                                                                    label="Growth",
                                                                    tab_id="subtab-growth",
                                                                    children=[
                                                                        html.Div(
                                                                            [
                                                                                dcc.Graph(
                                                                                    id="growth-chart",
                                                                                    style={
                                                                                        "height": "370px"
                                                                                    },
                                                                                ),
                                                                                html.Div(
                                                                                    id="growth-summary",
                                                                                    className="mt-2",
                                                                                ),
                                                                            ],
                                                                            className="compact-panel compact-chart-panel mt-1",
                                                                        )
                                                                    ],
                                                                ),
                                                                dbc.Tab(
                                                                    label="Drawdown",
                                                                    tab_id="subtab-drawdown",
                                                                    children=[
                                                                        html.Div(
                                                                            [
                                                                                dcc.Graph(
                                                                                    id="drawdown-chart",
                                                                                    style={
                                                                                        "height": "370px"
                                                                                    },
                                                                                )
                                                                            ],
                                                                            className="compact-panel compact-chart-panel mt-1",
                                                                        )
                                                                    ],
                                                                ),
                                                                dbc.Tab(
                                                                    label="Correlation",
                                                                    tab_id="subtab-corr",
                                                                    children=[
                                                                        html.Div(
                                                                            [
                                                                                dcc.Graph(
                                                                                    id="corr-chart",
                                                                                    style={
                                                                                        "height": "370px"
                                                                                    },
                                                                                )
                                                                            ],
                                                                            className="compact-panel compact-chart-panel mt-1",
                                                                        )
                                                                    ],
                                                                ),
                                                                dbc.Tab(
                                                                    label="Metrics",
                                                                    tab_id="subtab-metrics",
                                                                    children=[
                                                                        html.Div(
                                                                            id="metrics-table-container",
                                                                            className="compact-panel mt-1",
                                                                        )
                                                                    ],
                                                                ),
                                                                dbc.Tab(
                                                                    label="Breakdown",
                                                                    tab_id="subtab-breakdown",
                                                                    children=[
                                                                        html.Div(
                                                                            id="breakdown-container",
                                                                            className="compact-panel mt-1",
                                                                        )
                                                                    ],
                                                                ),
                                                                dbc.Tab(
                                                                    label="Dividends",
                                                                    tab_id="subtab-dividends",
                                                                    children=[
                                                                        html.Div(
                                                                            [
                                                                                html.Div(
                                                                                    id="dividend-summary",
                                                                                    className="row g-2 mb-3",
                                                                                ),
                                                                                dcc.Graph(
                                                                                    id="dividend-chart",
                                                                                    style={
                                                                                        "height": "340px"
                                                                                    },
                                                                                ),
                                                                                html.Div(
                                                                                    id="dividend-events-container",
                                                                                    className="mt-2",
                                                                                ),
                                                                            ],
                                                                            className="compact-panel compact-chart-panel mt-1",
                                                                        )
                                                                    ],
                                                                ),
                                                            ],
                                                            id="result-subtabs",
                                                            active_tab="subtab-growth",
                                                            className="mt-3",
                                                        ),
                                                    ]
                                                )
                                            ],
                                            color="primary",
                                            type="border",
                                        )
                                    ],
                                    lg=8,
                                    md=7,
                                ),
                            ],
                            className="mt-2",
                        )
                    ],
                ),
                # Tab 2: Portfolio Manager & Editor
                dbc.Tab(
                    label="Portfolio Manager",
                    tab_id="tab-manager",
                    children=[
                        html.Div(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                html.H4(
                                                    "Manage Portfolios",
                                                    className="fw-semibold mb-1",
                                                ),
                                                html.P(
                                                    "Create and edit saved allocations. Changes are stored locally.",
                                                    className="text-muted small mb-2",
                                                ),
                                            ]
                                        )
                                    ]
                                ),
                                dbc.Row(
                                    [
                                        # Left Column: Portfolio selector & actions
                                        dbc.Col(
                                            [
                                                html.Div(
                                                    [
                                                        html.Label(
                                                            "Select Portfolio to Edit:",
                                                            className="form-label text-white-50 small",
                                                        ),
                                                        dcc.Dropdown(
                                                            id="manager-portfolio-dropdown",
                                                            options=[],
                                                            clearable=False,
                                                            className="mb-3 text-dark",
                                                        ),
                                                        dbc.Button(
                                                            "➕ New Portfolio",
                                                            id="btn-new-portfolio",
                                                            color="success",
                                                            className="w-100 mb-2 fw-bold",
                                                        ),
                                                        dbc.Button(
                                                            "Delete Portfolio",
                                                            id="btn-delete-portfolio",
                                                            color="danger",
                                                            outline=True,
                                                            className="w-100 mb-2 fw-bold",
                                                        ),
                                                        dbc.Button(
                                                            "Clone Portfolio",
                                                            id="btn-clone-portfolio",
                                                            color="secondary",
                                                            className="w-100 mb-2",
                                                        ),
                                                        dbc.Button(
                                                            "Export Portfolios",
                                                            id="btn-export-portfolios",
                                                            color="secondary",
                                                            className="w-100 mb-2",
                                                        ),
                                                        dcc.Upload(
                                                            id="upload-portfolios",
                                                            children=dbc.Button(
                                                                "Import Portfolios",
                                                                color="secondary",
                                                                className="w-100",
                                                            ),
                                                            className="d-block mb-2",
                                                        ),
                                                        dcc.Download(id="download-portfolios"),
                                                        html.Hr(className="border-secondary"),
                                                        html.Div(
                                                            id="portfolio-validation-alert",
                                                            className="mt-2",
                                                        ),
                                                    ],
                                                    className="compact-panel",
                                                )
                                            ],
                                            lg=4,
                                            md=5,
                                        ),
                                        # Right Column: Editable DataTable
                                        dbc.Col(
                                            [
                                                html.Div(
                                                    [
                                                        html.H5(
                                                            "Asset Allocation Grid",
                                                            className="text-white mb-3",
                                                        ),
                                                        html.P(
                                                            "Edit asset ticker symbols and weight percentages directly in the table below.",
                                                            className="text-muted small",
                                                        ),
                                                        html.Div(
                                                            [
                                                                dash_table.DataTable(
                                                                    id="portfolio-editor-table",
                                                                    columns=[
                                                                        {
                                                                            "name": "Asset (Ticker)",
                                                                            "id": "asset",
                                                                            "editable": True,
                                                                        },
                                                                        {
                                                                            "name": "Weight (%)",
                                                                            "id": "weight",
                                                                            "editable": True,
                                                                            "type": "numeric",
                                                                        },
                                                                    ],
                                                                    data=[],
                                                                    editable=True,
                                                                    row_deletable=True,
                                                                    style_header={
                                                                        "backgroundColor": "#202327",
                                                                        "color": "#a2a7ae",
                                                                        "fontWeight": "600",
                                                                        "fontSize": "12px",
                                                                        "padding": "5px 7px",
                                                                        "border": "1px solid #34383e",
                                                                    },
                                                                    style_cell={
                                                                        "backgroundColor": "#191b1e",
                                                                        "color": "#e7e8ea",
                                                                        "fontSize": "12px",
                                                                        "padding": "5px 7px",
                                                                        "minHeight": "29px",
                                                                        "border": "1px solid #34383e",
                                                                        "textAlign": "center",
                                                                    },
                                                                )
                                                            ],
                                                            className="mb-3",
                                                        ),
                                                        dbc.Row(
                                                            [
                                                                dbc.Col(
                                                                    dbc.Button(
                                                                        "Add Row",
                                                                        id="btn-add-row",
                                                                        color="secondary",
                                                                        size="sm",
                                                                        className="me-2",
                                                                    )
                                                                ),
                                                                dbc.Col(
                                                                    dbc.Button(
                                                                        "Normalize",
                                                                        id="btn-normalize-portfolio",
                                                                        color="secondary",
                                                                        size="sm",
                                                                        className="me-2",
                                                                    )
                                                                ),
                                                                dbc.Col(
                                                                    dbc.Button(
                                                                        "Save Portfolio",
                                                                        id="btn-save-portfolio",
                                                                        color="primary",
                                                                        size="sm",
                                                                        className="float-end fw-bold",
                                                                    )
                                                                ),
                                                            ]
                                                        ),
                                                    ],
                                                    className="compact-panel",
                                                )
                                            ],
                                            lg=8,
                                            md=7,
                                        ),
                                    ]
                                ),
                            ],
                            className="compact-manager mt-2",
                        )
                    ],
                ),
            ],
            id="main-tabs",
            active_tab="tab-workbench",
            className="mt-3",
        ),
        # Modal for New Portfolio Creation
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle("Create New Portfolio", className="text-dark")),
                dbc.ModalBody(
                    [
                        html.Label("Portfolio Name:", className="form-label text-dark"),
                        dbc.Input(
                            id="new-portfolio-name",
                            placeholder="e.g. Dividend Growth",
                            className="mb-3",
                        ),
                    ]
                ),
                dbc.ModalFooter(
                    [
                        dbc.Button(
                            "Cancel", id="btn-modal-cancel", color="secondary", className="me-2"
                        ),
                        dbc.Button("Create", id="btn-modal-create", color="primary"),
                    ]
                ),
            ],
            id="new-portfolio-modal",
            is_open=False,
        ),
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle("Delete portfolio?")),
                dbc.ModalBody("This removes the selected browser-local portfolio."),
                dbc.ModalFooter(
                    [
                        dbc.Button("Cancel", id="btn-delete-cancel", color="secondary"),
                        dbc.Button("Delete", id="btn-delete-confirm", color="danger"),
                    ]
                ),
            ],
            id="delete-portfolio-modal",
            is_open=False,
        ),
    ],
    fluid=True,
    className="compact-app min-vh-100 pb-3",
)


# Populate workbench, optional comparison, and manager portfolio selectors.
@app.callback(
    [
        Output("preset-dropdown", "options"),
        Output("preset-dropdown", "value"),
        Output("second-portfolio-dropdown", "options"),
        Output("second-portfolio-dropdown", "value"),
        Output("manager-portfolio-dropdown", "options"),
        Output("manager-portfolio-dropdown", "value"),
    ],
    Input("user-portfolios-store", "data"),
    [
        State("preset-dropdown", "value"),
        State("second-portfolio-dropdown", "value"),
        State("manager-portfolio-dropdown", "value"),
    ],
)
def update_dropdowns(
    user_portfolios,
    current_workbench_val,
    current_second_val,
    current_manager_val,
):
    options = portfolio_options(user_portfolios)
    optional_options = optional_portfolio_options(user_portfolios)
    values = {option["value"] for option in options}
    first_value = first_portfolio_value(options)

    wb_val = current_workbench_val if current_workbench_val in values else first_value
    second_val = current_second_val if current_second_val in values else ""
    mgr_val = current_manager_val if current_manager_val in values else first_value

    return options, wb_val, optional_options, second_val, options, mgr_val


# Update the workbench portfolio type badge.
@app.callback(
    [
        Output("workbench-portfolio-type-badge", "children"),
        Output("workbench-portfolio-type-badge", "color"),
    ],
    Input("preset-dropdown", "value"),
)
def update_workbench_portfolio_badge(selected_portfolio):
    portfolio_type, _ = parse_portfolio_value(selected_portfolio)
    badge_label = portfolio_type_label(selected_portfolio)
    badge_color = "primary" if portfolio_type == "user" else "info"
    return badge_label, badge_color


@app.callback(
    [
        Output("second-portfolio-type-badge", "children"),
        Output("second-portfolio-type-badge", "color"),
    ],
    Input("second-portfolio-dropdown", "value"),
)
def update_second_portfolio_badge(selected_portfolio):
    if not selected_portfolio:
        return "No second portfolio", "secondary"
    portfolio_type, _ = parse_portfolio_value(selected_portfolio)
    badge_color = "primary" if portfolio_type == "user" else "info"
    return portfolio_type_label(selected_portfolio), badge_color


@app.callback(
    [
        Output("portfolio-1-strategy-title", "children"),
        Output("portfolio-2-strategy-title", "children"),
        Output("portfolio-2-strategy-row", "style"),
    ],
    [
        Input("preset-dropdown", "value"),
        Input("second-portfolio-dropdown", "value"),
    ],
)
def update_strategy_rows(primary_selection, second_selection):
    primary_name = portfolio_display_name(primary_selection, "Portfolio 1")
    second_name = portfolio_display_name(second_selection, "Portfolio 2")
    second_style = {} if second_selection else {"display": "none"}
    return (
        f"Portfolio 1 · {primary_name}",
        f"Portfolio 2 · {second_name}",
        second_style,
    )


# Load the selected portfolio and enable editing only for user portfolios.
@app.callback(
    [
        Output("portfolio-editor-table", "data"),
        Output("portfolio-editor-table", "editable"),
        Output("portfolio-editor-table", "row_deletable"),
        Output("btn-add-row", "disabled"),
        Output("btn-save-portfolio", "disabled"),
        Output("btn-delete-portfolio", "disabled"),
        Output("portfolio-validation-alert", "children"),
    ],
    [Input("manager-portfolio-dropdown", "value"), Input("user-portfolios-store", "data")],
)
def load_manager_table(selected_portfolio, user_portfolios):
    portfolio_type, _ = parse_portfolio_value(selected_portfolio)
    portfolio = get_portfolio(selected_portfolio, user_portfolios)
    rows = [{"asset": k, "weight": v} for k, v in portfolio.items()]
    is_user_portfolio = portfolio_type == "user"

    total_wt = sum(portfolio.values())
    if abs(total_wt - 100.0) < 0.01:
        weight_message = "✓ Total weight equals 100%"
        alert_color = "success"
    else:
        weight_message = f"⚠ Total weight is {total_wt:.1f}% (should equal 100%)"
        alert_color = "warning"

    if not is_user_portfolio:
        weight_message = f"🔒 Predefined portfolio — read only. {weight_message}"
        alert_color = "info"

    alert = dbc.Alert(weight_message, color=alert_color, className="py-2 small mb-0")
    controls_disabled = not is_user_portfolio
    return (
        rows,
        is_user_portfolio,
        is_user_portfolio,
        controls_disabled,
        controls_disabled,
        controls_disabled,
        alert,
    )


# Callback to add a blank row in the DataTable
@app.callback(
    Output("portfolio-editor-table", "data", allow_duplicate=True),
    Input("btn-add-row", "n_clicks"),
    State("portfolio-editor-table", "data"),
    prevent_initial_call=True,
)
def add_table_row(n_clicks, rows):
    return [*(rows or []), {"asset": "", "weight": 0.0}]


@app.callback(
    Output("portfolio-editor-table", "data", allow_duplicate=True),
    Input("btn-normalize-portfolio", "n_clicks"),
    State("portfolio-editor-table", "data"),
    prevent_initial_call=True,
)
def normalize_portfolio_table(n_clicks, rows):
    return normalize_rows(rows) if n_clicks else dash.no_update


# Save edits only when the selected portfolio is user-defined.
@app.callback(
    Output("user-portfolios-store", "data"),
    Input("btn-save-portfolio", "n_clicks"),
    [
        State("manager-portfolio-dropdown", "value"),
        State("portfolio-editor-table", "data"),
        State("user-portfolios-store", "data"),
    ],
    prevent_initial_call=True,
)
def save_portfolio(n_clicks, selected_portfolio, rows, user_portfolios):
    portfolio_type, portfolio_name = parse_portfolio_value(selected_portfolio)
    if not n_clicks or portfolio_type != "user" or not portfolio_name:
        return dash.no_update

    new_portfolio, errors = validate_allocation_rows(rows)
    blocking_errors = [error for error in errors if "duplicate rows" not in error]
    if blocking_errors:
        return dash.no_update

    updated_portfolios = dict(user_portfolios or {})
    updated_portfolios[portfolio_name] = new_portfolio
    return updated_portfolios


# Modal toggle callbacks for New Portfolio
@app.callback(
    Output("new-portfolio-modal", "is_open"),
    [
        Input("btn-new-portfolio", "n_clicks"),
        Input("btn-modal-cancel", "n_clicks"),
        Input("btn-modal-create", "n_clicks"),
    ],
    State("new-portfolio-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_modal(btn_new, btn_cancel, btn_create, is_open):
    if not ctx.triggered:
        return is_open
    button_id = ctx.triggered_id
    if button_id in ["btn-new-portfolio", "btn-modal-cancel", "btn-modal-create"]:
        return not is_open
    return is_open


# Create a new user-defined portfolio from the modal.
@app.callback(
    [
        Output("user-portfolios-store", "data", allow_duplicate=True),
        Output("manager-portfolio-dropdown", "value", allow_duplicate=True),
        Output("new-portfolio-name", "value"),
    ],
    Input("btn-modal-create", "n_clicks"),
    [State("new-portfolio-name", "value"), State("user-portfolios-store", "data")],
    prevent_initial_call=True,
)
def create_new_portfolio(n_clicks, name, user_portfolios):
    if not n_clicks or not name:
        return dash.no_update, dash.no_update, dash.no_update

    clean_name = name.strip()
    if not clean_name:
        return dash.no_update, dash.no_update, ""

    updated_portfolios = dict(user_portfolios or {})
    existing_name = next(
        (
            existing
            for existing in updated_portfolios
            if existing.casefold() == clean_name.casefold()
        ),
        None,
    )
    if existing_name is not None:
        return dash.no_update, dash.no_update, clean_name
    updated_portfolios[clean_name] = {"SPY": 100.0}

    selected_value = portfolio_value("user", clean_name)
    return updated_portfolios, selected_value, ""


@app.callback(
    Output("delete-portfolio-modal", "is_open"),
    [
        Input("btn-delete-portfolio", "n_clicks"),
        Input("btn-delete-cancel", "n_clicks"),
        Input("btn-delete-confirm", "n_clicks"),
    ],
    State("delete-portfolio-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_delete_modal(delete_clicks, cancel_clicks, confirm_clicks, is_open):
    return not is_open


# Delete only user-defined portfolios after explicit confirmation.
@app.callback(
    [
        Output("user-portfolios-store", "data", allow_duplicate=True),
        Output("manager-portfolio-dropdown", "value", allow_duplicate=True),
    ],
    Input("btn-delete-confirm", "n_clicks"),
    [State("manager-portfolio-dropdown", "value"), State("user-portfolios-store", "data")],
    prevent_initial_call=True,
)
def delete_portfolio(n_clicks, selected_portfolio, user_portfolios):
    portfolio_type, portfolio_name = parse_portfolio_value(selected_portfolio)
    if not n_clicks or portfolio_type != "user" or not portfolio_name:
        return dash.no_update, dash.no_update

    updated_portfolios = dict(user_portfolios or {})
    if portfolio_name not in updated_portfolios:
        return dash.no_update, dash.no_update

    del updated_portfolios[portfolio_name]
    return updated_portfolios, DEFAULT_PORTFOLIO_VALUE


@app.callback(
    [
        Output("user-portfolios-store", "data", allow_duplicate=True),
        Output("manager-portfolio-dropdown", "value", allow_duplicate=True),
    ],
    Input("btn-clone-portfolio", "n_clicks"),
    [State("manager-portfolio-dropdown", "value"), State("user-portfolios-store", "data")],
    prevent_initial_call=True,
)
def clone_portfolio(n_clicks, selected_portfolio, user_portfolios):
    if not n_clicks:
        return dash.no_update, dash.no_update
    source = get_portfolio(selected_portfolio, user_portfolios)
    if not source:
        return dash.no_update, dash.no_update
    base = f"{portfolio_display_name(selected_portfolio)} Copy"
    existing = {name.casefold() for name in (user_portfolios or {})}
    name = base
    suffix = 2
    while name.casefold() in existing:
        name = f"{base} {suffix}"
        suffix += 1
    updated = dict(user_portfolios or {})
    updated[name] = dict(source)
    return updated, portfolio_value("user", name)


@app.callback(
    Output("download-portfolios", "data"),
    Input("btn-export-portfolios", "n_clicks"),
    State("user-portfolios-store", "data"),
    prevent_initial_call=True,
)
def download_portfolios(n_clicks, user_portfolios):
    if not n_clicks:
        return dash.no_update
    return dcc.send_string(
        export_portfolios_json(user_portfolios or {}), "testfolio-portfolios.json"
    )


@app.callback(
    Output("user-portfolios-store", "data", allow_duplicate=True),
    Input("upload-portfolios", "contents"),
    [State("upload-portfolios", "filename"), State("user-portfolios-store", "data")],
    prevent_initial_call=True,
)
def upload_portfolios(contents, filename, current):
    if not contents:
        return dash.no_update
    try:
        _, encoded = contents.split(",", 1)
        imported = import_portfolios_json(base64.b64decode(encoded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return dash.no_update
    merged = dict(current or {})
    existing = {name.casefold() for name in merged}
    for name, allocation in imported.items():
        if name.casefold() in existing:
            continue
        merged[name] = allocation
        existing.add(name.casefold())
    return merged


# Main Backtest & Dashboard Renderer Callback
@app.callback(
    [
        Output("summary-cards", "children"),
        Output("growth-chart", "figure"),
        Output("growth-summary", "children"),
        Output("breakdown-container", "children"),
        Output("drawdown-chart", "figure"),
        Output("corr-chart", "figure"),
        Output("metrics-table-container", "children"),
        Output("dividend-summary", "children"),
        Output("dividend-chart", "figure"),
        Output("dividend-events-container", "children"),
        Output("analysis-status", "children"),
    ],
    Input("run-button", "n_clicks"),
    [
        State("start-date-picker", "date"),
        State("end-date-picker", "date"),
        State("initial-capital", "value"),
        State("benchmark-dropdown", "value"),
        State("second-portfolio-dropdown", "value"),
        State("user-portfolios-store", "data"),
        State("preset-dropdown", "value"),
        State("portfolio-1-rebalance-freq", "value"),
        State("portfolio-1-dividend-mode", "value"),
        State("portfolio-2-rebalance-freq", "value"),
        State("portfolio-2-dividend-mode", "value"),
        State("risk-free-rate", "value"),
        State("inflation-rate", "value"),
        State("recurring-flow", "value"),
        State("flow-frequency", "value"),
        State("transaction-cost-percent", "value"),
        State("transaction-cost-fixed", "value"),
        State("cash-yield", "value"),
        State("force-refresh", "value"),
    ],
)
def run_backtest(
    n_clicks,
    start_date,
    end_date,
    capital,
    benchmark_name,
    second_selection,
    user_portfolios,
    primary_selection,
    portfolio_1_rebalance,
    portfolio_1_dividend_mode,
    portfolio_2_rebalance,
    portfolio_2_dividend_mode,
    risk_free_rate,
    inflation_rate,
    recurring_flow,
    flow_frequency,
    transaction_cost_percent,
    transaction_cost_fixed,
    cash_yield,
    force_refresh,
):

    try:
        start_date, end_date, capital = validate_backtest_request(
            start_date,
            end_date,
            capital,
            (portfolio_1_rebalance, portfolio_2_rebalance),
            (portfolio_1_dividend_mode, portfolio_2_dividend_mode),
        )
        risk_free_rate = float(risk_free_rate or 0) / 100.0
        inflation_rate = float(inflation_rate or 0) / 100.0
        recurring_flow = float(recurring_flow or 0)
        transaction_cost_percent = max(float(transaction_cost_percent or 0), 0.0)
        transaction_cost_fixed = max(float(transaction_cost_fixed or 0), 0.0)
        cash_yield = float(cash_yield or 0) / 100.0
    except (ValueError, TypeError) as error:
        empty_fig = px.line(title="Invalid backtest settings")
        empty_fig.update_layout(template="plotly_dark")
        message = html.Div(str(error), className="text-danger")
        return (
            [],
            empty_fig,
            None,
            None,
            empty_fig,
            empty_fig,
            message,
            [],
            empty_fig,
            "",
            str(error),
        )

    portfolio = get_portfolio(primary_selection, user_portfolios)
    if not portfolio:
        empty_fig = px.line(title="Selected Portfolio 1 is no longer available.")
        empty_fig.update_layout(template="plotly_dark")
        message = html.Div(
            "Selected Portfolio 1 is no longer available. Choose another portfolio.",
            className="text-danger",
        )
        return [], empty_fig, None, None, empty_fig, empty_fig, message, [], empty_fig, "", message

    benchmark_name = benchmark_name if benchmark_name in BENCHMARK_PORTFOLIOS else DEFAULT_BENCHMARK
    benchmark = BENCHMARK_PORTFOLIOS[benchmark_name]
    second_portfolio = (
        get_portfolio(second_selection, user_portfolios) if second_selection else None
    )
    if second_selection and not second_portfolio:
        second_selection = ""
        second_portfolio = None

    ticker_groups = [portfolio, benchmark]
    if second_portfolio:
        ticker_groups.append(second_portfolio)
    tickers = list(dict.fromkeys(ticker for allocation in ticker_groups for ticker in allocation))

    empty_fig = px.line(title="No data available or error fetching tickers.")
    empty_fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )

    try:
        prices, dividends, provenance = load_cached_market_data(
            tickers,
            start_date,
            end_date,
            force_refresh=bool(force_refresh),
            include_provenance=True,
        )
        missing_tickers = [
            ticker
            for ticker in tickers
            if ticker not in prices.columns or prices[ticker].dropna().empty
        ]
        if missing_tickers:
            raise ValueError(f"No price data for: {', '.join(missing_tickers)}")
        prices = prices[tickers].dropna(how="all")
        target_index = pd.date_range(
            start=pd.Timestamp(start_date),
            end=pd.Timestamp(end_date),
            freq="W-FRI",
        )
        prices, dividends, fill_warnings = fill_limited_history(
            prices,
            dividends,
            tickers,
            provenance["warnings"],
            target_index=target_index,
        )
        provenance["warnings"] = fill_warnings
        if prices.isna().any().any():
            raise ValueError("Unable to fill missing price history for all selected tickers.")
        dividends = dividends.reindex(
            index=prices.index,
            columns=tickers,
            fill_value=0.0,
        ).fillna(0.0)
        for ticker in tickers:
            provenance["tickers"].setdefault(ticker, {})
            provenance["tickers"][ticker]["synthetic_price_history"] = any(
                ticker in warning for warning in provenance["warnings"]
            )
        portfolio_result = simulate_portfolio_with_dividends(
            prices,
            dividends,
            portfolio,
            capital,
            portfolio_1_rebalance,
            portfolio_1_dividend_mode,
            recurring_flow,
            flow_frequency,
            transaction_cost_percent,
            transaction_cost_fixed,
            cash_yield,
            0.05,
            inflation_rate,
        )
        benchmark_result = simulate_portfolio_with_dividends(
            prices,
            dividends,
            benchmark,
            capital,
            "Year",
            "reinvest",
        )
        second_portfolio_result = (
            simulate_portfolio_with_dividends(
                prices,
                dividends,
                second_portfolio,
                capital,
                portfolio_2_rebalance,
                portfolio_2_dividend_mode,
                recurring_flow,
                flow_frequency,
                transaction_cost_percent,
                transaction_cost_fixed,
                cash_yield,
                0.05,
                inflation_rate,
            )
            if second_portfolio
            else None
        )
        portfolio_series = portfolio_result["value"]
        benchmark_series = benchmark_result["value"]
        second_portfolio_series = (
            second_portfolio_result["value"] if second_portfolio_result else None
        )
    except Exception as error:
        logger.exception("Backtest market-data or simulation failure")
        message = f"Unable to complete the backtest: {error}"
        return (
            [],
            empty_fig,
            None,
            None,
            empty_fig,
            html.Div(message, className="text-danger"),
            [],
            empty_fig,
            "",
            message,
        )

    try:
        comparison = build_comparison(
            portfolio_series,
            benchmark_series,
            capital,
            second_portfolio_series,
            portfolio_result["dividends"],
            benchmark_result["dividends"],
            (second_portfolio_result["dividends"] if second_portfolio_result else None),
            risk_free_rate,
        )
    except ValueError as error:
        return (
            [],
            empty_fig,
            None,
            None,
            empty_fig,
            empty_fig,
            html.Div(str(error), className="text-danger"),
            [],
            empty_fig,
            "",
            str(error),
        )

    common_index = comparison["index"]
    portfolio_series = comparison["portfolio_series"]
    second_portfolio_series = comparison["second_portfolio_series"]
    benchmark_series = comparison["benchmark_series"]
    portfolio_metrics = comparison["portfolio_metrics"]
    second_portfolio_metrics = comparison["second_portfolio_metrics"]
    benchmark_metrics = comparison["benchmark_metrics"]
    excess_balance = comparison["excess_balance"]
    excess_return = comparison["excess_return"]
    excess_class = "text-success" if excess_balance >= 0 else "text-danger"
    primary_name = portfolio_display_name(primary_selection, "Portfolio 1")
    second_name = portfolio_display_name(second_selection, "Portfolio 2")
    portfolio_1_label = f"Portfolio 1 — {primary_name}"
    portfolio_2_label = f"Portfolio 2 — {second_name}"

    cards = [
        dbc.Col(
            dbc.Card(
                [
                    dbc.CardBody(
                        [
                            html.H6("Portfolio 1 Balance", className="text-muted"),
                            html.H4(
                                f"${portfolio_metrics['ending_balance']:,.2f}",
                                className="text-white fw-bold",
                            ),
                        ]
                    )
                ],
                className="border-secondary",
            ),
            md=3,
        ),
        dbc.Col(
            dbc.Card(
                [
                    dbc.CardBody(
                        [
                            html.H6("Portfolio 1 CAGR", className="text-muted"),
                            html.H4(
                                f"{portfolio_metrics['cagr'] * 100:.2f}%",
                                className="text-white fw-semibold",
                            ),
                        ]
                    )
                ],
                className="border-secondary",
            ),
            md=3,
        ),
    ]
    if second_portfolio_metrics:
        cards.extend(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H6("Portfolio 2 Balance", className="text-muted"),
                                    html.H4(
                                        f"${second_portfolio_metrics['ending_balance']:,.2f}",
                                        className="text-white fw-bold",
                                    ),
                                ]
                            )
                        ],
                        className="border-secondary",
                    ),
                    md=3,
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H6("Portfolio 2 CAGR", className="text-muted"),
                                    html.H4(
                                        f"{second_portfolio_metrics['cagr'] * 100:.2f}%",
                                        className="text-white fw-semibold",
                                    ),
                                ]
                            )
                        ],
                        className="border-secondary",
                    ),
                    md=3,
                ),
            ]
        )
    else:
        cards.extend(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H6(f"vs. {benchmark_name}", className="text-muted"),
                                    html.H4(
                                        f"{excess_return * 100:+.2f}%",
                                        className=f"{excess_class} fw-bold",
                                    ),
                                ]
                            )
                        ],
                        className="border-secondary",
                    ),
                    md=3,
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H6("Excess Ending Value", className="text-muted"),
                                    html.H4(
                                        f"${excess_balance:+,.2f}",
                                        className=f"{excess_class} fw-bold",
                                    ),
                                ]
                            )
                        ],
                        className="border-secondary",
                    ),
                    md=3,
                ),
            ]
        )

    growth_fig = go.Figure()
    growth_fig.add_trace(
        go.Scatter(
            x=common_index,
            y=portfolio_series,
            name=portfolio_1_label,
            mode="lines",
            line={"color": "#3987e5", "width": 2},
        )
    )
    if second_portfolio_series is not None:
        growth_fig.add_trace(
            go.Scatter(
                x=common_index,
                y=second_portfolio_series,
                name=portfolio_2_label,
                mode="lines",
                line={"color": "#d95926", "width": 2, "dash": "dot"},
            )
        )
    growth_fig.add_trace(
        go.Scatter(
            x=common_index,
            y=benchmark_series,
            name=benchmark_name,
            mode="lines",
            line={"color": "#199e70", "width": 2, "dash": "dash"},
        )
    )
    growth_summary = build_growth_summary(
        capital,
        [
            (
                portfolio_1_label,
                portfolio_metrics["ending_balance"],
                portfolio_metrics["total_return"],
                portfolio_metrics["cagr"],
            ),
            *(
                [
                    (
                        portfolio_2_label,
                        second_portfolio_metrics["ending_balance"],
                        second_portfolio_metrics["total_return"],
                        second_portfolio_metrics["cagr"],
                    )
                ]
                if second_portfolio_metrics
                else []
            ),
            (
                benchmark_name,
                benchmark_metrics["ending_balance"],
                benchmark_metrics["total_return"],
                benchmark_metrics["cagr"],
            ),
        ],
    )
    breakdown_entities = [
        {
            "key": "portfolio-1",
            "name": portfolio_1_label,
            "allocation": portfolio,
            "metrics": portfolio_metrics,
            "holding_results": portfolio_result["holding_results"],
        },
        *(
            [
                {
                    "key": "portfolio-2",
                    "name": portfolio_2_label,
                    "allocation": second_portfolio,
                    "metrics": second_portfolio_metrics,
                    "holding_results": second_portfolio_result["holding_results"],
                }
            ]
            if second_portfolio_metrics
            else []
        ),
        {
            "key": "benchmark",
            "name": benchmark_name,
            "allocation": benchmark,
            "metrics": benchmark_metrics,
            "holding_results": benchmark_result["holding_results"],
        },
    ]
    breakdown_panel = build_breakdown_panel(breakdown_entities)
    growth_fig.update_layout(
        title=f"Portfolio Comparison vs. {benchmark_name}",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis_title="Date",
        yaxis_title="Value ($)",
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.02, "x": 0, "font": {"size": 10}},
        margin={"l": 48, "r": 16, "t": 48, "b": 40},
        font={"size": 11, "color": "#c3c2b7"},
        title_font={"size": 14, "color": "#e7e8ea"},
    )

    drawdown_fig = go.Figure()
    drawdown_fig.add_trace(
        go.Scatter(
            x=common_index,
            y=portfolio_metrics["drawdown"] * 100,
            name=portfolio_1_label,
            mode="lines",
            line={"color": "#3987e5", "width": 2},
        )
    )
    if second_portfolio_metrics:
        drawdown_fig.add_trace(
            go.Scatter(
                x=common_index,
                y=second_portfolio_metrics["drawdown"] * 100,
                name=portfolio_2_label,
                mode="lines",
                line={"color": "#d95926", "width": 2, "dash": "dot"},
            )
        )
    drawdown_fig.add_trace(
        go.Scatter(
            x=common_index,
            y=benchmark_metrics["drawdown"] * 100,
            name=benchmark_name,
            mode="lines",
            line={"color": "#199e70", "width": 2, "dash": "dash"},
        )
    )
    drawdown_fig.update_layout(
        title=f"Drawdown vs. {benchmark_name}",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis_title="Date",
        yaxis_title="Drawdown (%)",
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.02, "x": 0, "font": {"size": 10}},
        margin={"l": 48, "r": 16, "t": 48, "b": 40},
        font={"size": 11, "color": "#c3c2b7"},
        title_font={"size": 14, "color": "#e7e8ea"},
    )

    portfolio_prices = prices[list(portfolio)].reindex(common_index)
    correlation = portfolio_prices.pct_change().dropna().corr()
    correlation_fig = px.imshow(
        correlation,
        text_auto=True,
        color_continuous_scale="RdBu_r",
        zmin=-1,
        zmax=1,
        title="Portfolio 1 Asset Correlation Matrix",
    )
    correlation_fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 48, "r": 16, "t": 48, "b": 40},
        font={"size": 11, "color": "#c3c2b7"},
        title_font={"size": 14, "color": "#e7e8ea"},
    )

    def format_metric(value, metric_type, signed=False):
        if not np.isfinite(value):
            return "N/A"
        sign = "+" if signed else ""
        if metric_type == "currency":
            return f"${value:{sign},.2f}"
        if metric_type == "percent":
            return f"{value * 100:{sign}.2f}%"
        return f"{value:{sign}.2f}"

    metric_records = []
    for label, values, metric_type in comparison["metric_rows"]:
        portfolio_1_value = values["portfolio_1"]
        benchmark_value = values["benchmark"]
        record = {
            "Metric": label,
            "Portfolio 1": format_metric(portfolio_1_value, metric_type),
        }
        if "portfolio_2" in values:
            portfolio_2_value = values["portfolio_2"]
            record["Portfolio 2"] = format_metric(portfolio_2_value, metric_type)
        record[benchmark_name] = format_metric(benchmark_value, metric_type)
        record["P1 vs Benchmark"] = format_metric(
            portfolio_1_value - benchmark_value,
            metric_type,
            signed=True,
        )
        if "portfolio_2" in values:
            record["P2 vs Benchmark"] = format_metric(
                portfolio_2_value - benchmark_value,
                metric_type,
                signed=True,
            )
        metric_records.append(record)

    metrics_df = pd.DataFrame(metric_records)
    table = dbc.Table.from_dataframe(
        metrics_df,
        striped=True,
        bordered=True,
        hover=True,
        responsive=True,
        color="dark",
        className="text-center",
    )
    table = html.Div(
        [
            html.H6("Risk & Return", className="text-info fw-bold mb-2"),
            table,
            html.P(
                "Dividend Income rows report gross distributions received under either dividend treatment.",
                className="text-muted small mt-2 mb-0",
            ),
        ]
    )

    entity_labels = {
        "portfolio_1": portfolio_1_label,
        "portfolio_2": portfolio_2_label,
        "benchmark": benchmark_name,
    }
    entity_colors = {
        "portfolio_1": "#3987e5",
        "portfolio_2": "#d95926",
        "benchmark": "#199e70",
    }
    dividend_summary, dividend_figure, dividend_events = build_dividend_panel(
        comparison,
        entity_labels,
        entity_colors,
    )
    relative = benchmark_relative_metrics(
        portfolio_series,
        benchmark_series,
        risk_free_rate,
    )
    all_warnings = list(
        dict.fromkeys(
            warning
            for metrics in comparison["metrics"].values()
            for warning in metrics.get("warnings", [])
        )
    )
    source_summary = (
        f"Network: {len(provenance['downloaded_windows'])} window(s); "
        f"cache hits: {len(provenance['cache_hits'])}."
    )
    analysis_status = html.Div(
        [
            html.Strong(
                f"Effective period: {common_index.min().date()} to {common_index.max().date()} · "
                f"Source: {provenance['provider']} · {source_summary}"
            ),
            html.Div(
                f"Risk-free rate: {risk_free_rate * 100:.2f}% · "
                f"Beta: {relative['beta']:.2f} · Alpha: {relative['alpha'] * 100:.2f}% · "
                f"Tracking error: {relative['tracking_error'] * 100:.2f}%"
            ),
            html.Ul(
                [html.Li(message) for message in [*all_warnings, *provenance["warnings"]]],
                className="mb-0",
            )
            if all_warnings or provenance["warnings"]
            else None,
        ]
    )

    return (
        cards,
        growth_fig,
        growth_summary,
        breakdown_panel,
        drawdown_fig,
        correlation_fig,
        table,
        dividend_summary,
        dividend_figure,
        dividend_events,
        analysis_status,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG if CONFIG.debug else logging.INFO)
    app.run(host=CONFIG.host, port=CONFIG.port, debug=CONFIG.debug)
