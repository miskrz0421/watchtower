# Developer commands for Watchtower. Run `just` to see them all.
# Install just with `uv tool install rust-just` (or from https://just.systems).

# List the available commands
default:
    @just --list --unsorted

# ---------------------------------------------------------------- setup

# Install the project and its development tools
[group('setup')]
install:
    @uv sync

# Remove generated files: tool caches, coverage data and Python bytecode
[group('setup')]
clean:
    @rm -rf .artifacts
    @find . -path ./.venv -prune -o -name __pycache__ -type d -exec rm -rf {} +

# ---------------------------------------------------------------- test

# Run the tests; extra arguments go to pytest, e.g. `just test tests/test_cli.py` or `just test -k cli`
[group('test')]
test *args:
    @uv run pytest {{ args }}

# Run the tests with coverage and write the HTML report to .artifacts/coverage/html
[group('test')]
coverage:
    @uv run pytest --cov=watchtower --cov-report=html

# ---------------------------------------------------------------- code quality

# Fix formatting and the lint problems ruff can fix by itself
[group('code quality')]
format:
    @uv run ruff format .
    @uv run ruff check --fix .

# Report lint problems
[group('code quality')]
lint:
    @uv run ruff check .

# Check types
[group('code quality')]
typecheck:
    @uv run mypy

# Run everything CI runs; do this before pushing
[group('code quality')]
check:
    @uv run ruff check .
    @uv run ruff format --check .
    @uv run mypy
    @uv run pytest --cov=watchtower

# ---------------------------------------------------------------- run

# Run the app, e.g. `just watchtower run examples/config.yaml`
[group('run')]
watchtower *args:
    @uv run watchtower {{ args }}

# Open the tray app, e.g. `just gui` or `just gui my-config.yaml`
[group('run')]
gui config="examples/config.yaml":
    @uv run watchtower gui {{ config }}

# Serve the fake listings website for demos, e.g. `just serve --port 8001`
[group('run')]
serve *args:
    @uv run watchtower-fake-listings {{ args }}
