# Changelog

## 0.1.4 - 2026-10-26

### Fixed
- **`DetachedInstanceError` on every tick** — `_maybe_reload` now reads
  `PeriodicTaskChanged.last_update` as a scalar inside the session instead
  of touching the ORM instance after the session closes.
- **`TypeError: ScheduleEntry._next_instance() got an unexpected keyword
  argument 'total_run_count'`** — `DatabaseScheduleEntry.__next__` no longer
  forwards `total_run_count` to Celery's base method. Celery auto-increments
  it internally; the kwarg was only ever accepted because a different Celery
  version was assumed.

### Changed
- `SessionManager` now defaults to `expire_on_commit=False`, preventing a
  whole class of "detached object" bugs. Pass `expire_on_commit=True`
  explicitly if you need the old behaviour.
- `DatabaseScheduler.sync()` is now called at the end of every `tick()`,
  so `last_run_at` / `total_run_count` are persisted regularly instead of
  only on `close()`.
- `DatabaseScheduler._reload()` is guarded by an `RLock`, making it safe to
  call from a background thread (e.g. a Postgres LISTEN/NOTIFY listener).

### Added
- `SessionManager.session_scope(readonly=True)` for read-only queries that
  should not pay the cost of a `COMMIT` roundtrip.

## 0.1.3 — 2026-10-26

### Added
- `celery.beat_schedulers` entry point alias `sqlmodel` — `celery -S sqlmodel` now works.
- `DatabaseScheduleEntry` enforcing `start_time`, `expire_seconds`, and `one_off`.
- `PeriodicTask.start_time`, `expire_seconds`, `description` columns (migration `0003`).
- `sbeat cleanup-schedules` command and `cleanup_orphan_schedules()` helper.
- `validate_schedule_exists()` helper.
- `[solar]` extra (`ephem`); solar schedules validate event/coordinates on construction.
- Crontab schedules validate expressions at write time (also surfaced in admin).
- `tzdata` declared for Windows.

### Changed
- `DatabaseScheduler` resolves its database from `app.conf.beat_dburi`, `beat_schema`, `beat_engine_options`; an explicit `session_manager` still wins.
- `BeatConfig.apply_to_celery()` writes only supported Celery settings and also sets `beat_max_loop_interval = 5` and `timezone`.
- `Period` is now stored as lowercase values (`seconds`); migration `0004` converts existing rows.
- `args`, `kwargs`, `headers` are `Text` columns (no 1024-char cap). Migration `0003`.
- `PeriodicTaskChanged` normalised to a single row (`id = 1`); `update_changed()` no longer commits. Migration `0005`.
- `use_timezone` is applied to Celery; `table_prefix` removed (fixed `celery_` prefix).
- `sbeat-migrate revision` correctly parses `-m/--message`, `--autogenerate`, `--rev-id`.
- `SessionManager.session_factory(None)` reuses the configured engine; override engines are cached and disposed on `close()`.
- `init_db()` only creates the six package tables.
- CLI prints an actionable message instead of a traceback when no database is configured.

### Fixed
- Stock `celery -A app beat -S sqlmodel` boots without manual `session_manager` injection.
- `sync()` persists `last_run_at` and `total_run_count`; dirty state survives reload and DB errors; `close()` flushes.
- `_reload()` isolates per-entry failures, merges dirty run state, merges `beat_schedule`, installs default entries.
- Change detection listens on all four schedule models, uses the marker timestamp (clock-skew safe), and refreshes at least every 300 s.
- One-off tasks are only disabled after a successful publish.
- `one_off` no longer leaks into dispatch options; only valid for `discriminator="clocked"`.
- `headers` are forwarded and `periodic_task_name` is always set.
- Naive `clocked_time` values are normalised to UTC.
- Deleting the last referencing task removes the orphan schedule.
- `date_changed` updates on write.
- `alembic check` reports no drift between models and migrations.

### Compatibility
- Requires Celery >= 5.3; Celery 5.6 `clocked` fallback is covered by tests.
- No breaking changes to public imports or existing CLI command names.

## 0.1.2 — 2026-10-25

### Fixed
- **`SessionManager(schema=...)`** now actually applied via `search_path=<schema>,public`.
- **`PeriodicTask.args` / `.kwargs`** deserialized from JSON strings.
- **`PeriodicTaskChanged`** row created on first write.
- **`DatabaseScheduler.tick()`** now calls `super().tick()`.
- **`ClockedSchedule` one-shot semantics** enforced via `one_off` (migration `0002`).

### Changed
- `sqlmodel>=0.0.14`, `sqlalchemy>=2.0`.
- `sbeat migrate` / `sbeat-migrate` accept `--schema`.

### Added
- `PeriodicTask.one_off` and `0002_add_one_off`.

## 0.1.1 — 2025-01-01
Initial release.