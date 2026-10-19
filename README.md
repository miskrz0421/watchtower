# Watchtower

**A plugin-based monitoring framework in Python.** Watchtower watches anything, detects meaningful
changes, filters what matters, and reacts. It has a small core, and every source, filter and
notifier is a plugin, so you can connect a new service by writing one small class.

It runs as a **PySide6 desktop tray app** (native notifications, a window with watchers, change
history and reports) or **headless** from the command line.

> *"Tell me when a new flat under 3000 zł appears in Krowodrza."*
> *"Notify me about new AGH announcements mentioning scholarships."*

## Status

| Milestone | Theme | Status |
|---|---|---|
| M1 | Foundations | ⏳ planned |
| M2 | Real data and memory | ⏳ planned |
| M3 | Config and filters | ⏳ planned |
| M4 | Robustness and real notifications | ⏳ planned |
| M5 | Desktop app | ⏳ planned |
| M6 | Analytics and final demo | ⏳ planned |

## Quick start

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                    # core + dev tools
uv sync --all-extras       # + GUI (PySide6) and reports (pandas, matplotlib)

uv run pytest              # tests
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy                # type check
```

Planned commands (added milestone by milestone):

```bash
uv run watchtower check config.yaml    # run every watcher once        (M1–M2)
uv run watchtower run config.yaml      # headless scheduler            (M3)
uv run watchtower plugins              # list registered plugins       (M3)
uv run watchtower gui config.yaml      # tray app                      (M5)
uv run watchtower report --out out/    # export charts                 (M6)
```

## Example (target API)

```yaml
watchers:
  - name: Cheap flats in Krowodrza
    source: { type: webpage, url: "http://localhost:8000/listings", selector: ".offer" }
    interval: 15m
    diff: { type: items }
    filters:
      - new_items
      - { price_below: 3000 }
      - { not: { text_contains: agency } }
    notify:
      - { type: console }
      - { type: discord, webhook_url: "${DISCORD_WEBHOOK_URL}" }
```

## Project structure

```
.
├── pyproject.toml        project metadata, dependencies, tool config (ruff, mypy, pytest)
├── uv.lock               exact dependency versions (commit this)
├── README.md
├── src/watchtower/       the package
└── tests/                pytest tests, mirroring src/
```
