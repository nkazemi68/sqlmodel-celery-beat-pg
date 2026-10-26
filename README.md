# sqlmodel-celery-beat-pg

**Database-backed Celery Beat scheduler, models, CLI, and admin UI on SQLModel + PostgreSQL** — a `django-celery-beat` equivalent without Django.

Published on PyPI: <https://pypi.org/project/sqlmodel-celery-beat-pg/>

Import it as `sqlmodel_celery_beat`.

---

## Features

- **SQLModel** models with timezone-aware datetime columns (`TIMESTAMPTZ` on PostgreSQL).
- **PostgreSQL** first-class support using the `psycopg` v3 driver, with optional schema isolation.
- **All four schedule types** offered by `django-celery-beat`:
  - `IntervalSchedule`
  - `CrontabSchedule`
  - `SolarSchedule` (sunrise, sunset, dawn, dusk, etc.)
  - `ClockedSchedule` (one-shot datetime)
- **One-shot tasks** — set `one_off=True` on a `PeriodicTask` attached to a `ClockedSchedule`; the scheduler fires it once and then disables it.
- **Start-time and expiry windows** — `PeriodicTask.start_time` and `.expire_seconds` (or `.expires`) are enforced by the scheduler; expired rows are disabled automatically.
- **`DatabaseScheduler`** for `celery beat -S`, with automatic reloads when changes are detected through `PeriodicTaskChanged`. Change detection listens on every schedule model, not just `PeriodicTask`.
- **Durable run state** — `last_run_at` and `total_run_count` are persisted on every tick through `sync()` and survive beat restarts.
- **Bundled Alembic migrations** — no need to manage Alembic yourself.
- **CLI** (`sbeat` / `scb`) — inspect tasks, run migrations, clean up orphan schedules, and open a Python shell.
- **Optional admin UI** (FastAPI + SQLAdmin) available at `/admin`.
- **PostgreSQL schema isolation** — keep beat tables in `celery_beat.celery_*` while the rest of your application uses `public.*`.

---

## Installation

```bash
pip install sqlmodel-celery-beat-pg
```

Optional extras:

```bash
# Web admin UI (FastAPI + SQLAdmin)
pip install 'sqlmodel-celery-beat-pg[admin]'

# Solar schedules (requires ephem)
pip install 'sqlmodel-celery-beat-pg[solar]'
```

On Windows, `tzdata` is pulled in automatically so timezone resolution works without the OS tz database.

Alternatively, use `pipx` if you only need the CLI tools globally:

```bash
pipx install sqlmodel-celery-beat-pg
pipx inject sqlmodel-celery-beat-pg "sqlmodel-celery-beat-pg[admin]"
```

---

## Quick Start

### 1. Create the database schema

```bash
sbeat migrate --dburi postgresql+psycopg://user:pass@localhost:5432/celery_beat
```

This applies the bundled migrations and creates six tables:

```text
celery_interval_schedule
celery_crontab_schedule
celery_solar_schedule
celery_clocked_schedule
celery_periodic_task
celery_periodic_task_changed
```

All datetime columns are stored as `TIMESTAMP WITH TIME ZONE`.

### 2. Configure Celery

```python
# app.py
from celery import Celery

from sqlmodel_celery_beat import configure

app = Celery("app", broker="redis://localhost:6379/0")

configure(
    dburi="postgresql+psycopg://user:pass@localhost:5432/celery_beat"
).apply_to_celery(app)
```

`configure(...)` sets the following Celery configuration options:

- `app.conf.beat_scheduler = "sqlmodel_celery_beat.schedulers:DatabaseScheduler"`
- `app.conf.beat_dburi`
- `app.conf.beat_schema` (only when `schema=` is passed)
- `app.conf.beat_engine_options` (only when `engine_options=` is passed)
- `app.conf.beat_max_loop_interval = 5`
- `app.conf.timezone` (from `use_timezone=`, default `"UTC"`)

The scheduler reads these directly — **no manual `session_manager` injection is required**.

### 3. Create a periodic task

```python
from sqlmodel_celery_beat import (
    SessionManager,
    IntervalSchedule,
    PeriodicTask,
    Period,
)

mgr = SessionManager(
    "postgresql+psycopg://user:pass@localhost:5432/celery_beat"
)

with mgr.session_scope() as session:
    schedule = IntervalSchedule(
        every=10,
        period=Period.SECONDS,
    )

    session.add(schedule)
    session.commit()
    session.refresh(schedule)

    session.add(
        PeriodicTask(
            name="tick",
            task="app.tick",
            discriminator="interval",
            schedule_id=schedule.id,
        )
    )

    session.commit()
```

### 4. Start Celery Beat

```bash
celery -A app beat -S sqlmodel_celery_beat.schedulers:DatabaseScheduler -l info
```

The short alias registered through the `celery.beat_schedulers` entry point also works:

```bash
celery -A app beat -S sqlmodel -l info
```

**Run exactly one Beat process.** Running two Beat replicas can cause every scheduled task to execute twice.

### 5. Inspect and manage tasks

```bash
sbeat list-tasks --dburi postgresql+psycopg://user:pass@localhost:5432/celery_beat

sbeat cleanup-schedules --dburi postgresql+psycopg://user:pass@localhost:5432/celery_beat

sbeat admin --dburi postgresql+psycopg://user:pass@localhost:5432/celery_beat
```

The admin UI is available at <http://127.0.0.1:8000/admin>.

---

## CLI Reference

Two command names point to the same application. Use whichever name your shell does not shadow.

| Command | Description |
|---|---|
| `sbeat init [--dburi URI] [--schema NAME]` | Create all six tables directly. Useful for quick starts; use migrations in production. |
| `sbeat migrate [--rev REV] [--dburi URI] [--schema NAME]` | Apply migrations, targeting the latest revision by default. |
| `sbeat list-tasks [--dburi URI] [--schema NAME]` | Print all periodic tasks as a table. |
| `sbeat cleanup-schedules [--dburi URI] [--schema NAME]` | Remove schedule rows no longer referenced by any `PeriodicTask` and report the count. |
| `sbeat shell [--dburi URI] [--schema NAME]` | Open an interactive Python shell with models preloaded. |
| `sbeat admin [--dburi URI] [--schema NAME] [--host HOST] [--port PORT]` | Start the FastAPI + SQLAdmin web UI. |
| `sbeat-migrate <upgrade\|downgrade\|revision\|stamp> [args...] [--dburi URI] [--schema NAME]` | Run the underlying Alembic commands. |

Every command that accesses the database accepts `--dburi` to override the configured database URI and `--schema` to direct operations to a specific PostgreSQL schema. If no `--dburi` is provided and `configure(...)` has not been called, the CLI prints a short actionable error and exits with code `1` instead of a traceback.

### Windows / PowerShell

`scb` is a built-in alias for `Set-Clipboard` in PowerShell. Calling `scb ...` may copy the arguments to the clipboard instead of running this package's CLI.

Use one of these alternatives:

```powershell
sbeat --help

# Force PowerShell to run the executable
scb.exe --help

# Remove the alias for the current session
Remove-Item Alias:scb
```

---

## Schedule Types

### Interval

Run a task at a fixed interval.

```python
IntervalSchedule(
    every=10,
    period=Period.SECONDS,
)
```

`Period` values are stored in the database as lowercase strings (`seconds`, `minutes`, …).

### Crontab

Run a task according to a cron-like schedule.

```python
CrontabSchedule(
    minute="*/5",
    hour="*",
    day_of_week="*",
    timezone="Europe/Paris",
)
```

Crontab expressions are validated when the schedule is written (constructor and ORM flush). An out-of-range minute or hour raises `ValueError` immediately, so an invalid row never reaches the scheduler.

### Solar

Run a task at a solar event. Solar schedules require the `[solar]` extra (`ephem`).

```python
SolarSchedule(
    event="sunset",
    latitude=51.5074,
    longitude=-0.1278,
)
```

Supported events:

- `dawn_astronomical`
- `dawn_nautical`
- `dawn_civil`
- `sunrise`
- `solar_noon`
- `sunset`
- `dusk_civil`
- `dusk_nautical`
- `dusk_astronomical`

The event name, latitude, and longitude are validated on construction. If `ephem` is not installed, `schedule()` raises an `ImportError` explaining how to install the extra.

### Clocked

Run a task at a specific date and time.

```python
from datetime import datetime, timezone

ClockedSchedule(
    clocked_time=datetime(
        2026, 1, 1, 0, 0,
        tzinfo=timezone.utc,
    )
)
```

Naive `clocked_time` values are normalised to UTC.

Any schedule type can be attached to a `PeriodicTask` through `discriminator` and `schedule_id`. The discriminator must be one of `"interval"`, `"crontab"`, `"solar"`, or `"clocked"`; any other value raises `ValueError`.

For example:

```python
PeriodicTask(
    name="my-periodic-task",
    task="app.my_task",
    discriminator="crontab",
    schedule_id=crontab_schedule.id,
)
```

---

## One-Shot Tasks (`one_off`)

Set `one_off=True` on a `PeriodicTask` attached to a `ClockedSchedule`. The scheduler fires the task once and then sets `enabled=False`.

The database row remains available for auditing but is no longer scheduled.

```python
from datetime import datetime, timezone

clocked_schedule = ClockedSchedule(
    clocked_time=datetime(
        2026, 1, 1, 0, 0,
        tzinfo=timezone.utc,
    )
)

session.add(clocked_schedule)
session.commit()
session.refresh(clocked_schedule)

session.add(
    PeriodicTask(
        name="send-once",
        task="app.send_email",
        discriminator="clocked",
        schedule_id=clocked_schedule.id,
        one_off=True,
    )
)

session.commit()
```

`one_off=True` is only allowed when `discriminator="clocked"`; using it with an interval, crontab, or solar task raises `ValueError`.

Without `one_off=True`, a `ClockedSchedule` whose scheduled time has already passed will continue firing on every Beat tick until the task is manually disabled. This is Celery's native clocked-schedule behavior.

**Use `one_off=True` for one-time tasks** when you want behavior similar to `django-celery-beat`.

A one-off task is only disabled **after** Celery confirms the publish succeeded. If the broker is down and `apply_async()` raises, the task stays enabled and is retried on a later tick.

---

## Start Time and Expiry

`PeriodicTask` supports optional scheduling windows:

```python
PeriodicTask(
    name="with-window",
    task="app.maintenance",
    discriminator="interval",
    schedule_id=schedule.id,
    start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    expire_seconds=3600,
)
```

- `start_time` — the entry is not dispatched before this time.
- `expire_seconds` — measured from the last successful run; once the window is exceeded, the scheduler disables the task.
- `expires` — an absolute deadline for the Celery message; mutually exclusive with `expire_seconds`.

Expired rows are disabled automatically (`enabled=False`) and logged.

---

## Task Arguments, Keyword Arguments, and Headers

`PeriodicTask.args`, `.kwargs`, and `.headers` are stored as JSON text in the database but delivered to Celery as real Python objects.

```python
PeriodicTask(
    name="with-args",
    task="app.process",
    discriminator="interval",
    schedule_id=schedule.id,
    args='["order-42"]',
    kwargs='{"dry_run": true}',
    headers='{"x-trace": "abc"}',
)
```

- `args` — decoded to a tuple.
- `kwargs` — decoded to a dict.
- `headers` — decoded to a dict and forwarded to `apply_async(headers=...)`.
- `periodic_task_name` is added to the headers automatically so worker-side handlers can identify the beat entry.

All three columns are `Text`, so payloads are no longer capped at 1024 characters. Invalid JSON logs a warning and falls back to the empty value.

---

## Migrations

Migrations are bundled with the package. You do not need to maintain a separate Alembic setup for these tables.

### Apply migrations

```bash
sbeat migrate --dburi "$DBURI"
```

### Apply migrations inside a specific schema

```bash
sbeat migrate --dburi "$DBURI" --schema celery_beat
```

### Generate a new revision

For development only:

```bash
sbeat-migrate revision -m "add foo" --dburi "$DBURI"
```

`sbeat-migrate revision` understands `-m` / `--message`, `--autogenerate`, and `--rev-id`. The message value is passed through to Alembic (previously `-m` was treated as the message).

### Roll back one revision

```bash
sbeat-migrate downgrade -1 --dburi "$DBURI"
```

The bundled chain is `0001_initial` → `0002_add_one_off` → `0003_parity_fields` → `0004_period_values` → `0005_marker_row`.

**Never edit an existing migration revision after it has been published.** Create a new revision instead.

---

## Using PostgreSQL Schemas

You can isolate the scheduler's tables in a dedicated PostgreSQL schema while keeping the rest of your application in `public`.

Configure Celery with the desired schema:

```python
from sqlmodel_celery_beat import configure

configure(
    dburi="postgresql+psycopg://user:pass@localhost/celery_beat",
    schema="celery_beat",
).apply_to_celery(app)
```

The `SessionManager` configures the PostgreSQL connection's search path as:

```text
celery_beat,public
```

It uses Psycopg connection options equivalent to `-c search_path=celery_beat,public`, so unqualified SQL statements resolve objects in `celery_beat` first and then fall back to `public`.

Run migrations using the same schema:

```bash
sbeat migrate --dburi "$DBURI" --schema celery_beat
```

Alembic's own `alembic_version` table is also created in the specified schema, so your project's `public.alembic_version` table is not modified.

**Important:** The schema must exist before migrations run.

```sql
CREATE SCHEMA IF NOT EXISTS celery_beat;

GRANT ALL ON SCHEMA celery_beat TO appuser;
```

If you prefer a completely separate database rather than a separate schema, point `dburi` to that database. No `schema` argument is necessary.

---

## Admin UI

Install the optional admin dependencies:

```bash
pip install 'sqlmodel-celery-beat-pg[admin]'
```

Start the admin UI:

```bash
sbeat admin --dburi "$DBURI" --host 0.0.0.0 --port 8000
```

Open <http://127.0.0.1:8000/admin> to manage all six models with list, search, edit, and delete functionality.

Editing a schedule model through the admin bumps `PeriodicTaskChanged`, so the running scheduler picks up the change on its next tick (within ~5 seconds). Invalid crontab or solar rows are rejected by the model validators and surfaced as admin form errors rather than being saved.

The admin UI is an optional extra rather than a core dependency. Install the core package on Celery workers and install the `[admin]` extra only on the machine running the admin UI.

---

## Detecting Changes and Bulk Updates

Single-object ORM operations automatically update `PeriodicTaskChanged` through SQLAlchemy `after_insert`, `after_update`, and `after_delete` events on **all six models** (the marker table is excluded to avoid recursion). The marker table is a single row with `id = 1`, updated through a PostgreSQL upsert.

Bulk `UPDATE` and `DELETE` statements bypass these ORM events. After a bulk update, notify the scheduler manually:

```python
from sqlmodel import update

from sqlmodel_celery_beat import PeriodicTask, PeriodicTaskChanged

with mgr.session_scope() as session:
    session.exec(
        update(PeriodicTask)
        .where(...)
        .values(enabled=False)
    )

    PeriodicTaskChanged.update_from_session(session)
```

`update_from_session()` does **not** commit; your `session_scope()` (or explicit `commit()`) controls the transaction.

The scheduler detects the change on its next `tick()`. In addition to marker-driven reloads, a full refresh runs at least every 300 seconds.

---

## Detecting and Cleaning Orphan Schedules

Deleting the last `PeriodicTask` that references a schedule removes that schedule automatically through an `after_delete` hook. Shared schedules (still referenced by another task) are kept.

For pre-existing orphans, use the CLI:

```bash
sbeat cleanup-schedules --dburi "$DBURI"
```

or the helper:

```python
from sqlmodel_celery_beat import cleanup_orphan_schedules

with mgr.session_scope() as session:
    removed = cleanup_orphan_schedules(session)
```

---

## Version Compatibility

| Package version | SQLModel | SQLAlchemy | Celery | Python |
|---|---|---|---|---|
| `0.1.3` | `>=0.0.14` | `>=2.0` | `>=5.3` | `>=3.10` |
| `0.1.2` | `>=0.0.14` | `>=2.0` | `>=5.3` | `>=3.10` |
| `0.1.1` | `>=0.0.48` (too restrictive) | `>=2.1` (conflicts with SQLModel versions requiring SQLAlchemy `<2.1`) | `>=5.3` | `>=3.10` |

Upgrade to `0.1.3` for the stock-Celery boot path, durable run state, per-entry reload isolation, and the parity fields. See `CHANGELOG.md` for the full list.

---

## Development

Clone the repository and install the development dependencies.

```bash
git clone <repo>
cd sqlmodel-celery-beat-pg

python -m venv .venv
```

Activate the virtual environment.

**Windows / PowerShell:**

```powershell
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**

```bash
source .venv/bin/activate
```

Install the package in editable mode with all extras:

```bash
pip install -e '.[dev,solar]'
```

Run tests (the database suite uses `TEST_DATABASE_URL` and a disposable schema; without it, database tests are skipped with a clear message):

```bash
export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/celery_beat_test

python -m pytest
```

Lint:

```bash
ruff check src tests
```

Build the package:

```bash
python -m build
```

---

## Publishing a New Release

Update the package version in both `pyproject.toml` and `src/sqlmodel_celery_beat/__init__.py`. The two versions must match; CI and the release workflow enforce it.

Remove previous build artifacts and rebuild:

```bash
rm -rf dist build

python -m build

python -m twine check dist/*
```

Verify the wheel installs cleanly:

```bash
python -m venv /tmp/verify
/tmp/verify/bin/pip install dist/*.whl
/tmp/verify/bin/python -c "import sqlmodel_celery_beat; print(sqlmodel_celery_beat.__version__)"
/tmp/verify/bin/sbeat --help
```

Upload to TestPyPI first, verify installation in a clean virtual environment, and then upload to PyPI:

```bash
twine upload --repository testpypi dist/*

twine upload dist/*
```

The GitHub `release.yml` workflow runs the full test suite and the wheel install smoke test before publishing. A failed test blocks the upload.

Tag the release:

```bash
git tag vX.Y.Z
git push origin main --tags
```

**Important:** PyPI does not allow an uploaded distribution filename to be reused. Always bump the version, even for a one-character fix.

---

## License

BSD-3-Clause. See `LICENSE.md`.