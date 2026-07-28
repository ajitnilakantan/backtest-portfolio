"""Holding and portfolio structures for backtesting.

This module defines dataclasses and enums used to represent investment
holdings and portfolios, along with default benchmark and example portfolios
for backtesting scenarios.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import ClassVar, Final

__all__ = ["Holding", "Portfolio"]


class PortfolioType(StrEnum):
    """Types of portfolio holding specification.

    Attributes:
        PERCENT: Holdings specified as percentage of the total portfolio value.
        SHARES: Holdings specified as number of shares owned.
    """

    PERCENT = "percent"
    SHARES = "shares"


@dataclass
class Holding:
    """An individual holding within a portfolio.

    Attributes:
        ticker: Ticker symbol of the security (e.g., "AAPL", "VGRO.TO").
        value: Value of the holding. When PortfolioType.PERCENT, this is the
               percentage of the portfolio (0-100). When PortfolioType.SHARES,
               this is the number of shares owned.
    """

    ticker: str = ""
    value: float = 0


@dataclass
class Portfolio:
    """A collection of holdings representing an investment portfolio.

    Attributes:
        name: Human-readable name or label for the portfolio (e.g., "Tech Stocks").
        holdings: List of Holding objects in this portfolio.
        type: Whether holdings are specified as percentages or share counts.
    """

    name: str = ""
    holdings: list[Holding] = field(default_factory=list)
    type: PortfolioType = PortfolioType.PERCENT
    DEFAULT_INITIAL_INVESTMENT: ClassVar[Final[float]] = 1_000_000.0
    DEFAULT_USD_CAD: ClassVar[Final[float]] = 1.3

    def __init__(self, name: str, holdings: list[Holding] | str | None = None, type: PortfolioType = PortfolioType.PERCENT):
        self.name = name
        self.type = type

        if holdings is None:
            self.holdings = []
        elif isinstance(holdings, list):
            self.holdings = holdings
        elif isinstance(holdings, str):
            self.holdings = self._parse_holdings_string(holdings)
        else:
            raise TypeError("holdings must be a list of Holding objects or a comma-separated string")

    def _parse_holdings_string(self, holdings_str: str) -> list[Holding]:
        """Helper method to parse a string like 'AAPL 50, GOOGL 50' into Holding objects."""
        holdings = []
        # Split by comma,semicolon etc to get individual token pairs
        parts = re.split(r"[,;|#%\s]+", holdings_str)
        # Remove empty tokens
        parts = [x for x in parts if x]
        # Zip the even indices with the odd indices
        pairs = zip(parts[::2], parts[1::2], strict=True)
        for ticker, value_str in pairs:
            holdings.append(Holding(ticker=ticker, value=float(value_str)))
        return holdings


# Baseline benchmark portfolios for comparison
default_benchmark_portfolios = [
    Portfolio(
        name="S&P 500",
        type=PortfolioType.PERCENT,
        holdings=[Holding("^GSPC", 100)],
    ),  # S&P 500 Total Return Index
    Portfolio(
        name="Nasdaq-100",
        type=PortfolioType.PERCENT,
        holdings=[Holding("^NDX", 100)],
    ),  # Nasdaq-100 Total Return Index
]


# Example portfolio configurations with diverse asset allocation strategies
default_portfolios = [
    Portfolio(
        name="Vanguard Canadian",
        type=PortfolioType.PERCENT,
        holdings=[
            Holding("VGRO.TO", 80),
            Holding("XGRO.TO", 10),
            Holding("VEQT.TO", 10),
        ],
    ),
    Portfolio(
        name="Tech Stocks",
        type=PortfolioType.PERCENT,
        holdings=[
            Holding("AAPL", 20),
            Holding("AMZN", 20),
            Holding("NFLX", 20),
            Holding("META", 20),
            Holding("BRK-B", 20),
        ],
    ),
    Portfolio(
        name="Nasdaq QQQ",
        type=PortfolioType.PERCENT,
        holdings=[Holding("QQQ", 100)],
    ),
    Portfolio(
        # Cascade Investment Advisors (Bill Gates' investment vehicle)
        # See: https://www.holdingschannel.com/13f/cascade-investment-advisors-inc-top-holdings/
        name="BillG",
        type=PortfolioType.SHARES,
        holdings=[
            Holding("AAPL", 4077),
            Holding("MSFT", 3303),
            Holding("INTC", 2953),
            Holding("AMAT", 2405),
            Holding("FDX", 2217),
            Holding("FFIV", 2096),
            Holding("DIS", 2036),
            Holding("NTR", 1999),
            Holding("TGT", 1993),
            Holding("WSM", 1989),
            Holding("USB", 1979),
            Holding("AMGN", 1961),
            Holding("META", 1906),
            Holding("AMZN", 1872),
            Holding("SCHW", 1863),
            Holding("NVS", 1850),
            Holding("EMR", 1817),
            Holding("INFY", 1790),
            Holding("RJF", 1790),
            Holding("MET", 1788),
            Holding("JLL", 1757),
        ],
    ),
]
