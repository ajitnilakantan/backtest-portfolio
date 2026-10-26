from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

PERIODS_PER_YEAR = 52


def calculate_metrics(
    series: pd.Series,
    capital: float,
    dividends: pd.Series | None = None,
    risk_free_rate: float = 0.02,
) -> dict[str, Any]:
    if series.empty:
        raise ValueError("Cannot calculate metrics for an empty series.")
    series = series.astype(float).dropna()
    returns = series.pct_change().dropna()
    elapsed_days = (series.index[-1] - series.index[0]).days
    years = elapsed_days / 365.25
    ending_balance = float(series.iloc[-1])
    total_return = ending_balance / capital - 1
    cagr = (
        (ending_balance / capital) ** (1 / years) - 1
        if years > 0 and capital > 0 and ending_balance > 0
        else float("nan")
    )
    volatility = (
        float(returns.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR))
        if len(returns) > 1
        else float("nan")
    )
    weekly_rf = (1 + risk_free_rate) ** (1 / PERIODS_PER_YEAR) - 1
    sharpe = (
        float((returns.mean() - weekly_rf) / returns.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR))
        if len(returns) > 1 and returns.std(ddof=1) > 0
        else float("nan")
    )
    downside = returns[returns < weekly_rf] - weekly_rf
    downside_deviation = (
        float(np.sqrt(np.mean(np.square(downside))) * math.sqrt(PERIODS_PER_YEAR))
        if not downside.empty
        else 0.0
    )
    annual_return = float(returns.mean() * PERIODS_PER_YEAR) if not returns.empty else float("nan")
    sortino = (
        (annual_return - risk_free_rate) / downside_deviation
        if downside_deviation > 0
        else float("nan")
    )
    drawdown = series / series.cummax() - 1
    max_drawdown = float(drawdown.min())
    calmar = cagr / abs(max_drawdown) if np.isfinite(cagr) and max_drawdown < 0 else float("nan")
    underwater = drawdown < 0
    longest_underwater = 0
    current = 0
    for value in underwater:
        current = current + 1 if value else 0
        longest_underwater = max(longest_underwater, current)

    dividend_series = (
        dividends.reindex(series.index).fillna(0.0)
        if dividends is not None
        else pd.Series(0.0, index=series.index)
    )
    yearly_dividends = dividend_series.groupby(dividend_series.index.year).sum()
    yearly_average_values = series.groupby(series.index.year).mean()
    yearly_yields = yearly_dividends / yearly_average_values.replace(0, np.nan)
    warnings = []
    if years < 1:
        warnings.append("Annualized metrics are based on less than one year of overlapping data.")
    if len(returns) < 26:
        warnings.append("Risk metrics are based on fewer than 26 weekly returns.")

    return {
        "ending_balance": ending_balance,
        "total_return": total_return,
        "cagr": cagr,
        "volatility": volatility,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "downside_deviation": downside_deviation,
        "max_drawdown": max_drawdown,
        "drawdown": drawdown,
        "best_week": float(returns.max()) if not returns.empty else float("nan"),
        "worst_week": float(returns.min()) if not returns.empty else float("nan"),
        "weeks_underwater": longest_underwater,
        "cumulative_dividends": float(dividend_series.sum()),
        "average_yearly_dividends": float(yearly_dividends.mean())
        if not yearly_dividends.empty
        else 0.0,
        "average_yearly_dividend_yield": float(yearly_yields.fillna(0.0).mean())
        if not yearly_yields.empty
        else 0.0,
        "observation_count": len(series),
        "elapsed_years": years,
        "warnings": warnings,
    }


def benchmark_relative_metrics(
    portfolio: pd.Series, benchmark: pd.Series, risk_free_rate: float = 0.02
) -> dict[str, float]:
    frame = (
        pd.concat([portfolio.rename("portfolio"), benchmark.rename("benchmark")], axis=1)
        .dropna()
        .pct_change()
        .dropna()
    )
    if len(frame) < 2:
        return {
            key: float("nan")
            for key in ["beta", "alpha", "tracking_error", "information_ratio", "active_return"]
        }
    active = frame["portfolio"] - frame["benchmark"]
    benchmark_variance = frame["benchmark"].var(ddof=1)
    beta = (
        frame["portfolio"].cov(frame["benchmark"]) / benchmark_variance
        if benchmark_variance > 0
        else float("nan")
    )
    weekly_rf = (1 + risk_free_rate) ** (1 / PERIODS_PER_YEAR) - 1
    alpha = (
        float(
            (
                (frame["portfolio"].mean() - weekly_rf)
                - beta * (frame["benchmark"].mean() - weekly_rf)
            )
            * PERIODS_PER_YEAR
        )
        if np.isfinite(beta)
        else float("nan")
    )
    tracking_error = float(active.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR))
    active_return = float(active.mean() * PERIODS_PER_YEAR)
    information_ratio = active_return / tracking_error if tracking_error > 0 else float("nan")
    return {
        "beta": float(beta),
        "alpha": alpha,
        "tracking_error": tracking_error,
        "information_ratio": information_ratio,
        "active_return": active_return,
    }


def rolling_metrics(series: pd.Series, risk_free_rate: float = 0.02) -> dict[str, pd.DataFrame]:
    returns = series.pct_change()
    weekly_rf = (1 + risk_free_rate) ** (1 / PERIODS_PER_YEAR) - 1
    results = {}
    for years in (1, 3, 5):
        window = years * PERIODS_PER_YEAR
        rolling_return = series / series.shift(window) - 1
        rolling_volatility = returns.rolling(window).std() * math.sqrt(PERIODS_PER_YEAR)
        rolling_sharpe = (
            (returns.rolling(window).mean() - weekly_rf)
            / returns.rolling(window).std()
            * math.sqrt(PERIODS_PER_YEAR)
        )
        results[f"{years}y"] = pd.DataFrame(
            {"return": rolling_return, "volatility": rolling_volatility, "sharpe": rolling_sharpe}
        )
    return results


def periodic_return_tables(series: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    monthly = series.resample("ME").last().pct_change()
    monthly_table = monthly.to_frame("return")
    monthly_table["year"] = monthly_table.index.year
    monthly_table["month"] = monthly_table.index.month
    pivot = monthly_table.pivot(index="year", columns="month", values="return")
    yearly = series.resample("YE").last().pct_change()
    return pivot, yearly
