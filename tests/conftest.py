from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

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
def sample_prices_df(sample_dates):
    """Weekly closing prices for AAPL and MSFT over a year."""
    start, end = sample_dates
    idx = pd.date_range(start, end, freq="W-FRI")
    data = {
        "AAPL": [150.0 + i * 0.5 for i in range(len(idx))],
        "MSFT": [200.0 + i * 0.3 for i in range(len(idx))],
    }
    return pd.DataFrame(data, index=idx)


@pytest.fixture
def sample_num_shares(sample_portfolio, sample_dates):
    """Initial share allocation DataFrame."""
    start, _ = sample_dates
    index = pd.date_range(datetime.now().date(), periods=0, freq="W")
    columns = [fund.ticker for fund in sample_portfolio.holdings]
    df = pd.DataFrame(index=index, columns=columns)
    # 100000 investment at close prices: AAPL=150, MSFT=200
    # 60% → 60000 / 150 = 400 shares AAPL
    # 40% → 40000 / 200 = 200 shares MSFT
    df.loc[start] = [400.0, 200.0]
    return df


@pytest.fixture
def benchmark_portfolio():
    """S&P 500 benchmark portfolio."""
    return Portfolio(
        name="S&P 500 Benchmark",
        type=PortfolioType.PERCENT,
        holdings=[Holding("^GSPC", 100)],
    )