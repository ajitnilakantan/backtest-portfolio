# Justfile

# Force variables to be evaluated at runtime
set positional-arguments

# By default run all recipes as scripts
set default-script := true

# Fail on unset variables, errors, pipe errors
set shell := ["bash", "-euo", "pipefail", "-c"]

# Detect the operating system family (returns 'windows', 'unix', etc.)
os_family := os_family()

# Define platform-specific tools and flags dynamically
clean_cmd := if os_family == "windows" { "Remove-Item -Recurse -Force" } else { "rm -rf" }
exe_ext   := if os_family == "windows" { ".exe" } else { "" }
mkdir_cmd := if os_family == "windows" { "New-Item -ItemType Directory -Force" } else { "mkdir -p" }

# Set standard variables
default := "help"


# Fetch the repository root and project name from git
project_root := shell("git rev-parse --show-toplevel")
project_name := shell(f"basename {{ project_root }}")

# Get the current date in YYYYMMDD format
current_date := shell("date +%Y%m%d")

# Determine the backup directory based on XDG_CACHE_HOME
backup_dir   := if env_var_or_default("XDG_CACHE_HOME", "") == "" {
    clean(home_dir() / ".cache/backups")
} else {
    clean(env_var("XDG_CACHE_HOME") / "backups")
}

# Define the complete output path
archive_name := project_name + "-" + current_date + ".7z"
archive_path := backup_dir / archive_name

# List all available commands
help:
    just --list

# Backup git folder
backup:
    # Put inside ~/cache/backups/dated.7z
    @echo "Creating backup directory: {{backup_dir}}"
    @mkdir -p "{{backup_dir}}"
    @echo "Compressing {{project_name}} into {{archive_path}}..."
    @7z a -r "{{archive_path}}" "{{project_root}}/*" -xr'!__pycache__' -xr'!*.pyc' -xr'!*.log' -xr'!*.tmp' -xr'!.venv' -xr'!.git' -xr'!.pytest_cache/'

# For testing just
[script]
mytest:
    x="foo"
    export y="goo"
    printf "y=$y"
    echo "x=${x}"

# ------------------------------------------------------------------------------
# Setup & Maintenance
# ------------------------------------------------------------------------------

# Initialize local virtual environment and install all dependencies
bootstrap:
    uv sync

# Update lockfile and upgrade dependencies to latest allowed versions
update:
    uv lock --upgrade

# Clean up build artifacts, temporary caches, and environment files
clean:
    rm -rf .venv .uv .pytest_cache .ruff_cache build/ dist/ *.egg-info
    find . -type d -name "__pycache__" -exec rm -rf {} +

# ------------------------------------------------------------------------------
# Development & Testing
# ------------------------------------------------------------------------------

# Run the local development server or main entrypoint
run:
    uv run python main.py

# Format and lint code using Ruff
lint:
    uv run ruff format .
    uv run ruff check . --fix

# Run static type checking with Mypy
typecheck:
    uv run mypy .

# Execute test suite using Pytest
test *args:
    uv run pytest {{args}}

# ------------------------------------------------------------------------------
# Packaging & CI
# ------------------------------------------------------------------------------

# Run linting, typechecking, and tests in sequence
ci: lint typecheck test

# Build source distribution and wheel packages
build:
    uv build
