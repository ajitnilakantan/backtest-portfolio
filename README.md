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
```

* Linting
```bash
uv run ruff check .  # Run linter
uv run ruff check . --fix  # Run linter and try to fix warnings
uv format [--check] # Format code, optionally only check

# FYI:
uv run ruff linter  # Lists available linters
uv run ruff analyze graph # Print out dependency graph
```

* Check dependencies
```bash
uv run --with deptry deptry "$(git rev-parse --show-toplevel)" --config "$(git rev-parse --show-toplevel)/pyproject.toml"
```

* Sanitize/check pyproject.toml
```bash
uv run --with pytomlcleaner pytomlcleaner
uv run --with validate-pyproject validate-pyproject pyproject.toml
```

### Running program

* Running cli front end
```bash
uv run -m main
```

* Running the Jupyter frontend
```bash
# Old "notebook" frontend
uv run jupyter notebook --notebook-dir=$(git rev-parse --show-toplevel)/notebooks
# Newer "jupyter lab" frontend


## Help

* Modify the portfolio and date range to customize
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
