class TestfolioError(Exception):
    """Base class for expected application errors."""


class InputValidationError(TestfolioError, ValueError):
    """The requested analysis settings are invalid."""


class MarketDataError(TestfolioError):
    """Market data could not be retrieved or interpreted."""


class InsufficientDataError(TestfolioError):
    """The requested entities do not have enough overlapping observations."""
