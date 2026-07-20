from .api import Backtest
from .holding import Holding, Portfolio

__all__ = [
    "Backtest",
    "Holding",
    "Portfolio",
]


_initialized = False


def _initialize():
    # Store flag in the global module namespace
    global _initialized
    if _initialized:
        return
    _initialized = True

    # For Jupyter:
    from IPython.core.interactiveshell import InteractiveShell

    # Explicitly re-enable mime processing in the active shell formatter
    ip = InteractiveShell.instance()
    display_formatter = ip.display_formatter
    if display_formatter is not None:
        display_formatter.formatters["application/javascript"].enabled = True
        display_formatter.formatters["image/jpeg"].enabled = True
        display_formatter.formatters["image/png"].enabled = True
        display_formatter.formatters["image/svg+xml"].enabled = True
        display_formatter.formatters["text/html"].enabled = True
        display_formatter.formatters["text/markdown"].enabled = True

    print("backtest has been initialized!!")


# Run initialization when package is imported
_initialize()
