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
| M2 | Real data and memory | ✅ done |
| M3 | Config and filters | ✅ done |
| M4 | Robustness and real notifications | 🚧 in progress |
| M5 | Desktop app | 🚧 in progress |
| M6 | Analytics and final demo | ⏳ planned |

## Quick start

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/) and
[just](https://just.systems) (`uv tool install rust-just`).

Every developer command is a recipe in the [`justfile`](justfile); `just` alone lists them by group:

```bash
# setup
just install               # uv sync: the project + dev tools (incl. PySide6, pandas, matplotlib)
just clean                 # remove tool caches, coverage data and bytecode
# test
just test                  # the tests; `just test tests/test_cli.py` runs one file
just coverage              # the tests with an HTML coverage report
# code quality
just format                # fix formatting and auto-fixable lint problems
just lint                  # report lint problems
just typecheck             # mypy
just check                 # everything CI runs, tests with coverage (fails below 95%)
# run
just watchtower plugins    # the app; arguments are passed on
just gui                   # the tray app on examples/config.yaml
just serve                 # fake listings website for demos
```

The dev tools already include the `gui`, `reports` and `desktop` extras;
`uv sync --no-dev --all-extras` installs only the app with all of them, and `--extra NAME`
picks single ones, e.g. `uv sync --no-dev --extra desktop`.

The app's own commands are entry points declared under `[project.scripts]` in `pyproject.toml`
(added milestone by milestone):

```bash
uv run watchtower check config.yaml    # check every watcher once      (M3)
uv run watchtower run config.yaml      # headless scheduler            (M3)
uv run watchtower plugins [config.yaml] # list registered plugins       (M3)
uv run watchtower gui config.yaml      # tray app                      (M5)
uv run watchtower report config.yaml   # charts as PNG files           (M6)
uv run watchtower-fake-listings        # fake listings website for demos
```

## Demo: watchers from a config file

[`examples/config.yaml`](examples/config.yaml) describes two watchers on the fake listings
website. The first reports only new flats under 3000 zł without "agency" in the text.

```bash
just serve                                  # terminal 1: fake listings site
just watchtower run examples/config.yaml    # terminal 2: checks every 30 s / 1 min, Ctrl+C stops
# add a cheap flat to examples/fake_listings/listings.json: it is reported;
# an expensive one, or one from an agency, is not
```

`just watchtower check examples/config.yaml` checks every watcher once instead. Snapshots and
the history of checks and changes are kept in the SQLite file named by `database`
(`examples/watchtower.db`, delete the file after upgrading if you see `no column named diff_text`),
so a restart does not report old changes again.

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

Set `DISCORD_WEBHOOK_URL` in the environment before loading this config: the loader replaces
`${NAME}` placeholders with environment values and raises `ConfigError` if one is missing, so
secrets stay out of the file. Every `${NAME}` in the file is replaced (there is no way to escape
one); inside `{ ... }` it must be quoted, as above, or YAML cannot parse it.

## Your own plugins

A plugin is a class registered with a `@register_*` decorator. List the file it is in under
`plugins` and the config can use it like a built-in one:

```python
# shout.py, next to the config file
from watchtower import ChangeEvent, Notifier, register_notifier


@register_notifier("shout")
class ShoutNotifier(Notifier):
    """Print the summary of every event in capitals."""

    def send(self, event: ChangeEvent) -> None:
        """Print the event's summary in capitals."""
        print(event.summary.upper())
```

```yaml
plugins:
  - shout.py              # a file, relative to the config file
  - my_package.plugins    # or the name of an installed module
watchers:
  - name: Notes
    source: { type: file, path: notes.txt }
    diff: { type: text }
    notify:
      - { type: shout }
```

`uv run watchtower plugins config.yaml` lists the built-in plugins and the config's own. A plugin
file runs as Python when the config is loaded, so only list files you trust. A file is loaded
once: after editing a loaded plugin, restart the app; a newly listed file is picked up by Reload
config.

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
