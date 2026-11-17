# Developer commands for Watchtower. Run `just` to see them all.
# Install just with `uv tool install rust-just` (or from https://just.systems).

# List the available commands
default:
    @just --list --unsorted

# Install the project and its development tools
install:
    @uv sync

# Run the tests; extra arguments go to pytest, e.g. `just test tests/test_cli.py` or `just test -k cli`
test *args:
    @uv run pytest {{ args }}

# Report lint problems
lint:
    @uv run ruff check .

# Fix formatting and the lint problems ruff can fix by itself
format:
    @uv run ruff format .
    @uv run ruff check --fix .

# Check types
typecheck:
    @uv run mypy

# Run everything CI runs; do this before pushing
check:
    @uv run ruff check .
    @uv run ruff format --check .
    @uv run mypy
    @uv run pytest --cov=watchtower

# Run the tests with coverage and write the HTML report to .artifacts/coverage/html
coverage:
    @uv run pytest --cov=watchtower --cov-report=html

# Remove generated files: tool caches, coverage data and Python bytecode
clean:
    @rm -rf .artifacts
    @find . -path ./.venv -prune -o -name __pycache__ -type d -exec rm -rf {} +

# Run the app, e.g. `just watchtower run examples/config.yaml`
watchtower *args:
    @uv run watchtower {{ args }}

# Serve the fake listings website for demos, e.g. `just serve --port 8001`
serve *args:
    @uv run watchtower-fake-listings {{ args }}
