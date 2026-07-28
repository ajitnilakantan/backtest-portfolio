from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from backtest.backtest import get_numrebalancedshares_column, get_numshares_column
from backtest.db_cache import DbCache
from backtest.holding import Holding, Portfolio, PortfolioType

EST = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def in_memory_db():
    """A fresh DbCache instance using an in-memory SQLite database."""
    with DbCache(db_path=":memory:") as db:
        yield db


@pytest.fixture
def sample_portfolio():
    """A simple portfolio with two holdings."""
    return Portfolio(
        name="Test Portfolio",
        type=PortfolioType.PERCENT,
        holdings=[
            Holding("AAPL", 60),
            Holding("MSFT", 40),
        ],
    )


@pytest.fixture
def sample_dates():
    """Standard start/end dates for testing."""
    start = datetime(2020, 1, 1, tzinfo=EST)
    end = datetime(2021, 1, 1, tzinfo=EST)
    return start, end


@pytest.fixture
def sample_portfolio_data(sample_dates):
    """Integrated weekly prices and share allocations for a sample portfolio."""
    start, end = sample_dates
    index = pd.date_range(start, end, freq="W-FRI")
    return pd.DataFrame(
        {
            "AAPL": [150.0 + i * 0.5 for i in range(len(index))],
            "MSFT": [200.0 + i * 0.3 for i in range(len(index))],
            get_numshares_column("AAPL"): 400.0,
            get_numshares_column("MSFT"): 200.0,
            get_numrebalancedshares_column("AAPL"): 400.0,
            get_numrebalancedshares_column("MSFT"): 200.0,
        },
        index=index,
    )


@pytest.fixture
def benchmark_portfolio():
    """S&P 500 benchmark portfolio."""
    return Portfolio(
        name="S&P 500 Benchmark",
        type=PortfolioType.PERCENT,
        holdings=[Holding("^GSPC", 100)],
    )


@pytest.fixture
def sample_benchmark_data(sample_dates):
    """Integrated weekly prices and share allocations for the benchmark."""
    start, end = sample_dates
    index = pd.date_range(start, end, freq="W-FRI")
    return pd.DataFrame(
        {
            "^GSPC": [4000.0 + i * 2 for i in range(len(index))],
            get_numshares_column("^GSPC"): 25.0,
            get_numrebalancedshares_column("^GSPC"): 25.0,
        },
        index=index,
    )
