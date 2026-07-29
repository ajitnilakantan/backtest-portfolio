"""
Module-level docstring
====================

This module contains the core data structures and utilities for the backtest portfolio
management system. It exposes the `Backtest`, `Holding`, and `Portfolio` classes
used to build, run, and analyze backtests.

The module includes a package initialization hook that configures the IPython shell
formatter to display multimedia content (JavaScript, images, HTML, and Markdown).
This is primarily useful in Jupyter notebooks.

The initialization hook ensures that IPython multimedia formats are enabled only once,
preventing redundant configuration and potential conflicts.
"""

from .api import Backtest
from .holding import Holding, Portfolio

__all__ = [
    "Backtest",
    "Holding",
    "Portfolio",
]


_initialized = False
"""
Global flag indicating whether the backtest package has been initialized.

This flag is used by the package initialization function to ensure that
IPython shell formatter configuration (enabling multimedia MIME types)
is performed only once when the package is first imported.

Variables
---------
bool
    ``True`` if the package has been initialized, ``False`` otherwise.
"""


def _initialize():
    """
    Initialize the backtest package configuration for IPython environments.

    This function sets up the IPython shell's display formatter to enable
    multimedia MIME types (JavaScript, JPEG, PNG, SVG, HTML, and Markdown).
    It is primarily used when the backtest module is imported in a Jupyter
    notebook context.

    The function performs a single initialization check using the global
    ``_initialized`` flag to ensure configuration is applied only once.

    Notes
    -----
    - This function modifies the global ``_initialized`` flag upon successful initialization.
    - In non-IPython environments (standard Python interpreter), this function has no effect.
    - The initialization hook is automatically triggered when the module is imported.

    See Also
    --------
    `_initialized` : Global initialization flag
    """
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
