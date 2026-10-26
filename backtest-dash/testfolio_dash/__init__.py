"""Backtest Portfolio analytics library and Dash application package."""

__version__ = "0.3.0"

from .api import (
    DEFAULT_CACHE_PATH,
    DbCache,
    benchmark_relative_metrics,
    calculate_metrics,
    clean_allocation_rows,
    export_portfolios_json,
    import_portfolios_json,
    normalize_allocation,
    normalize_rows,
    parse_portfolio_value,
    periodic_return_tables,
    portfolio_display_name,
    portfolio_value,
    rolling_metrics,
    simulate_portfolio_with_dividends,
    validate_allocation_rows,
    validate_backtest_request,
)

__all__ = [
    "DEFAULT_CACHE_PATH",
    "DbCache",
    "benchmark_relative_metrics",
    "calculate_metrics",
    "clean_allocation_rows",
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
    "validate_allocation_rows",
    "validate_backtest_request",
]
