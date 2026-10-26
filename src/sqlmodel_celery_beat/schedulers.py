from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from celery.beat import ScheduleEntry, Scheduler
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


def _decode_json(value: Any, default: Any) -> Any:
    """Deserialize a JSON string coming from the DB (args / kwargs columns)."""
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


class DatabaseScheduler(Scheduler):
    def __init__(self, *args, **kwargs):
        self.session_manager: SessionManager = kwargs.pop("session_manager", None)
        if self.session_manager is None:
            raise ValueError("session_manager is required")
        self._last_reload: Optional[datetime] = None
        self._schedule: Dict[str, ScheduleEntry] = {}
        self._pending_one_off: Set[str] = set()
        super().__init__(*args, **kwargs)

    # ==================================================================
    # Base contract
    # ==================================================================
    @property
    def schedule(self) -> Dict[str, ScheduleEntry]:
        return self._schedule

    def setup_schedule(self):
        self._reload()

    # ==================================================================
    # tick: reload on change + fire due tasks + disable one-shot rows
    # ==================================================================
    def tick(self):
        self._maybe_reload()
        try:
            result = super().tick()
        finally:
            self._drain_pending_one_off()
        return result

    def _maybe_reload(self) -> None:
        with self.session_manager.session_scope() as session:
            marker = session.exec(select(PeriodicTaskChanged).limit(1)).first()
            if marker is None:
                # No marker row yet — nothing has ever changed. Skip reload.
                return
            if self._last_reload is None or marker.last_update > self._last_reload:
                self._last_reload = marker.last_update
                self._reload()

    # ==================================================================
    # fire-and-disable for one_off tasks (ClockedSchedule)
    # ==================================================================
    def apply_entry(self, entry, producer=None):
        super().apply_entry(entry, producer=producer)
        if entry.options.get("one_off"):
            self._pending_one_off.add(entry.name)

    def _drain_pending_one_off(self) -> None:
        if not self._pending_one_off:
            return
        for name in list(self._pending_one_off):
            try:
                self._disable_one_off(name)
            except Exception:
                logger.exception("Failed to disable one-off task %r", name)
        self._pending_one_off.clear()

    def _disable_one_off(self, name: str) -> None:
        with self.session_manager.session_scope() as session:
            task = session.exec(
                select(PeriodicTask).where(PeriodicTask.name == name)
            ).first()
            if task is not None and task.enabled:
                task.enabled = False
                session.add(task)
                PeriodicTaskChanged.update_changed(session)
        # Remove from in-memory schedule so the next tick doesn't fire it again
        self._schedule.pop(name, None)

    # ==================================================================
    # Reload from DB
    # ==================================================================
    def _reload(self) -> None:
        new_schedule: Dict[str, ScheduleEntry] = {}
        with self.session_manager.session_scope() as session:
            tasks = session.exec(
                select(PeriodicTask).where(PeriodicTask.enabled == True)
            ).all()

            for task in tasks:
                model_cls = MODEL_MAP.get(task.discriminator)
                if model_cls is None:
                    logger.warning(
                        "Unknown discriminator %r for task %r",
                        task.discriminator, task.name,
                    )
                    continue

                sched_obj = session.get(model_cls, task.schedule_id)
                if sched_obj is None:
                    logger.warning(
                        "Missing %s schedule id=%s for task %r",
                        task.discriminator, task.schedule_id, task.name,
                    )
                    continue

                # ── FIX: deserialize args/kwargs (JSON strings from DB) ──
                args = tuple(_decode_json(task.args, []))
                kwargs = _decode_json(task.kwargs, {})
                if not isinstance(kwargs, dict):
                    kwargs = {}

                new_schedule[task.name] = ScheduleEntry(
                    name=task.name,
                    task=task.task,
                    schedule=sched_obj.schedule(),
                    args=args,
                    kwargs=kwargs,
                    options={
                        "queue": task.queue,
                        "exchange": task.exchange,
                        "routing_key": task.routing_key,
                        "priority": task.priority,
                        "expires": task.expires,
                        "one_off": task.one_off,
                    },
                    last_run_at=task.last_run_at,
                    total_run_count=task.total_run_count,
                )

        self._schedule = new_schedule
        self._last_reload = datetime.now(timezone.utc)
        logger.debug("Reloaded %d entries from DB", len(new_schedule))

    # ==================================================================
    # Classmethod aliases (kept for backward compatibility)
    # ==================================================================
    @classmethod
    def update_changed(cls, session) -> None:
        PeriodicTaskChanged.update_changed(session)

    @classmethod
    def update_from_session(cls, session) -> None:
        PeriodicTaskChanged.update_from_session(session)