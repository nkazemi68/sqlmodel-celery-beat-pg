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
- **`DatabaseScheduler`** for `celery beat -S`, with automatic reloads when changes are detected through `PeriodicTaskChanged`.
- **Bundled Alembic migrations** — no need to manage Alembic yourself.
- **CLI** (`sbeat` / `scb`) — inspect tasks, run migrations, and open a Python shell.
- **Optional admin UI** (FastAPI + SQLAdmin) available at `/admin`.
- **PostgreSQL schema isolation** — keep beat tables in `celery_beat.celery_*` while the rest of your application uses `public.*`.

---

## Installation

```bash
pip install sqlmodel-celery-beat-pg

# Optional: install the web admin UI
pip install 'sqlmodel-celery-beat-pg[admin]'
```

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
- `app.conf.beat_scheduler_kwargs["session_manager"]`

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

**Run exactly one Beat process.** Running two Beat replicas can cause every scheduled task to execute twice.

### 5. Inspect and manage tasks

```bash
sbeat list-tasks --dburi postgresql+psycopg://user:pass@localhost:5432/celery_beat

sbeat admin --dburi postgresql+psycopg://user:pass@localhost:5432/celery_beat
```

The admin UI is available at <http://127.0.0.1:8000/admin>.

---

## CLI Reference

Two command names point to the same application. Use whichever name your shell does not shadow.

| Command | Description |
|---|---|
| `sbeat init [--schema NAME]` | Create all tables directly. Useful for quick starts; use migrations in production. |
| `sbeat migrate [--rev REV] [--schema NAME]` | Apply migrations, targeting the latest revision by default. |
| `sbeat list-tasks [--schema NAME]` | Print all periodic tasks as a table. |
| `sbeat shell [--schema NAME]` | Open an interactive Python shell with models preloaded. |
| `sbeat admin [--schema NAME] [--host HOST] [--port PORT]` | Start the FastAPI + SQLAdmin web UI. |
| `sbeat-migrate <upgrade\|downgrade\|revision\|stamp> [args...] [--dburi URI] [--schema NAME]` | Run the underlying Alembic commands. |

Every command that accesses the database accepts `--dburi` to override the configured database URI and `--schema` to direct operations to a specific PostgreSQL schema.

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

### Solar

Run a task at a solar event.

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

Any schedule type can be attached to a `PeriodicTask` through `discriminator` and `schedule_id`.

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

Without `one_off=True`, a `ClockedSchedule` whose scheduled time has already passed will continue firing on every Beat tick until the task is manually disabled. This is Celery's native clocked-schedule behavior.

**Use `one_off=True` for one-time tasks** when you want behavior similar to `django-celery-beat`.

---

## Task Arguments and Keyword Arguments

`PeriodicTask.args` and `PeriodicTask.kwargs` are stored as JSON strings in the database but delivered to Celery as real Python objects: a tuple and a dictionary, respectively.

Both arguments can be specified as JSON strings:

```python
PeriodicTask(
    name="with-args",
    task="app.process",
    discriminator="interval",
    schedule_id=schedule.id,
    args='["order-42"]',
    kwargs='{"dry_run": true}',
)
```

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

### Roll back one revision

```bash
sbeat-migrate downgrade -1 --dburi "$DBURI"
```

**Never edit an existing migration revision after it has been published.** Create a new revision, such as `0003_add_foo.py`, instead.

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

The admin UI is an optional extra rather than a core dependency. Install the core package on Celery workers and install the `[admin]` extra only on the machine running the admin UI.

---

## Detecting Changes and Bulk Updates

Single-object ORM operations automatically update `PeriodicTaskChanged` through SQLAlchemy's `after_insert`, `after_update`, and `after_delete` events.

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

The scheduler detects the change on its next `tick()`.

---

## Version Compatibility

| Package version | SQLModel | SQLAlchemy | Celery | Python |
|---|---|---|---|---|
| `0.1.2` | `>=0.0.14` | `>=2.0` | `>=5.3` | `>=3.10` |
| `0.1.1` | `>=0.0.48` (too restrictive) | `>=2.1` (conflicts with SQLModel versions requiring SQLAlchemy `<2.1`) | `>=5.3` | `>=3.10` |

Upgrade to `0.1.2` if your stack pins SQLModel below `0.0.48` or SQLAlchemy below `2.1`.

Version `0.1.2` also fixes several runtime bugs. See `CHANGELOG.md` for details.

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

Install the package in editable mode:

```bash
pip install -e '.[dev]'
```

Run tests:

```bash
python -m pytest
```

Build the package:

```bash
python -m build
```

---

## Publishing a New Release

Update the package version in both `pyproject.toml` and `src/sqlmodel_celery_beat/__init__.py`. The two versions must match.

Remove previous build artifacts and rebuild:

```bash
rm -rf dist build

python -m build

python -m twine check dist/*
```

Upload to TestPyPI first, verify installation in a clean virtual environment, and then upload to PyPI:

```bash
twine upload --repository testpypi dist/*

twine upload dist/*
```

Tag the release:

```bash
git tag vX.Y.Z
git push origin main --tags
```

**Important:** PyPI does not allow an uploaded distribution filename to be reused. Always bump the version, even for a one-character fix.

---

## License

BSD-3-Clause. See `LICENSE.md`.