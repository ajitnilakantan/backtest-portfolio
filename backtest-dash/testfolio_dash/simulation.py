"""Portfolio simulation compatibility API.

The Dash-compatible implementation remains in ``testfolio_dash.gui`` until
its extraction is complete; this lazy shim keeps package imports lightweight.
"""


def simulate_portfolio_with_dividends(*args, **kwargs):
    from .gui import simulate_portfolio_with_dividends as simulate

    return simulate(*args, **kwargs)


__all__ = ["simulate_portfolio_with_dividends"]
