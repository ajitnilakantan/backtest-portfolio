# Portfolio Backtester

Simple backtesting of portfolio with option to rebalance holdings yearly

## Description

A Jupyter Notebook that allows you to define a stock portfolio, assigning percentages to each holding.
Backtests the portfolio and compares with a benchmark.
Optionally re-balance the holdings yearly.

## Getting Started

### Dependencies

* uv
Install from [Astral](https://docs.astral.sh/uv/getting-started/installation/ "Installation instructions")

### Development

* Running tests
```bash
uv run pytest
uv run pytest --doctest-modules # Run the docstring embedded tests

```

* Linting
```bash
uv run ruff check .  # Run linter
uv run ruff check . --fix  # Run linter and try to fix warnings
uv run --with vulture vulture src # Look for unused methods etc.
uv format [--check] # Format code, optionally only check

# FYI:
uv run ruff linter  # Lists available linters
uv run ruff analyze graph # Print out dependency graph
```

* Check dependencies; find unused dependencies
```bash
uv run --with deptry deptry "$(git rev-parse --show-toplevel)" --config "$(git rev-parse --show-toplevel)/pyproject.toml"
```

* Update dependencies to latest versions
```bash
uv lock --upgrade # Update lock file
uvx uv-bump # External tool to sync lock file with pyproject.toml
```

* Sanitize/check pyproject.toml
```bash
uv run --with pytomlcleaner pytomlcleaner
uv run --with validate-pyproject validate-pyproject pyproject.toml
```

* AI related
```bash
# Adding marimo skills
uvx add-skills marimo-team/skills --agent claude-code
```

### Running program

* Running cli front end
```bash
uv run -m main
```

* Running the Jupyter frontend
```bash
# Run the project without the code cells
uv run voila "$(git rev-parse --show-toplevel)/notebooks/Backtest.ipynb"

# Old "notebook" frontend
uv run jupyter notebook --notebook-dir="$(git rev-parse --show-toplevel)/notebooks" "$(git rev-parse --show-toplevel)/notebooks/Backtest.ipynb"

# New "lab" frontend
uv run jupyter lab --notebook-dir="$(git rev-parse --show-toplevel)/notebooks" "$(git rev-parse --show-toplevel)/notebooks/Backtest.ipynb"
```

* Running the Marimo frontend
```bash
uv run marimo run --sandbox notebooks/backtest_marimo.py
```
## Notes

### This entry in pyproject.toml opens the marimo app in its own window
```toml
[tool.marimo.server]
browser = "uv run open_chromeless_window.py %s"
```

### Publishing Marimo to wasm/html
Note: This is broken.  All dependencies need to be pure python and some transitive dependencies like curl-cffi have native code.

For future reference:

```bash
# Marimo py files ignore pyproject.toml dependencies, so manually add them:
uv add --script .\notebooks\backtest_marimo.py altair inquirerpy ipython ipywidgets itables marimo numpy pandas python-dateutil tabulate yfinance backtest

# Export to an html/wasm project
uv run --with backtest  marimo export html-wasm --output marimo_export/ --mode run --sandbox --force notebooks/backtest_marimo.py

# Serve the project output
uv run python -m http.server --directory marimo_export
# Open http://localhost:8000  in your browser
```

### Publishing a Jupyter notebook using voici:

Note: This is also broken.  All dependencies need to be pure python.

For future reference:

```bash
uv add --dev voici-core
uv run --with backtest voici build --contents notebooks/Backtest.ipynb --output-dir jupyter_export
uv run python -m http.server --directory jupyter_export

```
## Help

* If a stock is not avalable on Yahoo Finance, will get an exception

## Authors

* ajitnilakantan

## Version History

* 0.2
    * Fixed bitrot
    * Moved to "uv"
    * Removed Anaconda dependencies
    * Added marimo front-end
* 0.1
    * Initial Release

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details

## Acknowledgments

* Uses Yahoo Finance to get historical data
