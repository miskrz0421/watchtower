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
  plugin discovery through package entry points, the GUI watcher editor and PyInstaller to
  stretch goals.
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
- Note (M4): pandas, matplotlib and pandas-stubs joined the `dev` group for the same reason:
  mypy and the tests of `reports/` need them. `watchtower.gui` and `watchtower.reports` are
  imported only inside the `gui` and `report` CLI commands, so the other commands still run
  without the extras.
- Note (M5, notifiers PR): `desktop-notifier` is another extra, in the new `desktop` group (and
  in `dev`). It sets a new pattern: a plugin imports its optional package inside `__init__`, a
  missing one raises the new public `MissingDependencyError`, and the config loader turns that
  into a `ConfigError` naming the watcher.

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
- Broken input: a response that is not an RSS or Atom feed, and a matched page element without
  a title, raise `ParseError`, so the check fails instead of reporting every Item as removed or
  collapsing untitled elements into one Item with an empty key. A selector that matches nothing
  is not an error, because an empty listing is a valid page; after a site redesign this shows
  up as every Item removed once, and the selector has to be updated.

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

## ADR-014: Reading a price out of free text
- Status: accepted · M2
- Context: RSS entries carry the price inside the description, together with other numbers
  ("2 rooms, 45 m², 2 800 zł"). Prices are written with spaces, dots or commas as thousands
  separators and a comma or dot for decimals.
- Decision: `parse_price` joins digits only across a space followed by exactly three digits
  (`2 800` is one number, `Flat 2, 2 800` is two). The first number written next to a currency
  (zł, PLN, €, EUR, $, USD, £, GBP) is the price; without a currency, the first number is.
  A single dot or comma before three digits groups thousands, before one or two digits it
  starts the decimals.
- Alternatives: removing all whitespace first (merges separate numbers: `Flat 2, 2 800 zł`
  became 2.28); always taking the last number (breaks on "2 800 zł/mies., 2 rooms"); a full
  price library (one more dependency for one function, ADR-009).
- Consequences: text without a currency and with several numbers can still give the wrong
  one, so a source that knows where the price is (`WebPageSource` with a `price_selector`)
  passes only that text.

## ADR-015: What is public and how private names are marked
- Status: accepted · after M2 (amended · M3)
- Context: the top-level package re-exported 44 names, including test helpers (`FakeSource`),
  serialisation details (`ItemDict`) and every built-in plugin, and module-level names such as
  `logger` looked public. A reader could not tell what a user of the framework may rely on.
- Decision: there are three levels.
  1. `watchtower` exports only what is needed to build a watcher in code or to write a plugin:
     `Watcher`, `SnapshotStore`, the models, the events and `EventBus`, the plugin base classes,
     the errors and the registry functions.
  2. Each subpackage lists its public classes in the `__all__` of its `__init__.py`. Built-in
     plugins are imported from there (`from watchtower.sources import WebPageSource`) or
     created by name through the registry.
  3. Anything used only inside its own file or class starts with an underscore: `_logger`,
     helper functions, constants, instance attributes.
- Module files keep plain names (`storage/snapshots.py`, not `storage/_snapshots.py`). With
  level 2 every module would get the underscore, so it would mark nothing; inside the package
  we import from the module that defines a name, which keeps imports free of cycles.
- Alternatives: underscore-prefixed module files (the same information as `__all__`, at the
  cost of renaming every file and import); exporting everything from the top level (hides what
  is stable); no top-level exports (every user needs to know the internal layout).
- Consequences: importing `watchtower` still imports the plugin packages, so built-in plugins
  are registered. A new public name has to be added to an `__all__` on purpose.
- Amended (M3): after the M3 review, every module file except `cli.py` gets a leading
  underscore (`_models.py`, `storage/_snapshots.py`), so a package can only be used through
  the `__all__` of its `__init__.py`; `watchtower.storage.snapshots` no longer exists. `cli.py`
  keeps its name because `[project.scripts]` points at it. Inside the package, modules still
  import from the `_` module that defines a name, which keeps imports free of cycles. Tests
  import only from the package roots, and `tests/test_public_api.py` checks every `__all__`.

## ADR-016: One way to run things, one place for generated files, a coverage floor
- Status: accepted · after M2
- Context: a new developer had to find the right pytest, ruff and mypy commands in the README,
  the demo website was started by file path, tools left four cache folders in the project
  root, and nothing said how much of the code the tests have to reach.
- Decision:
  - Developer commands are recipes in the `justfile`, run with [just](https://just.systems):
    `just test`, `just format`, `just check`. `just` alone lists them with a description
    each, so the file is the documentation, and a recipe can grow without anyone relearning
    it. CI runs `just check`, the same recipe we run before pushing.
  - What the application itself offers is a command under `[project.scripts]` in
    `pyproject.toml`: `watchtower` and `watchtower-fake-listings`. For the second one the
    `examples/fake_listings` folder is installed as a package next to `watchtower`, which
    also lets the tests import it without a `pythonpath` setting.
  - pytest, ruff, mypy and coverage write to `.artifacts/`, set once per tool in
    `pyproject.toml`; the project root holds only files that belong to the project.
  - The tests measure coverage and fail below 95%. The number is just under what we had when
    the rule was added (97%); it is raised as coverage grows and never lowered.
    Lines that only `raise NotImplementedError` (stubs for a later milestone) are not counted.
  - Note (M3): coverage is measured by `just check` and `just coverage` (`--cov=watchtower`),
    not by every pytest run. A bare `--cov` in pytest's `addopts` took the first argument as its
    value, so `just test tests/test_cli.py` ran every test; and the floor would fail any run of
    a single file anyway.
  - Note (M5): CI runs `just check` on Ubuntu and Windows (`fail-fast: false`, so one failing
    system does not hide the other's result). The app is meant for both, and the GUI tests run on
    both with Qt's offscreen platform.
  - Note (M6): config files are grouped by topic, with a heading per group: `pyproject.toml`
    (project, optional dependencies, build, then one section per kind of tool), the `justfile`
    (`[group]`, which `just` shows), `.gitignore`, the CI steps and `examples/config.yaml`. The
    `dev` dependencies are split into `test`, `lint`, `types` and `extras`; `extras` refers to the
    project's own extras, so each version is written once.
- Alternatives: a Makefile (needs tabs, awkward on Windows, built for files rather than
  commands); only `uv run ...` lines in the README (nothing keeps them up to date); a Python
  task runner such as poethepoet (one more dependency inside the project, less known); a 100%
  threshold (forces tests for lines like `if TYPE_CHECKING`, or exclusion comments in the
  code); a threshold only as a team rule (nobody checks it).
- Consequences: just is one more tool to install (`uv tool install rust-just`); every recipe
  is a plain `uv run` line, so the project still works without it. `uv sync` is needed after
  pulling a change to the entry points. The wheel contains the demo website; acceptable for a
  project that is not published.

## ADR-017: Config file format
- Status: accepted · M3
- Context: users describe watchers in a YAML file; the loader has to turn each entry into
  plugin objects without knowing any plugin by name.
- Decision: the file has an optional `database` path and a `watchers` list. Each watcher has
  `name`, `source`, `diff`, and optionally `interval` (text such as `15m`), `filters` and
  `notify`. `source`, `diff` and each `notify` entry are mappings with a `type` (the registry
  name); every other key is passed to the plugin's constructor as a keyword argument.
- Filters are a special case: most take a single value, so an entry is either a plain name
  (`new_items`) or a mapping with one key — the registry name — whose value is passed positionally
  (`price_below: 3000`). The composite filters `all` and `any` take any number of filter entries
  as their value; `not` takes one. Rules can nest, or combine many filters at once (see ADR-019).
  The filters listed under `filters` must all pass.
- Alternatives: a small expression language (`price < 3000 and not agency`: needs a parser of our own).
- Consequences: `create_filter` accepts positional arguments. A filter with several parameters
  takes a mapping as its one argument or is written in Python.

## ADR-018: One builder for Python and YAML; observers attach themselves
- Status: accepted · M3
- Context: the milestone asks for the same watcher from the fluent Python API and from YAML,
  and three parts written by three people have to meet: the loader, the scheduler and the
  history.
- Decision:
  - `WatcherBuilder` is a separate class; `Watcher` keeps its plain constructor.
    `load_config` returns a `Config` holding one builder per watcher and the database path.
    The caller (the CLI) adds what is shared, the `SnapshotStore` and the `EventBus`, and
    calls `build()`.
  - A `Watcher` carries its `interval`; the `Scheduler` only reads it and keeps the due times.
  - `HistoryRecorder` and `LoggingObserver` have the same `attach(event_bus)` method and
    subscribe themselves; nothing else knows which events they listen to.
- Alternatives: chained methods on `Watcher` itself, as first sketched (a watcher would exist
  half-configured, and its constructor could not check anything); the loader returning built
  watchers (it would have to open the database, and tests of the loader would need one);
  intervals kept in the scheduler (the config would have to return pairs).
- Consequences: the loader never touches the database or the network, so it is tested with
  plain files. The "same watcher" test compares what the two builders build.
  `WatcherBuilder.every` takes a `timedelta`, not text: reading `15m` is the config's job, so
  the loader calls `parse_interval` and the builder does not depend on the config package.
  `build()` raises `ConfigError` naming the watcher when the source or the differ is missing,
  and `every` rejects an interval that is not positive.

## ADR-019: Composite filters accept any number of inner filters
- Status: accepted · M3
- Context: `And` and `Or` are composite filters that combine other filters. The `&` and `|`
  operators on `Filter` only ever combine two filters, so a chain such as `a & b & c` builds a
  nested tree (`And(And(a, b), c)`). The YAML config, however, lists filter entries under `filters`
  and each composite entry can name any number of inner filters. The constructor signature needed
  to match what the config can express.
- Decision: `And.__init__` and `Or.__init__` accept `*filters: Filter`, i.e. exactly one or more
  inner filters (zero is rejected with `ValueError`). They are evaluated lazily: `And` returns
  `False` on the first non-matching filter, `Or` returns `True` on the first matching filter.
- Alternatives: requiring exactly two arguments (matches `&` and `|`, but the YAML config could not
  express more than two without nesting); requiring zero or more with vacuous truth (an `And` of
  nothing would accept everything, which is surprising and hard to debug).
- Consequences: the YAML config may list any number of filters under an `all` or `any` entry. A
  user can also test filters in a composite condition one by one while debugging, without having to
  remove the whole block, because a single-element composite filter accepts exactly what its inner filter
  accepts. The `&` and `|` operators keep their two-argument behaviour in Python; nesting handles
  longer chains there.
  In the config, each entry listed under `all` or `any` becomes its own argument:
  `all: [a, b]` is built as `create_filter("all", a, b)`, not `create_filter("all", [a, b])`.

## ADR-020: When the scheduler runs a check, and what it does with failures
- Status: accepted · M3
- Context: the scheduler runs watchers with different intervals in one loop (ADR-007), and one
  broken website must not stop the others. Failures also reach the event bus, so the scheduler
  and the observers could both report the same error.
- Decision:
  - A newly added watcher is due at once. After each check, successful or not, the next one is
    due one `interval` after the check ends, read from the injected clock (ADR-008).
  - The loop sleeps until the earliest due time, then runs every due watcher one after another.
    `stop()` sets a flag; `run_forever` returns once the current round of checks is done.
  - A `WatchtowerError` is the normal way a check fails, and the watcher already publishes it as
    `FetchFailed` and `CheckCompleted`, so the scheduler logs it only at DEBUG. Any other exception
    is a bug in a plugin: the scheduler logs it with its traceback. Both keep the loop running.
  - `LoggingObserver` logs `CheckCompleted` (INFO, or WARNING with the error when it failed) and
    `ChangeDetected` (INFO). It does not log `FetchFailed`, which carries the same error, so
    every failure is logged once.
- Alternatives: keeping a fixed rhythm from the first due time (after a long outage or a laptop
  sleep, every missed check would run at once); the scheduler logging every failure at WARNING
  (each failure would appear twice when a `LoggingObserver` is attached); a `threading.Event` to
  wake the loop on `stop()` (not needed until the GUI runs the engine in a thread in M5).
- Consequences: a slow check pushes its watcher's next check back by its duration. Without an
  observer, expected failures are visible only at DEBUG, so the CLI always attaches a
  `LoggingObserver` to `run`. `stop()` called from another thread takes effect after the current
  sleep; M5 can replace the sleep with an event wait if that is too slow.
- Note (M4): the sleep is now `Clock.wait(seconds, wake)`. `submit` and `stop` set the wake
  event, so the loop applies a command or returns at once instead of after the wait (ADR-023).
  The loop checks the due watchers first and then waits, so `stop` never starts another round.
  A `stop` sent before `run_forever` starts is kept, and the flag is cleared when the loop
  ends, so the GUI can quit at once and a stopped scheduler can run again.

## ADR-021: History storage schema and streaming generator queries
- Status: accepted · M3
- Context: every executed check and detected change must be preserved for history inspection,
  reporting, and the GUI. Reading back large tables could consume excessive memory.
- Decision:
  - `HistoryStore` creates `changes` and `checks` tables in the same SQLite database file as
    `SnapshotStore`.
  - Like `SnapshotStore`, it opens a short-lived connection per operation for thread safety
    (ADR-013).
  - `changes()` and `checks()` are generator methods that yield `ChangeRecord` and `CheckRecord`
    instances row by row ordered chronologically (`id ASC`), optionally filtered by `watcher_name`.
  - `HistoryRecorder` attaches to `EventBus` (Observer pattern, ADR-006, ADR-018), subscribing to
    `CheckCompleted` and `ChangeDetected` to persist records automatically.
- Alternatives: separate SQLite database files (complicates configuration and backup); returning
  eager lists (loads the entire historical log into memory at once); storing raw JSON like
  snapshots (prevents relational queries and filtering by watcher in SQL).
- Consequences: all persistent state resides in a single database file. Streaming queries scale to
  large histories without memory spikes. Iterating a generator holds the SQLite connection open,
  keeping a read lock until consumption finishes; in M5 (background engine thread) callers should
  consume rows promptly to avoid delaying writers.

## ADR-022: The CLI runs watchers from a config file
- Status: accepted · M3
- Context: until M2 the CLI had hard-coded demo watchers (`check`, `check --db`,
  `check FILE --db`). With the YAML loader, any watcher can be described in a file.
- Decision:
  - `watchtower check CONFIG` checks every watcher once and prints one line per watcher
    (baseline saved, no changes, or the summary of what the notifiers printed). A failing
    watcher is reported on stderr and the others still run; the exit code is 1 if any failed.
  - `watchtower run CONFIG` adds every watcher to a `Scheduler` and runs it until Ctrl+C, with a
    `LoggingObserver` attached. Logging shows Watchtower's INFO lines, and other libraries'
    (httpx logs every request) only from WARNING.
  - `watchtower plugins` prints `list_plugins()`.
  - When the config names a `database`, both commands share one `SnapshotStore` and record
    every check and change through a `HistoryRecorder` on the same file. Without one, snapshots
    stay in memory, so every `check` is a baseline.
  - The hard-coded demo watchers and their options are removed; `examples/config.yaml` replaces
    them.
- Alternatives: keeping `check FILE --db` as a shortcut (a `file` source in a config does the
  same, and two ways to do one thing need two sets of tests); stopping `check` at the first
  failing watcher (one broken website would hide the results of the others).
- Consequences: every demo needs a config file. `check` without a `database` is only useful to
  test that a config loads and its sources answer.

## ADR-023: Watcher states and commands
- Status: accepted · M4
- Context: a watcher whose website is down is retried every interval forever, and nobody is
  told. The M5 window must pause, resume and check a watcher while the engine runs in another
  thread, and the Watchers tab has to show each watcher's state.
- Decision:
  - Each state is an object (State pattern, `core/_states.py`): `Active`, `Paused`,
    `Backoff(failures)` and `Disabled`. The scheduler keeps one per watcher. After every check it
    replaces it with `after_success()` or `after_failure()`, and `delay(interval)` says when the
    next check is due (None: not checked at all). `kind` is the `WatcherState` that goes into
    `WatcherStateChanged`, which the scheduler publishes on every transition.
  - `Backoff` waits the interval doubled once per failure, at most one hour; the fifth failure in
    a row gives `Disabled`, a success gives `Active`. `Paused` and `Disabled` are not checked and
    only `Resume` brings them back.
  - Other threads talk to the scheduler only through commands: frozen dataclasses `Pause`,
    `Resume`, `CheckNow` (each with a `watcher_name`) and `ReloadConfig`. `Scheduler.submit` puts
    them on a `queue.SimpleQueue`; `run_pending` applies every queued command first, in the
    scheduler's own thread. `Pause` gives `Paused`; `Resume` gives `Active` and makes the watcher
    due at once; `CheckNow` makes it due at once in any state (a paused watcher is checked once and
    stays paused). A command for a name that is not scheduled is logged and ignored.
  - `Scheduler.statuses()` returns a frozen `WatcherStatus` per watcher. The GUI reads it once,
    before the engine thread starts, and then follows `WatcherStateChanged` and `CheckCompleted`.
- Alternatives: a `WatcherState` enum with `if`/`elif` in the scheduler (the rules of every state
  in one function, and a new state touches all of it); the GUI calling `scheduler.pause(name)`
  directly (two threads changing the same dictionaries, so locks everywhere); the state inside
  `Watcher` (the watcher would decide its own schedule, against ADR-018).
- Consequences: only the scheduler's thread changes the schedule and the states, so they need no
  lock. A command waits until the loop wakes up, so `run_forever` must stop sleeping when a command
  arrives; the states PR replaces the sleep with a wait that `submit` and `stop` interrupt (the
  M5 change ADR-020 mentions). Tests submit a command and call `run_pending` with a `FakeClock`.
- Note (M4, states PR): the backoff cap is one hour or the watcher's own interval, whichever is
  longer, so a daily watcher in backoff is not checked more often than when it works. A watcher
  in `Backoff` is logged at INFO after every failure with its failure count and next wait, and
  `LoggingObserver` logs `WatcherStateChanged` (WARNING for Backoff and Disabled, INFO
  otherwise), so `watchtower run` shows the whole Active → Backoff → Active cycle.

## ADR-024: GUI threading and the bridge contract
- Status: accepted · M5
- Context: a check can block on the network for seconds, Qt widgets may only be used from the GUI
  thread, and the core must not import Qt (ADR-003). Three people build the tabs in parallel, so
  what each tab receives has to be fixed first.
- Decision:
  - The scheduler runs in an `EngineThread` (`QThread`); the GUI thread only runs the Qt event loop.
  - Engine → GUI: `EngineBridge` is a `QObject` created in the GUI thread. It attaches to the bus
    like any other observer (ADR-018) and re-emits the events unchanged as the signals
    `check_completed`, `change_detected`, `fetch_failed` and `state_changed`. They are emitted in
    the engine thread; Qt queues each call to the thread of the receiving `QObject`, so only
    methods of widgets and models are connected to them, never lambdas or plain functions (those
    would run in the engine thread).
  - GUI → engine: only `Scheduler.submit` (ADR-023).
  - Desktop notifications: `DesktopNotifier` is an ordinary notifier plugin (`desktop`) built on
    the cross-platform `desktop-notifier` package, without Qt. It works the same in
    `watchtower run` and in the tray app, so the GUI does not wire it up.
  - `MainWindow(bridge, scheduler, history)` gives each tab only what it needs: Watchers gets the
    bridge and the scheduler, Changes the bridge and the history, Reports the history. `history`
    is None when the config has no database.
- Alternatives: a `QTimer` calling `run_pending` in the GUI thread (a slow website freezes the
  window); watchers emitting Qt signals themselves (the core would import Qt); one signal carrying
  any event (every tab would check types, and nothing would say which events the GUI uses);
  desktop messages through the tray icon's `showMessage`, as first written here (the GUI would
  have to connect every `desktop` notifier to a bridge signal, and outside the GUI the notifier
  could only fail).
- Consequences: tabs are built and tested without the engine: a test emits the bridge's signals
  or calls a model's methods directly. Reading the history from the GUI thread is safe because
  `HistoryStore` opens a connection per call (ADR-021). `desktop-notifier` is one more dependency;
  it goes into an optional extra and the `dev` group, not into the core (ADR-003).
- Note (M5, engine PR): `run_gui(scheduler, event_bus, history)` gets everything built by the CLI,
  so building watchers from a config stays in one place (`cli.py`) for `run` and `gui`. It builds
  the bridge and the window before `EngineThread` starts, so the tabs read `Scheduler.statuses()`
  while nothing else runs, and stops the engine after the Qt event loop returns.
- Note (M5, tray PR): `TrayIcon` reads `Scheduler.statuses()` once and then follows
  `state_changed`. Its colour is the worst state (red Disabled, orange Backoff, grey when all are
  paused, green otherwise) and the tooltip counts the states. Pause all / Resume all submit one
  command per watcher. When the desktop has a tray, closing the window only hides it and the tray's
  Quit ends the app; without one, closing the window quits as before.
- Note (M5, notifiers): desktop delivery is best-effort. `desktop-notifier` does not raise
  when scheduling fails: it logs a warning with a traceback ("Notification failed") and `send()`
  still returns an identifier. KDE, for instance, reports DBus "Created too many similar
  notifications in quick succession" this way. `DesktopNotifier` does not turn those warnings into
  `NotifyError`; its `NotifyError` branch only covers exceptions that actually propagate out of the
  backend. Checking the returned identifier would not help, because the library returns one either
  way. How long a notification stays on screen is up to the OS notification server: after a
  one-shot `watchtower check` it may disappear at once, so use `watchtower run` or the tray app.
  Messages are cut to 2000 characters (Windows rejects toasts over about 30 KB).

## ADR-025: Diff text storage in history
- Status: accepted · M5
- Context: `TextDiffer` generates `Change(kind=ChangeKind.TEXT, diff_text=...)` containing unified diffs.
  Previously, `HistoryStore` and `ChangeRecord` only tracked structured item fields (`key`, `title`,
  `price`, `old_price`), discarding `diff_text`. The M5 Changes tab needs historical diffs to show
  the text details of changes.
- Decision:
  - Add a `diff_text TEXT` column to the `changes` table in SQLite.
  - Add `diff_text: str | None = None` to `ChangeRecord`.
  - Because Watchtower is pre-1.0 and has not been officially released yet, no backward compatibility
    layer or schema migration logic is maintained for existing test databases; existing databases can
    simply be recreated.
- Alternatives: storing diff text in separate files beside the database (scatters data across the filesystem);
  full database migrations using Alembic or schema version tables (unnecessary complexity before 1.0 release).
- Consequences: text watcher changes preserve unified diffs in the history; `ChangeRecord` carries
  `diff_text` for the GUI Changes tab and reporting. Any existing development database (such as
  `examples/watchtower.db`) should be deleted after upgrading if `no column named diff_text` appears.
