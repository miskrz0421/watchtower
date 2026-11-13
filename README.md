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
| M1 | Foundations | ✅ done |
| M2 | Real data and memory | ⏳ planned |
| M3 | Config and filters | ⏳ planned |
| M4 | Robustness and real notifications | ⏳ planned |
| M5 | Desktop app | ⏳ planned |
| M6 | Analytics and final demo | ⏳ planned |

## Quick start

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/) and
[just](https://just.systems) (`uv tool install rust-just`).

Every developer command is a recipe in the [`justfile`](justfile); `just` alone lists them:

```bash
just install               # uv sync: the project + dev tools (dev includes PySide6 for pytest-qt)
just test                  # tests + coverage (fails below 95%)
just lint                  # report lint problems
just format                # fix formatting and auto-fixable lint problems
just typecheck             # mypy
just check                 # everything CI runs; do this before pushing
just serve                 # fake listings website for demos
just watchtower check      # the app; arguments are passed on
```

`uv sync --all-extras` also installs the reports extra (pandas, matplotlib).

The app's own commands are entry points declared under `[project.scripts]` in `pyproject.toml`
(added milestone by milestone):

```bash
uv run watchtower check                # run the built-in demo watcher (M1)
uv run watchtower check --db PATH      # demo listings watcher with saved state (M2)
uv run watchtower check FILE --db PATH # changes in a local file since the last run (M2)
uv run watchtower check config.yaml    # run every watcher once        (M3)
uv run watchtower run config.yaml      # headless scheduler            (M3)
uv run watchtower plugins              # list registered plugins       (M3)
uv run watchtower gui config.yaml      # tray app                      (M5)
uv run watchtower report --out out/    # export charts                 (M6)
uv run watchtower-fake-listings        # fake listings website for demos
```

## M2 demo: remembering state between runs

```bash
just serve                               # terminal 1: fake listings site
uv run watchtower check --db demo.db     # terminal 2: "Baseline saved", nothing reported
# add a listing to examples/fake_listings/listings.json, then:
uv run watchtower check --db demo.db     # the new listing is reported
uv run watchtower check --db demo.db     # "No changes": no false alert after a restart
```

See [examples/fake_listings/README.md](examples/fake_listings/README.md) for the server.

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
├── pyproject.toml        project metadata, dependencies, entry points, tool config
├── justfile              developer commands (`just test`, `just check`, ...)
├── uv.lock               exact dependency versions (commit this)
├── README.md
├── .github/              PR template and CI workflow
├── docs/                 architecture and design decisions
├── src/watchtower/       the package
├── tests/                pytest tests
└── .artifacts/           tool caches and coverage data (generated, not in git)
```

See [docs/architecture.md](docs/architecture.md) for the design and
[docs/decisions.md](docs/decisions.md) for the reasons behind it.
