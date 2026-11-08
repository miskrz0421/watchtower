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

## ADR-012: Item keys and what counts as a changed item
- Status: accepted · M2
- Context: `ItemDiff` compares snapshots by identity, so every Item needs a key that stays the
  same between checks. Without one, a changed price or a reordered page would make every Item
  look new or removed. We also had to say which field differences are worth reporting.
- Decision: each source assigns every Item a stable key.
  - RSS: the entry `id` (guid), or its `link` when there is no id. An entry with neither, or
    without a title, is a `ParseError`.
  - Web page: the value of `key_attribute` when it is set and not blank, otherwise the first
    link's `href`, otherwise the title. The key uses the href exactly as written (a relative
    path stays relative), while `Item.url` is made absolute for following the link.
  - `ItemDiff` groups both snapshots by key. A key only in the new snapshot is `NEW`, a key only
    in the old one is `REMOVED`, and a key in both whose Item differs in **any** field (title,
    url, price, text, published) is `CHANGED`. For `CHANGED`, `Change.item` is the new version
    and `Change.before` the previous one; for `REMOVED`, `Change.item` is the removed Item.
  - Duplicate keys within one snapshot collapse to the last occurrence, because a key identifies
    one Item. The first run (`old is None`) still reports nothing (ADR-004).
- Alternatives: comparing snapshots as plain sets (a changed Item becomes a remove plus a new
  one, losing `before`); using the element position as key (breaks when the page order changes);
  using the title as key (titles change and may repeat); using the absolute href as key (a domain
  change would make every Item look new); reporting only price changes (misses title or text
  updates).
- Consequences: changing how a source derives keys makes every Item look new once, so the rule
  belongs in the source's documentation. Two elements with the same key become one Item. Because
  `CHANGED` keeps both versions, notifiers and filters can compare before and after. New sources
  must state their own key rule.

## ADR-013: Where snapshots are loaded and saved
- Status: accepted · M2
- Context: a watcher has to remember the last snapshot between runs, or every restart is a new
  baseline and changes made while the program was off are never reported.
- Decision: `Watcher` takes an optional `SnapshotStore`. On every check it fetches first, then
  loads the previous snapshot from the store, diffs, notifies, and **saves the new snapshot
  last**. A failed fetch saves nothing. Without a store the watcher keeps the last snapshot in
  memory, as in M1. The store opens a new SQLite connection for every `load`/`save`.
- Why save last: if the program crashes or the save fails after notifying, the next check
  compares against the old snapshot and repeats the alert. Saving first would lose that alert
  for good. A duplicate notification is better than a missed flat.
- Why load on every check instead of once: the store stays the only source of truth, so another
  process (later the GUI, or deleting the file) cannot leave the watcher with a stale copy.
  Reading one row by primary key is cheap next to an HTTP request.
- Why a connection per call: `sqlite3` connections must not be shared between threads, and from
  M5 the engine runs in a worker thread. A short connection per call is correct from any thread
  and needs no closing logic in the watcher.
- Alternatives: load once in `__init__` (stale state, and constructing a watcher would touch the
  disk); save before notifying (can lose alerts); one long-lived connection (breaks across
  threads); a required store with an in-memory implementation (an extra class with no use yet).
- Consequences: `initial_snapshot` is removed, since the store replaces it. A failed save makes
  the check fail (`CheckCompleted(ok=False)`) even though the notifiers already ran.
