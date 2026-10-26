from __future__ import annotations

import json
from pathlib import Path

from .portfolios import normalize_allocation

DEFAULT_BENCHMARK = "S&P 500"


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


def load_benchmark_registry(path):
    try:
        with Path(path).open(encoding="utf-8") as registry_file:
            registry = json.load(registry_file)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Unable to load benchmark registry '{path}': {error}") from error
    return validate_benchmark_registry(registry)
