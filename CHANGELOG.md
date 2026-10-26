# Changelog

All notable changes to `sqlmodel-celery-beat-pg` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.2] — 2026-10-25

### Fixed

- **`SessionManager(schema=...)` is now actually applied.** The argument was
  previously stored on the object but never passed to the engine, queries, or
  Alembic — the tables were silently created in `public`. The engine now opens
  every connection with `options=-c search_path=<schema>,public`, so both
  `CREATE TABLE` and unqualified `SELECT` resolve inside the schema first.

- **`PeriodicTask.args` / `.kwargs` are deserialized from JSON strings.**
  `DatabaseScheduler._reload` was passing the raw DB strings straight into
  `ScheduleEntry`, so Celery dispatched tasks with a single positional string
  instead of a tuple of arguments and an empty kwargs dict. Both fields are now
  parsed via `json.loads` before dispatch.

- **`PeriodicTaskChanged` marker row is created on first write.** The
  `after_insert` / `after_update` / `after_delete` handler only executed an
  `UPDATE`, so on a fresh database the marker table stayed empty and
  `DatabaseScheduler.tick()` returned early — no task ever fired. The handler
  now detects `rowcount == 0` and `INSERT`s the row.

- **`DatabaseScheduler.tick()` now actually dispatches due tasks.** The override
  previously reloaded the schedule and returned; it never called
  `super().tick()`. It now reloads (if the marker changed) and then runs the
  base implementation.

- **`ClockedSchedule` one-shot semantics are enforced.** A `ClockedSchedule`
  whose `clocked_time` had already passed would fire on every beat tick until
  the row was manually removed. `PeriodicTask` now has a `one_off` boolean
  (migration `0002`) and `DatabaseScheduler` disables the row after the first
  successful dispatch — matching `django-celery-beat`.

- **`sqlmodel_celery_beat.cli.migrate` no longer ignores `--schema`.**
  The CLI passes it through to `run_alembic`, which threads it into
  `migrations/env.py` via `run_schema` so `alembic_version` is created inside
  the target schema.

### Changed

- **Loosened dependency pins.**
  - `sqlmodel>=0.0.14` (was `>=0.0.48`).
  - `sqlalchemy>=2.0` (was `>=2.1`).

  The package’s code only uses SQLModel 0.0.14 APIs and SQLAlchemy 2.0 APIs. The
  previous pins conflicted with `sqlmodel<2.1.0`’s own SQLAlchemy cap and made
  the wheel unusable in stacks that pin `sqlmodel==0.0.31` / `sqlalchemy==2.0.46`.

- **`sbeat list-tasks`** now prints a `one_off` column alongside `enabled`.

- **`sbeat-migrate`** accepts `--dburi` and `--schema` as first-class options;
  positional args are forwarded to the Alembic command unchanged.

### Added

- `PeriodicTask.one_off` column (migration `0002_add_one_off`).
- `sbeat init --schema`, `sbeat migrate --schema`, `sbeat list-tasks --schema`,
  `sbeat shell --schema`, `sbeat admin --schema`.
- `migrations/env.py` honours `run_schema` for `version_table_schema` and sets
  `include_schemas=True` so autogenerate sees existing tables inside the target
  schema.
- `PeriodicTaskAdmin.column_list` now exposes `one_off` in the web UI.
- README section on one-shot tasks and the args/kwargs contract.

### Internal

- `_decode_json` helper in `schedulers.py` centralises the args/kwargs parsing.
- `_with_search_path` helper in `migrate.py` builds the `options=-c
  search_path=…` URL fragment consistently for both `run_alembic` and
  `SessionManager` callers.

### Upgrade notes

- **If you were relying on `SessionManager(schema=...)` to route tables into a
  schema, verify after upgrading that the tables actually landed where you
  expected.** In 0.1.1 they went to `public` regardless of the argument.
- **If you created any `PeriodicTask` rows with `args` / `kwargs` before 0.1.2,
  re-check them.** Tasks dispatched prior to this release received their args as
  a JSON string; if your task code defended against that, you can simplify it.
- **Run `sbeat migrate` after upgrading** so the new `one_off` column is added
  to `celery_periodic_task`.

---

## [0.1.1] — 2026-09-14

### Added

- Initial public release on PyPI.
- SQLModel models for `IntervalSchedule`, `CrontabSchedule`, `SolarSchedule`,
  `ClockedSchedule`, `PeriodicTask`, `PeriodicTaskChanged`.
- `DatabaseScheduler` for `celery beat -S`.
- Bundled Alembic migrations (`0001_initial`).
- `sbeat` / `scb` CLI with `init`, `migrate`, `list-tasks`, `shell`, `admin`.
- `sbeat-migrate` CLI wrapping Alembic.
- Optional FastAPI + SQLAdmin admin UI (`[admin]` extra) at `/admin`.
- `configure(dburi=..., schema=...).apply_to_celery(celery)` helper.

### Known issues (fixed in 0.1.2)

- `SessionManager(schema=...)` accepted the argument but never used it.
- `PeriodicTask.args` / `.kwargs` were forwarded to Celery as raw JSON strings.
- `PeriodicTaskChanged` was never inserted, so `tick()` short-circuited on a
  fresh database.
- `DatabaseScheduler.tick()` overrode the base method without calling `super()`,
  so due tasks were never dispatched.
- `ClockedSchedule` one-shot tasks fired on every beat tick after their due
  time.
- `sqlmodel>=0.0.48` and `sqlalchemy>=2.1` pins were incompatible with
  SQLModel’s own `sqlalchemy<2.1` requirement.

---

## Versioning policy

- **Major** — breaking API change (removed / renamed public function or model
  field).
- **Minor** — additive change (new model, new CLI command, new config option).
- **Patch** — bug fix, dependency relaxation, documentation only.

Deprecations are announced one minor version ahead of removal.