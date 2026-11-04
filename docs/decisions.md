# Design Decisions

A log of every non-obvious choice and the reasons behind it. Each entry is added in the same
PR that makes the decision.

**Template**

```
## ADR-NNN: Title
- Status: accepted | replaced by ADR-MMM
- Milestone:
- Context: what problem we had
- Decision: what we chose
- Alternatives: what else we considered and why not
- Consequences: what this makes easier or harder
```

---

## ADR-001: Reduce the scope of the original concept
- Status: accepted · M1
- Context: the original concept covered ~15 patterns, 4 roles, an LLM plugin, async and
  packaging. We are 3 people with 6 one-week milestones.
- Decision: keep the core pipeline, plugins, state machine, SQLite history, GUI (Watchers,
  Changes, Reports, Log tabs) and pandas reports. Move the LLM plugin, asyncio, processors,
  entry points, the GUI watcher editor and PyInstaller to stretch goals.
- Alternatives: everything (not doable); no GUI (loses the most visible part).
- Consequences: every milestone has a visible demo.

## ADR-002: uv + `src/` layout + hatchling
- Status: accepted · M1
- Decision: manage the project with `uv` (`pyproject.toml` + `uv.lock`), keep the code in
  `src/watchtower/`, and build with hatchling.
- Why: `uv sync` reproduces the exact same environment on every machine. The `src/`
  layout makes tests import the *installed* package, not whatever is in the current folder.
- Alternatives: pip + requirements.txt (no lock file by default), Poetry (slower, more config).

## ADR-003: Qt and pandas are optional extras
- Status: accepted · M1
- Decision: core dependencies are only httpx, beautifulsoup4, feedparser and pyyaml. `gui`
  (PySide6) and `reports` (pandas, matplotlib) are extras. PySide6 is also in the `dev` group,
  because pytest-qt cannot load without a Qt binding.
- Why: a headless install stays light (PySide6 is a few hundred MB), and `uv sync` followed by
  `uv run pytest` works with no extra steps.
- Consequences: Qt is always present in development, so a missing package will not catch an
  accidental Qt import in the core; code review has to.

## ADR-004: First run is a baseline
- Status: accepted · M1
- Decision: when there is no stored snapshot (`old is None`), the differ reports no changes;
  the snapshot is only saved.
- Why: otherwise every new watcher, or every restart without storage, would report all items
  as "new".

## ADR-005: Filters act on single Changes
- Status: accepted · M1
- Decision: `Filter.matches(change)`, not `matches(event)`. The watcher filters each Change
  and builds a ChangeEvent only from the ones that pass; an empty result means no
  notification.
- Why: rules like `PriceBelow(3000)` are about one item. Filtering whole events would let an
  expensive flat through just because a cheap one appeared at the same time.
- Consequences: the `Filter` base class exists from M1; the watcher starts applying filters
  in M3.

## ADR-006: Watchers call their own notifiers; the bus is for global observers
- Status: accepted · M1
- Decision: each watcher keeps its own list of notifiers and calls them directly. The EventBus
  carries events to observers that care about *all* watchers (history, logging, GUI).
- Why: notifier routing is per watcher config ("this watcher → Discord"). Doing that through
  the bus would mean every notifier has to filter events by watcher name.
- Alternatives: notifiers as bus subscribers.

## ADR-007: Synchronous engine, one check at a time
- Status: accepted · M3
- Decision: the scheduler runs due watchers one after another in one thread. asyncio is a
  stretch goal.
- Why: much simpler to reason about and test, and at intervals of minutes, sequential
  fetching is fast enough. Running one at a time is also the simplest way to "not hit the
  network all at once" (Mediator).

## ADR-008: Injected clock
- Status: accepted · M3
- Decision: all time-based logic (scheduler, backoff, quiet hours, rate limits) gets its time
  from a `Clock` object; tests use `FakeClock`.
- Why: tests never `sleep()`, and time-based behaviour can be tested exactly.

## ADR-009: Stdlib where it is good enough
- Status: accepted · M1
- Decision: `argparse` (CLI), `sqlite3` (storage), `logging`, `difflib`,
  `http.server` (demo server), `queue` (command queue).
- Why: fewer dependencies to learn and justify; each is enough for our needs.
- Alternatives: click/typer, SQLAlchemy, loguru: nicer, but more to explain and not needed.

## ADR-010: Secrets come from environment variables
- Status: accepted · M4
- Decision: the YAML refers to secrets as `${DISCORD_WEBHOOK_URL}`; the loader substitutes
  values from the environment. No secrets in the repo.

## ADR-011: Discord is the only external notification channel
- Status: accepted · M4
- Decision: a `DiscordNotifier` posts to a webhook. Console and desktop tray notifications are
  the other two notifiers.
