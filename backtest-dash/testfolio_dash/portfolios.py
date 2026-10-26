from __future__ import annotations

import csv
import io
import json
import math
from collections.abc import Mapping
from typing import Any

PORTFOLIO_SCHEMA_VERSION = 1


def portfolio_value(portfolio_type: str, name: str) -> str:
    return f"{portfolio_type}:{name}"


def parse_portfolio_value(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or ":" not in value:
        return None, None
    portfolio_type, name = value.split(":", 1)
    if portfolio_type not in {"predefined", "user"} or not name.strip():
        return None, None
    return portfolio_type, name.strip()


def portfolio_display_name(value: Any, fallback: str = "Portfolio") -> str:
    _, name = parse_portfolio_value(value)
    return name or fallback


def clean_allocation_rows(rows: Any) -> dict[str, float]:
    allocation: dict[str, float] = {}
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("asset", "")).strip().upper()
        try:
            weight = float(row.get("weight", 0))
        except (TypeError, ValueError):
            continue
        if ticker and math.isfinite(weight) and weight > 0:
            allocation[ticker] = allocation.get(ticker, 0.0) + weight
    return allocation


def normalize_allocation(allocation: Any) -> dict[str, float]:
    rows = (
        [{"asset": ticker, "weight": weight} for ticker, weight in (allocation or {}).items()]
        if isinstance(allocation, Mapping)
        else []
    )
    valid = clean_allocation_rows(rows)
    total = sum(valid.values())
    return {ticker: weight / total for ticker, weight in valid.items()} if total else {}


def validate_allocation_rows(rows: Any) -> tuple[dict[str, float], list[str]]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows or [], start=1):
        if not isinstance(row, Mapping):
            errors.append(f"Row {index} is invalid.")
            continue
        ticker = str(row.get("asset", "")).strip().upper()
        if not ticker:
            errors.append(f"Row {index} needs a ticker.")
            continue
        if ticker in seen:
            errors.append(
                f"Ticker {ticker} appears more than once; duplicate rows will be combined."
            )
        seen.add(ticker)
        try:
            weight = float(row.get("weight"))
        except (TypeError, ValueError):
            errors.append(f"{ticker} needs a numeric weight.")
            continue
        if not math.isfinite(weight) or weight <= 0:
            errors.append(f"{ticker} needs a positive finite weight.")
    allocation = clean_allocation_rows(rows)
    if not allocation:
        errors.append("Add at least one valid asset before saving.")
    return allocation, errors


def normalize_rows(rows: Any) -> list[dict[str, float | str]]:
    allocation, _ = validate_allocation_rows(rows)
    total = sum(allocation.values())
    if not total:
        return list(rows or [])
    return [
        {"asset": ticker, "weight": round(weight * 100.0 / total, 6)}
        for ticker, weight in allocation.items()
    ]


def export_portfolios_json(portfolios: Mapping[str, Mapping[str, float]]) -> str:
    return json.dumps(
        {"version": PORTFOLIO_SCHEMA_VERSION, "portfolios": portfolios}, indent=2, sort_keys=True
    )


def import_portfolios_json(payload: str) -> dict[str, dict[str, float]]:
    data = json.loads(payload)
    if not isinstance(data, Mapping) or data.get("version") != PORTFOLIO_SCHEMA_VERSION:
        raise ValueError("Unsupported portfolio export version.")
    raw = data.get("portfolios")
    if not isinstance(raw, Mapping):
        raise ValueError("Portfolio export must contain a portfolios object.")
    imported: dict[str, dict[str, float]] = {}
    folded: set[str] = set()
    for raw_name, allocation in raw.items():
        name = str(raw_name).strip()
        normalized = normalize_allocation(allocation)
        if not name or not normalized or name.casefold() in folded:
            raise ValueError("Every portfolio needs a unique name and valid allocation.")
        folded.add(name.casefold())
        imported[name] = {ticker: weight * 100.0 for ticker, weight in normalized.items()}
    return imported


def export_portfolios_csv(portfolios: Mapping[str, Mapping[str, float]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["portfolio", "ticker", "weight"])
    for name, allocation in portfolios.items():
        for ticker, weight in allocation.items():
            writer.writerow([name, ticker, weight])
    return output.getvalue()
