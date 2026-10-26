"""Standalone, GUI-free public API for portfolio analytics."""

from .analytics import (
    benchmark_relative_metrics,
    calculate_metrics,
    periodic_return_tables,
    rolling_metrics,
)
from .db_cache import DEFAULT_CACHE_PATH, DbCache
from .market_data import extract_market_data, to_weekly_market_data
from .portfolios import (
    clean_allocation_rows,
    export_portfolios_json,
    import_portfolios_json,
    normalize_allocation,
    normalize_rows,
    parse_portfolio_value,
    portfolio_display_name,
    portfolio_value,
    validate_allocation_rows,
)
from .simulation import simulate_portfolio_with_dividends
from .validation import validate_backtest_request

__all__ = [
    "DEFAULT_CACHE_PATH",
    "DbCache",
    "benchmark_relative_metrics",
    "calculate_metrics",
    "clean_allocation_rows",
    "extract_market_data",
    "export_portfolios_json",
    "import_portfolios_json",
    "normalize_allocation",
    "normalize_rows",
    "parse_portfolio_value",
    "periodic_return_tables",
    "portfolio_display_name",
    "portfolio_value",
    "rolling_metrics",
    "simulate_portfolio_with_dividends",
    "to_weekly_market_data",
    "validate_allocation_rows",
    "validate_backtest_request",
]
