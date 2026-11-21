# Architecture

This is the **target** architecture: what the project looks like after M6. Parts planned for
later milestones are not in the code yet. It is updated whenever the design changes.

## The pipeline

```
Scheduler ──tick──► Watcher.check_once()
                       │
                       ├─ Source.snapshot()        what does the world look like now?
                       ├─ SnapshotStore.load()     what did it look like last time?
                       ├─ Differ.diff(old, new)    → list of Changes
                       ├─ Filter.matches(change)   keep only the changes that matter
                       ├─ Notifiers.send(event)    tell the user
                       └─ SnapshotStore.save()     remember the new state
                       │
                       └─ EventBus.publish(...)  ──► HistoryRecorder (SQLite)
                                                 ──► LoggingObserver
                                                 ──► EngineBridge → Qt signals → GUI
```

Every arrow is an interface, so every stage can be swapped on its own. **The core never imports
Qt**: the GUI is just another subscriber on the event bus.

## Package layout

```
src/watchtower/
├── __init__.py      public API: Watcher, models, events, plugin base classes, registry
├── _models.py       Item, Snapshot, Change, ChangeKind, ChangeEvent (private)
├── _errors.py       WatchtowerError → SourceError, ParseError, NotifyError, StorageError, ConfigError, MissingDependencyError
├── _registry.py     @register_* decorators, create(kind, name, **params) (private)
├── _events.py       event dataclasses + EventBus (private)
├── cli.py           argparse CLI entry point: check / run / plugins / gui / report
├── sources/         _base (Template Method), _fake, _file, _rss, _webpage, _json_api, _http, _parsing
├── storage/         _snapshots (Memento), _history, _recorder
├── diffs/           _base (Strategy), _text, _items
├── filters/         _base (Specification + Composite: And/Or/Not), _builtin
├── notifiers/       _base (Adapter), _console, _discord, _desktop, _decorators
├── config/          _loader (YAML loader), _intervals (interval parsing), _filters (filter builder)
├── core/            _watcher, _builder (Builder), _scheduler (Mediator), _clock, _logging_observer,
│                    _states (State), _commands, _retry
├── reports/         _tables (pandas), _charts (matplotlib)
└── gui/             _app (run_gui), _engine (EngineThread), _bridge (EngineBridge), _tray,
    │                _main_window
    └── tabs/        _watchers, _changes, _reports, _log

What is public and what is private is decided in [ADR-015](decisions.md).

tests/               mirrors the package layout (core/, sources/, diffs/, ...)
examples/            fake_listings server, example config.yaml
docs/                this documentation
```

## Core concepts (contracts)

These are the contracts between the packages. A change to one needs an entry in
[decisions.md](decisions.md).

| Concept | What it is | Key rules |
|---|---|---|
| **Item** | One thing being watched (a listing, a feed entry) | Frozen dataclass. Fields: `key`, `title`, `url`, `price`, `text`, `published`. Hashable and compared by value, so diffs can use sets. |
| **Snapshot** | The state of a source at one moment | Frozen. Holds `items` (a tuple), `raw_text`, and `taken_at`. Serialisable to JSON for storage. |
| **Change** | One difference between two snapshots | `kind` ∈ {new, removed, changed, text}, plus `item` / `before` / `diff_text`. |
| **ChangeEvent** | What a notifier receives | Watcher name, time, a tuple of the Changes that passed the filters, and a `summary` string. |
| **Source** | Where data comes from | `snapshot()` is a fixed template calling the abstract `fetch()` and `parse()`; `parse()` returns an iterable of Items. Raises `SourceError` / `ParseError`. |
| **Differ** | How to compare (Strategy) | `diff(old: Snapshot or None, new) → list[Change]`. `old is None` (first run) → no changes. |
| **Filter** | What matters (Specification) | `matches(change) → bool`; combine with `&`, `|`, `~`. Filters work on single Changes, not on whole events. |
| **Notifier** | Where to send it (Adapter) | `send(event)`; raises `NotifyError`. Decorators wrap a notifier and are notifiers themselves. |
| **EventBus** | Observer hub | `subscribe(event_type, handler)`, `publish(event)`. Synchronous. A failing handler is logged and does not stop the other handlers. |
| **Watcher** | One configured pipeline + its state | Built with `WatcherBuilder`, directly or by the YAML loader. Has an `interval` but does not schedule itself. Calls **its own** notifiers directly; the bus is for global observers. |
| **Scheduler** | Decides who runs when (Mediator) | Keeps the next due time per watcher, runs due watchers one at a time, drains the command queue each tick. Time comes from an injected `Clock`. |

## Events on the bus

| Event | Published when | Main subscribers |
|---|---|---|
| `CheckCompleted` | After every check (success or failure), with duration | HistoryRecorder, LoggingObserver, GUI |
| `ChangeDetected` | A ChangeEvent passed the filters | HistoryRecorder, LoggingObserver, GUI Changes tab |
| `FetchFailed` | A source raised after retries | GUI Log tab |
| `WatcherStateChanged` | State machine transition (published by the Scheduler) | LoggingObserver, GUI Watchers tab, tray icon |

## Watcher state machine

```
           check ok                      check fails
 ┌──────── Active ◄──────────┐   Active ───────────► Backoff (delay × 2 each failure, capped)
 │                           │                          │
 │ Pause            Resume   │          recovers        │  5th failure in a row
 ▼                           │   Active ◄───────────────┤
Paused ──────────────────────┘                          ▼
                                                    Disabled (user alerted)
```

Each state is an object (State pattern, ADR-023): `delay(interval)` says when the watcher is
checked next (None: not at all), and `after_success()` / `after_failure()` give the state that
follows a check. The Scheduler keeps one per watcher and publishes `WatcherStateChanged` when the
kind changes. `Paused` and `Disabled` only leave via an explicit `Resume`.

## Storage (SQLite, one file)

| Table | Contents | Written by | Read by |
|---|---|---|---|
| `snapshots` | Last snapshot per watcher (JSON) | SnapshotStore | Watcher on the next check / restart |
| `changes` | One row per reported Change | HistoryRecorder | Changes tab, reports |
| `checks` | One row per check: time, ok/error, duration | HistoryRecorder | Reports (uptime, failure rate) |

Each thread opens its own connection (`sqlite3` connections must not be shared across threads).

## Threading (GUI mode)

- The **engine** (scheduler + watchers) runs in a worker `QThread`.
- **Engine → UI:** `EngineBridge` lives in the GUI thread and re-emits bus events as Qt signals,
  which Qt delivers to the GUI thread as queued calls. Widgets are only ever touched from the
  GUI thread, so only methods of widgets and models are connected to the signals (ADR-024).
- **UI → Engine:** buttons call `Scheduler.submit` with a command (`Pause`, `Resume`,
  `CheckNow`, `ReloadConfig`); it goes on a thread-safe `queue.SimpleQueue` and the scheduler
  applies it at the start of its next `run_pending` (Command pattern, ADR-023).
- **Desktop notifications:** the `desktop` notifier uses the `desktop-notifier` package, not Qt,
  so it works the same with and without the GUI (ADR-024).
- Headless mode (`watchtower run`) uses the same engine in the main thread and never imports Qt.

## Design patterns map

| Pattern | Where |
|---|---|
| Template Method | `sources/_base.py`: `snapshot()` → `fetch()` + `parse()` |
| Memento | `storage/`: `SnapshotStore` |
| Proxy | `sources/_http.py`: polite + caching HTTP |
| Factory / Registry | `_registry.py`, used by the YAML loader |
| Strategy | `diffs/`: TextDiff, ItemDiff |
| Specification + Composite | `filters/`: `&`, `\|`, `~` → And/Or/Not |
| Builder | `core/_builder.py`: `WatcherBuilder`, used by the YAML loader |
| Adapter | `notifiers/`: one interface over Discord / tray / console |
| Decorator | `notifiers/_decorators.py`: RateLimited, QuietHours |
| Observer | `_events.py`: EventBus; `gui/_bridge.py` |
| State | `core/_states.py` |
| Mediator | `core/_scheduler.py` |
| Command | `core/_commands.py` |
| Chain of Responsibility (simplified) | retry → Backoff → Disabled + alert |
| Model–View | `gui/tabs/*`: `QAbstractTableModel` subclasses |
