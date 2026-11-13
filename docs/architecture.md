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
├── models.py        Item, Snapshot, Change, ChangeKind, ChangeEvent
├── errors.py        WatchtowerError → SourceError, ParseError, NotifyError
├── registry.py      @register_* decorators, create(kind, name, **params)
├── events.py        event dataclasses + EventBus
├── cli.py           argparse: check / run / plugins / gui / report
├── sources/         base (Template Method), fake, file, rss, webpage, json_api, http, parsing
├── storage/         SnapshotStore (Memento), HistoryStore, HistoryRecorder
├── diffs/           base (Strategy), text, items
├── filters/         base (Specification + Composite: And/Or/Not), built-in filters
├── notifiers/       base (Adapter), console, discord, desktop, decorators
├── config/          fluent builder helpers, YAML loader, interval parsing
├── core/            watcher, states (State), scheduler (Mediator), commands, clock, retry
├── reports/         pandas analysis + matplotlib charts
└── gui/             app, worker thread, EngineBridge, tray, main window
    └── tabs/        changes, watchers, reports, log

What is public and what is private is decided in [ADR-015](decisions.md).

tests/               one test module per area (test_sources.py, test_diffs.py, ...)
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
| **Watcher** | One configured pipeline + its state | Built with the fluent builder or from YAML. Calls **its own** notifiers directly; the bus is for global observers. |
| **Scheduler** | Decides who runs when (Mediator) | Keeps the next due time per watcher, runs due watchers one at a time, drains the command queue each tick. Time comes from an injected `Clock`. |

## Events on the bus

| Event | Published when | Main subscribers |
|---|---|---|
| `CheckCompleted` | After every check (success or failure), with duration | HistoryRecorder, GUI |
| `ChangeDetected` | A ChangeEvent passed the filters | HistoryRecorder, GUI Changes tab |
| `FetchFailed` | A source raised after retries | LoggingObserver, GUI Log tab |
| `WatcherStateChanged` | State machine transition | GUI Watchers tab, tray icon |

## Watcher state machine

```
           tick() ok                     fetch fails
 ┌──────── Active ◄──────────┐   Active ───────────► Backoff (delay × 2 each failure, capped)
 │                           │                          │
 │ pause()          resume() │          recovers        │  N failures in a row
 ▼                           │   Active ◄───────────────┤
Paused ──────────────────────┘                          ▼
                                                    Disabled (user alerted)
```

Each state is an object that decides what `tick()` does (State pattern). `Disabled` only
leaves via an explicit `Resume`.

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
  GUI thread.
- **UI → Engine:** buttons put command objects (`Pause`, `Resume`, `CheckNow`, `ReloadConfig`)
  on a thread-safe `queue.Queue`; the scheduler applies them on its next tick (Command pattern).
- Headless mode (`watchtower run`) uses the same engine in the main thread and never imports Qt.

## Design patterns map

| Pattern | Where |
|---|---|
| Template Method | `sources/base.py`: `snapshot()` → `fetch()` + `parse()` |
| Memento | `storage/`: `SnapshotStore` |
| Proxy | `sources/http.py`: polite + caching HTTP |
| Factory / Registry | `registry.py`, used by the YAML loader |
| Strategy | `diffs/`: TextDiff, ItemDiff |
| Specification + Composite | `filters/`: `&`, `\|`, `~` → And/Or/Not |
| Builder | fluent `Watcher(...)` API + YAML loader |
| Adapter | `notifiers/`: one interface over Discord / tray / console |
| Decorator | `notifiers/decorators.py`: RateLimited, QuietHours |
| Observer | `events.py`: EventBus; `gui/bridge.py` |
| State | `core/states.py` |
| Mediator | `core/scheduler.py` |
| Command | `core/commands.py` |
| Chain of Responsibility (simplified) | retry → Backoff → Disabled + alert |
| Model–View | `gui/tabs/*`: `QAbstractTableModel` subclasses |
