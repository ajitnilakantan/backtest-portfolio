from dataclasses import dataclass, field
from enum import StrEnum

__all__ = ["Holding", "Portfolio"]


class PortfolioType(StrEnum):
    PERCENT = "percent"
    SHARES = "shares"

@dataclass
class Holding:
    ticker: str = ""
    value: float = 0


@dataclass
class Portfolio:
    name: str = ""
    type: PortfolioType = PortfolioType.PERCENT
    holdings: list[Holding] = field(default_factory=list)


# Baseline benchmark
default_benchmark_portfolios = [
    Portfolio(name="S&P 500 Benchmark", holdings=[Holding("^GSPC", 100)]), # S&P 500
    Portfolio(name="Nasdaq-100 Benchmark", holdings=[Holding("^NDX", 100)]), # Nasdaq-100
]


# Portfolio: Ticker, percentage of holdings, description
default_portfolios = [
    Portfolio(
        name="Vanguard Canadian",
        holdings=[
            Holding("VGRO.TO", 80),
            Holding("XGRO.TO", 10),
            Holding("VEQT.TO", 10),
        ],
    ),
    Portfolio(
        name="Tech Stocks",
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
        holdings=[
            Holding("QQQ", 100),
        ],
    ),
    Portfolio(
        # See: https://www.holdingschannel.com/13f/cascade-investment-advisors-inc-top-holdings/
        name="BillG",
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
