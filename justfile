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

# Remove cache files and directories
clean:
    @uv run python -c "\
        import shutil, pathlib; \
        [shutil.rmtree(p, ignore_errors=True) for p in ('.artifacts', '.mypy_cache', '.pytest_cache', '.ruff_cache', 'build', 'dist', 'htmlcov') if pathlib.Path(p).exists()]; \
        [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('*.egg-info') if '.venv' not in p.parts]; \
        [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__') if '.venv' not in p.parts]; \
        [p.unlink(missing_ok=True) for p in pathlib.Path('.').rglob('*.py[cod]') if '.venv' not in p.parts]; \
        [p.unlink(missing_ok=True) for p in pathlib.Path('.').glob('.coverage*') if p.is_file()]"

# Run the app, e.g. `just watchtower run examples/config.yaml`
watchtower *args:
    @uv run watchtower {{ args }}

# Serve the fake listings website for demos, e.g. `just serve --port 8001`
serve *args:
    @uv run watchtower-fake-listings {{ args }}
