# Developer commands for Watchtower. Run `just` to see them all.
# Install just with `uv tool install rust-just` (or from https://just.systems).

# List the available commands
default:
    @just --list --unsorted

# Install the project and its development tools
install:
    uv sync

# Run the tests with coverage; extra arguments go to pytest, e.g. `just test -k cli`
test *args:
    uv run pytest {{ args }}

# Report lint problems
lint:
    uv run ruff check .

# Fix formatting and the lint problems ruff can fix by itself
format:
    uv run ruff format .
    uv run ruff check --fix .

# Check types
typecheck:
    uv run mypy

# Run everything CI runs; do this before pushing
check:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy
    uv run pytest

# Write the HTML coverage report to .artifacts/coverage/html
coverage:
    uv run pytest --cov-report=html

# Run the app, e.g. `just watchtower check --db demo.db`
watchtower *args:
    uv run watchtower {{ args }}

# Serve the fake listings website for demos, e.g. `just serve --port 8001`
serve *args:
    uv run watchtower-fake-listings {{ args }}
