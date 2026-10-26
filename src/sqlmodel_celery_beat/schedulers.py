from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set

from celery.beat import ScheduleEntry, Scheduler
from celery.schedules import maybe_schedule
from sqlmodel import select

from .models import (
    ClockedSchedule, CrontabSchedule, IntervalSchedule,
    PeriodicTask, PeriodicTaskChanged, SolarSchedule,
)
from .session import SessionManager

logger = logging.getLogger(__name__)

MODEL_MAP = {
    "interval": IntervalSchedule,
    "crontab": CrontabSchedule,
    "solar": SolarSchedule,
    "clocked": ClockedSchedule,
}

FULL_REFRESH_INTERVAL = 300.0


def _decode_json(value: Any, default: Any) -> Any:
    if value in (None, "", b""):
        return default
    if isinstance(value, (dict, list, tuple)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning("Could not decode JSON value: %r", value)
            return default
    return default


class DatabaseScheduleEntry(ScheduleEntry):
    """ScheduleEntry that knows about start_time / expiry / one_off."""

    def __init__(self, *, model=None, **kwargs):
        self.model_name = model.name if model is not None else None
        self.start_time: Optional[datetime] = model.start_time if model else None
        self.expire_seconds: Optional[int] = model.expire_seconds if model else None
        self.expires: Optional[datetime] = model.expires if model else None
        self.one_off: bool = bool(model.one_off) if model else False
        super().__init__(**kwargs)

    def __next__(self, last_run_at=None, total_run_count=None):
        # Celery 5.x's ScheduleEntry._next_instance accepts only ``last_run_at``
        # and auto-increments ``total_run_count`` itself. Forwarding the kwarg
        # would raise TypeError on the first tick.
        new = super().__next__(last_run_at=last_run_at)
        if total_run_count is not None:
            new.total_run_count = total_run_count
        new.model_name = self.model_name
        new.start_time = self.start_time
        new.expire_seconds = self.expire_seconds
        new.expires = self.expires
        new.one_off = self.one_off
        return new

    def is_expired(self, now: datetime) -> bool:
        if self.expires is not None and now > self.expires:
            return True
        if self.expire_seconds is not None and self.last_run_at is not None:
            deadline = self.last_run_at + timedelta(seconds=self.expire_seconds)
            if now > deadline:
                return True
        return False

    def is_due(self):
        now = datetime.now(timezone.utc)
        if self.start_time is not None and now < self.start_time:
            return False, 5.0
        if self.is_expired(now):
            return False, FULL_REFRESH_INTERVAL
        return super().is_due()


class DatabaseScheduler(Scheduler):
    max_interval = 5
    Entry = DatabaseScheduleEntry

    def __init__(self, *args, **kwargs):
        self._schedule: Dict[str, DatabaseScheduleEntry] = {}
        self._dirty: Set[str] = set()
        self._pending_one_off: Set[str] = set()
        self._pending_expiry: Set[str] = set()
        self._last_reload: Optional[datetime] = None
        self._last_full_refresh: Optional[datetime] = None
        self._reload_mutex = threading.RLock()

        self.session_manager: Optional[SessionManager] = kwargs.pop(
            "session_manager", None
        )
        app = kwargs.get("app") or (args[0] if args else None)

        if self.session_manager is None and app is not None:
            self.session_manager = self._session_manager_from_app(app)
        if self.session_manager is None:
            try:
                from .config import get_config
                cfg = get_config()
                self.session_manager = SessionManager(
                    cfg.dburi, schema=cfg.schema, **(cfg.engine_options or {})
                )
            except RuntimeError:
                pass
        if self.session_manager is None:
            raise RuntimeError(
                "sqlmodel-celery-beat: no database configured. Set "
                "app.conf.beat_dburi, or call "
                "sqlmodel_celery_beat.configure(dburi=...) before starting beat."
            )
        super().__init__(*args, **kwargs)

    @staticmethod
    def _session_manager_from_app(app) -> Optional[SessionManager]:
        dburi = app.conf.get("beat_dburi")
        if not dburi:
            return None
        schema = app.conf.get("beat_schema")
        engine_options = dict(app.conf.get("beat_engine_options") or {})
        return SessionManager(dburi, schema=schema, **engine_options)

    # ------------------------------------------------------------------
    @property
    def schedule(self) -> Dict[str, DatabaseScheduleEntry]:
        return self._schedule

    def setup_schedule(self):
        self._reload()
        self._install_default_entries()
        self._merge_static_entries()

    # ------------------------------------------------------------------
    def tick(self):
        self._maybe_reload()
        self._scan_expirations()
        try:
            result = super().tick()
        finally:
            self._drain_pending_one_off()
            self._drain_pending_expiry()
            self.sync()
        return result

    # ------------------------------------------------------------------
    def reserve(self, entry):
        name = entry.name
        new_entry = super().reserve(entry)
        self._dirty.add(name)
        return new_entry

    def sync(self):
        if not self._dirty:
            return
        names = list(self._dirty)
        persisted: list[str] = []
        try:
            with self.session_manager.session_scope() as session:
                tasks = {
                    t.name: t
                    for t in session.exec(
                        select(PeriodicTask).where(PeriodicTask.name.in_(names))
                    ).all()
                }
                for name in names:
                    entry = self._schedule.get(name)
                    task = tasks.get(name)
                    if entry is None or task is None:
                        persisted.append(name)
                        continue
                    task.last_run_at = entry.last_run_at
                    task.total_run_count = entry.total_run_count
                    session.add(task)
                    persisted.append(name)
                # Our writes bump the change marker. Advance _last_reload past
                # our own bump so the next tick's _maybe_reload skips a
                # pointless reload.
                session.flush()
                marker = session.get(PeriodicTaskChanged, 1)
                if marker is not None:
                    self._last_reload = marker.last_update
        except Exception:
            logger.exception(
                "sync() failed; retaining %d dirty entries for retry",
                len(self._dirty),
            )
            return
        for name in persisted:
            self._dirty.discard(name)

    def close(self):
        try:
            self.sync()
        finally:
            super().close()

    # ------------------------------------------------------------------
    def apply_entry(self, entry, producer=None):
        result = super().apply_entry(entry, producer=producer)
        if result is not None and isinstance(entry, DatabaseScheduleEntry) and entry.one_off:
            self._pending_one_off.add(entry.name)
        return result

    # ------------------------------------------------------------------
    def _maybe_reload(self) -> None:
        now = datetime.now(timezone.utc)
        if (
            self._last_full_refresh is None
            or (now - self._last_full_refresh).total_seconds() >= FULL_REFRESH_INTERVAL
        ):
            self._last_full_refresh = now
            self._reload()
            return

        marker_last_update: Optional[datetime] = None
        try:
            with self.session_manager.session_scope(readonly=True) as session:
                marker = session.get(PeriodicTaskChanged, 1)
                if marker is not None:
                    # Read the scalar *inside* the session so the ORM object
                    # never escapes the session boundary (fixes DetachedInstanceError).
                    marker_last_update = marker.last_update
        except Exception:
            logger.exception("_maybe_reload: marker read failed")
            return

        if marker_last_update is None:
            return
        if self._last_reload is None or marker_last_update > self._last_reload:
            self._reload()

    def _scan_expirations(self) -> None:
        now = datetime.now(timezone.utc)
        for name, entry in self._schedule.items():
            if isinstance(entry, DatabaseScheduleEntry) and entry.is_expired(now):
                self._pending_expiry.add(name)

    def _drain_pending_one_off(self) -> None:
        if not self._pending_one_off:
            return
        names = list(self._pending_one_off)
        try:
            with self.session_manager.session_scope() as session:
                for name in names:
                    task = session.exec(
                        select(PeriodicTask).where(PeriodicTask.name == name)
                    ).first()
                    if task is not None and task.enabled:
                        task.enabled = False
                        session.add(task)
        except Exception:
            logger.exception("Failed to disable one-off tasks; will retry")
            return
        for name in names:
            self._pending_one_off.discard(name)
            self._schedule.pop(name, None)

    def _drain_pending_expiry(self) -> None:
        if not self._pending_expiry:
            return
        names = list(self._pending_expiry)
        try:
            with self.session_manager.session_scope() as session:
                for name in names:
                    task = session.exec(
                        select(PeriodicTask).where(PeriodicTask.name == name)
                    ).first()
                    if task is not None and task.enabled:
                        task.enabled = False
                        session.add(task)
                        logger.info("Disabled expired task %r", name)
        except Exception:
            logger.exception("Failed to disable expired tasks")
            return
        for name in names:
            self._pending_expiry.discard(name)
            self._schedule.pop(name, None)

    def _reload(self) -> None:
        with self._reload_mutex:
            self._reload_locked()

    def _reload_locked(self) -> None:
        new_schedule: Dict[str, DatabaseScheduleEntry] = {}
        marker_value: Optional[datetime] = None

        try:
            with self.session_manager.session_scope(readonly=True) as session:
                marker = session.get(PeriodicTaskChanged, 1)
                if marker is not None:
                    marker_value = marker.last_update
                tasks = session.exec(
                    select(PeriodicTask).where(PeriodicTask.enabled == True)  # noqa: E712
                ).all()
                for task in tasks:
                    try:
                        entry = self._make_entry(task, session)
                    except Exception:
                        logger.exception(
                            "Skipping invalid task %r (discriminator=%r, id=%r)",
                            task.name, task.discriminator, task.schedule_id,
                        )
                        continue
                    new_schedule[task.name] = entry
        except Exception:
            logger.exception("_reload failed; keeping current schedule")
            return

        for name in self._dirty:
            old = self._schedule.get(name)
            new = new_schedule.get(name)
            if old is not None and new is not None:
                new.last_run_at = old.last_run_at
                new.total_run_count = old.total_run_count

        self._schedule = new_schedule
        self._last_reload = marker_value or datetime.now(timezone.utc)
        self._last_full_refresh = datetime.now(timezone.utc)

        self._merge_static_entries()
        logger.debug("Reloaded %d entries from DB", len(new_schedule))

    def _make_entry(self, task: PeriodicTask, session) -> DatabaseScheduleEntry:
        model_cls = MODEL_MAP.get(task.discriminator)
        if model_cls is None:
            raise ValueError(f"Unknown discriminator {task.discriminator!r}")
        sched_obj = session.get(model_cls, task.schedule_id)
        if sched_obj is None:
            raise ValueError(
                f"Missing {task.discriminator} schedule id={task.schedule_id}"
            )

        args = tuple(_decode_json(task.args, []))
        kwargs_ = _decode_json(task.kwargs, {})
        if not isinstance(kwargs_, dict):
            kwargs_ = {}
        headers = _decode_json(task.headers, {})
        if not isinstance(headers, dict):
            headers = {}
        headers["periodic_task_name"] = task.name

        options: dict = {
            "queue": task.queue,
            "exchange": task.exchange,
            "routing_key": task.routing_key,
            "priority": task.priority,
            "expires": task.expires,
            "headers": headers,
        }
        options = {k: v for k, v in options.items() if v is not None}

        return self.Entry(
            model=task,
            name=task.name,
            task=task.task,
            schedule=sched_obj.schedule(),
            args=args,
            kwargs=kwargs_,
            options=options,
            last_run_at=task.last_run_at,
            total_run_count=task.total_run_count,
        )

    def _install_default_entries(self) -> None:
        try:
            if not self.app.conf.get("result_expires"):
                return
        except Exception:
            return
        name = "celery.backend_cleanup"
        if name in self._schedule:
            return
        try:
            from celery.schedules import crontab as _crontab
            self._schedule[name] = self.Entry(
                model=None,
                name=name,
                task="celery.backend_cleanup",
                schedule=_crontab("0", "4", "*"),
                options={"expire_seconds": 12 * 3600},
            )
        except Exception:
            logger.exception("Failed to install default cleanup entry")

    def _merge_static_entries(self) -> None:
        static = self.app.conf.get("beat_schedule") or {}
        for name, raw in static.items():
            if name in self._schedule:
                continue
            try:
                self._schedule[name] = self.Entry(
                    model=None,
                    name=name,
                    task=raw.get("task"),
                    schedule=maybe_schedule(raw.get("schedule")),
                    args=raw.get("args", ()),
                    kwargs=raw.get("kwargs", {}),
                    options=raw.get("options", {}),
                    relative=raw.get("relative"),
                )
            except Exception:
                logger.exception("Skipping static beat_schedule entry %r", name)

    # ------------------------------------------------------------------
    @classmethod
    def update_changed(cls, session) -> None:
        PeriodicTaskChanged.update_changed(session)

    @classmethod
    def update_from_session(cls, session) -> None:
        PeriodicTaskChanged.update_from_session(session)