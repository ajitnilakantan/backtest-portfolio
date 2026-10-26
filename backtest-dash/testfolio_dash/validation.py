from __future__ import annotations

import math
from datetime import date

import pandas as pd

from .models import InputValidationError

VALID_REBALANCE = {"None", "Year", "Month", "Threshold"}
VALID_DIVIDENDS = {"cash", "reinvest"}


def validate_backtest_request(start, end, capital, rebalance_values=(), dividend_values=()):
    try:
        start_ts = pd.Timestamp(start).normalize()
        end_ts = pd.Timestamp(end).normalize()
    except (TypeError, ValueError) as error:
        raise InputValidationError("Select valid start and end dates.") from error
    if pd.isna(start_ts) or pd.isna(end_ts):
        raise InputValidationError("Select valid start and end dates.")
    if start_ts >= end_ts:
        raise InputValidationError("Start date must be before end date.")
    if start_ts.date() > date.today():
        raise InputValidationError("Start date cannot be in the future.")
    try:
        capital_value = float(capital)
    except (TypeError, ValueError) as error:
        raise InputValidationError("Initial investment must be a number.") from error
    if not math.isfinite(capital_value) or capital_value <= 0:
        raise InputValidationError("Initial investment must be positive.")
    if any(value not in VALID_REBALANCE for value in rebalance_values):
        raise InputValidationError("Choose a supported rebalancing strategy.")
    if any(value not in VALID_DIVIDENDS for value in dividend_values):
        raise InputValidationError("Choose a supported dividend strategy.")
    return start_ts, min(end_ts, pd.Timestamp(date.today())), capital_value
