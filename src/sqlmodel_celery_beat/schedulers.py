from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

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

class DatabaseScheduler(Scheduler):
    def __init__(self, *args, **kwargs):
        self.session_manager: SessionManager = kwargs.pop("session_manager", None)
        if self.session_manager is None:
            raise ValueError("session_manager is required")
        self._last_reload: Optional[datetime] = None
        self._schedule: Dict[str, ScheduleEntry] = {}
        super().__init__(*args, **kwargs)

    @property
    def schedule(self) -> Dict[str, ScheduleEntry]:
        return self._schedule

    def setup_schedule(self):
        self._reload()

    def tick(self):
        with self.session_manager.session_scope() as session:
            marker = session.exec(select(PeriodicTaskChanged).limit(1)).first()
            if marker is None:
                return
            if self._last_reload is None or marker.last_update > self._last_reload:
                self._last_reload = marker.last_update
                self._reload()

    def _reload(self) -> None:
        new_schedule = {}
        with self.session_manager.session_scope() as session:
            tasks = session.exec(select(PeriodicTask).where(PeriodicTask.enabled == True)).all()
            for task in tasks:
                model_cls = MODEL_MAP.get(task.discriminator)
                if model_cls is None:
                    logger.warning("Unknown discriminator %r", task.discriminator)
                    continue
                sched_obj = session.get(model_cls, task.schedule_id)
                if sched_obj is None:
                    logger.warning("Missing schedule %s", task.schedule_id)
                    continue
                new_schedule[task.name] = ScheduleEntry(
                    name=task.name, task=task.task, schedule=sched_obj.schedule(),
                    args=task.args, kwargs=task.kwargs,
                    options={"queue": task.queue, "exchange": task.exchange,
                             "routing_key": task.routing_key, "priority": task.priority,
                             "expires": task.expires},
                    last_run_at=task.last_run_at, total_run_count=task.total_run_count,
                )
        self._schedule = new_schedule
        self._last_reload = datetime.now(timezone.utc)

    @classmethod
    def update_changed(cls, session) -> None:
        PeriodicTaskChanged.update_changed(session)

    @classmethod
    def update_from_session(cls, session) -> None:
        PeriodicTaskChanged.update_from_session(session)