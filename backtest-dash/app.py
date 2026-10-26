"""Compatibility launcher for the Dash application.

The implementation lives in :mod:`testfolio_dash.gui`; this module preserves
``uv run python app.py`` and legacy imports while keeping the GUI separate from
the standalone library modules.
"""

from testfolio_dash.gui import *  # noqa: F401,F403

if __name__ == "__main__":
    from testfolio_dash.gui import run

    run()
