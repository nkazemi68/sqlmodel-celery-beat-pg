from __future__ import annotations

import enum
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, Column, Enum, Index, Text, UniqueConstraint, event, false as sa_false,
)
from sqlmodel import Field, SQLModel, select

logger = logging.getLogger(__name__)


class Period(str, enum.Enum):
    DAYS = "days"
    HOURS = "hours"
    MINUTES = "minutes"
    SECONDS = "seconds"
    MICROSECONDS = "microseconds"


VALID_DISCRIMINATORS = {"interval", "crontab", "solar", "clocked"}

VALID_SOLAR_EVENTS = {
    "dawn_astronomical", "dawn_nautical", "dawn_civil",
    "sunrise", "solar_noon", "sunset",
    "dusk_civil", "dusk_nautical", "dusk_astronomical",
}

_MODEL_CLASSES: dict[str, type] = {}


# ──────────────────────────────────────────────────────────────────────
# Schedules
# ──────────────────────────────────────────────────────────────────────

class IntervalSchedule(SQLModel, table=True):
    __tablename__ = "celery_interval_schedule"
    __table_args__ = (UniqueConstraint("every", "period", name="uq_interval_every_period"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    every: int = Field(gt=0)
    period: Period = Field(
        sa_column=Column(
            Enum(Period, values_callable=lambda x: [e.value for e in x]),
            nullable=False,
        )
    )

    def schedule(self):
        import celery.schedules as s
        return s.schedule(timedelta(**{self.period.value: self.every}))


class CrontabSchedule(SQLModel, table=True):
    __tablename__ = "celery_crontab_schedule"

    id: Optional[int] = Field(default=None, primary_key=True)
    minute: str = Field(default="*", max_length=240)
    hour: str = Field(default="*", max_length=96)
    day_of_week: str = Field(default="*", max_length=64)
    day_of_month: str = Field(default="*", max_length=124)
    month_of_year: str = Field(default="*", max_length=64)
    timezone: str = Field(default="UTC", max_length=64)

    def _validate_expressions(self) -> None:
        _validate_crontab_field("minute", self.minute, 60)
        _validate_crontab_field("hour", self.hour, 24)
        _validate_crontab_field("day_of_month", self.day_of_month, 32)
        _validate_crontab_field("month_of_year", self.month_of_year, 13)
        # Let celery's own parser verify the day-of-week string
        try:
            from celery.schedules import crontab as _crontab
            _crontab(
                minute=self.minute, hour=self.hour,
                day_of_week=self.day_of_week, day_of_month=self.day_of_month,
                month_of_year=self.month_of_year, timezone=self.timezone,
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid crontab: {exc}") from exc

    def schedule(self):
        import celery.schedules as s
        return s.crontab(
            minute=self.minute, hour=self.hour, day_of_week=self.day_of_week,
            day_of_month=self.day_of_month, month_of_year=self.month_of_year,
            nowfun=lambda: datetime.now(timezone.utc), timezone=self.timezone,
        )


def _validate_crontab_field(name: str, expr: str, max_value: int) -> None:
    if expr is None:
        return
    text = str(expr).strip()
    if text in ("", "*"):
        return
    for part in text.split(","):
        part = part.strip()
        if part == "*":
            continue
        if "/" in part:
            part = part.split("/", 1)[0]
        if part == "*":
            continue
        if "-" in part:
            lo_s, _, hi_s = part.partition("-")
            try:
                lo, hi = int(lo_s), int(hi_s)
            except ValueError as exc:
                if name == "day_of_week":
                    continue
                raise ValueError(f"Invalid {name} expression: {expr!r}") from exc
            if lo < 0 or hi >= max_value or lo > hi:
                raise ValueError(f"Invalid {name} value in {expr!r}")
        else:
            try:
                v = int(part)
            except ValueError as exc:
                if name == "day_of_week":
                    continue
                raise ValueError(f"Invalid {name} expression: {expr!r}") from exc
            if v < 0 or v >= max_value:
                raise ValueError(f"Invalid {name} value in {expr!r}")


class SolarSchedule(SQLModel, table=True):
    __tablename__ = "celery_solar_schedule"

    id: Optional[int] = Field(default=None, primary_key=True)
    event: str = Field(max_length=64)
    latitude: float
    longitude: float

    def __init__(self, **data):
        super().__init__(**data)
        self._validate()

    def _validate(self) -> None:
        if self.event not in VALID_SOLAR_EVENTS:
            raise ValueError(
                f"Invalid solar event: {self.event!r}. "
                f"Must be one of: {', '.join(sorted(VALID_SOLAR_EVENTS))}"
            )
        if not (-90.0 <= float(self.latitude) <= 90.0):
            raise ValueError(f"Invalid latitude: {self.latitude!r}")
        if not (-180.0 <= float(self.longitude) <= 180.0):
            raise ValueError(f"Invalid longitude: {self.longitude!r}")

    def schedule(self):
        try:
            import ephem  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Solar schedules require 'ephem'. Install with: "
                "pip install 'sqlmodel-celery-beat-pg[solar]'"
            ) from exc
        import celery.schedules as s
        return s.solar(
            event=self.event, lat=self.latitude, lon=self.longitude,
            nowfun=lambda: datetime.now(timezone.utc),
        )


class ClockedSchedule(SQLModel, table=True):
    __tablename__ = "celery_clocked_schedule"

    id: Optional[int] = Field(default=None, primary_key=True)
    clocked_time: datetime

    def schedule(self):
        import celery.schedules as s

        clocked_time = self.clocked_time
        if clocked_time.tzinfo is None:
            clocked_time = clocked_time.replace(tzinfo=timezone.utc)

        clocked = getattr(s, "clocked", None)
        if clocked is not None:
            return clocked(clocked_time)

        class _Clocked(s.BaseSchedule):
            def __init__(self, run_at, nowfun=None, app=None):
                self.run_at = run_at
                super().__init__(nowfun, app)

            def __reduce__(self):
                return self.__class__, (self.run_at, self.nowfun, self.app)

            def remaining_estimate(self, last_run_at):
                return self.run_at - self.now()

            def is_due(self, last_run_at):
                remaining = self.remaining_estimate(last_run_at)
                return remaining.total_seconds() <= 0, remaining.total_seconds()

        return _Clocked(clocked_time)


_MODEL_CLASSES.update({
    "interval": IntervalSchedule,
    "crontab": CrontabSchedule,
    "solar": SolarSchedule,
    "clocked": ClockedSchedule,
})


# ──────────────────────────────────────────────────────────────────────
# PeriodicTask
# ──────────────────────────────────────────────────────────────────────

class PeriodicTask(SQLModel, table=True):
    __tablename__ = "celery_periodic_task"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, max_length=255)
    task: str = Field(max_length=255)
    args: str = Field(
        default="[]",
        sa_column=Column(Text, nullable=False, default="[]"),
    )
    kwargs: str = Field(
        default="{}",
        sa_column=Column(Text, nullable=False, default="{}"),
    )
    queue: Optional[str] = Field(default=None, max_length=255)
    exchange: Optional[str] = Field(default=None, max_length=255)
    routing_key: Optional[str] = Field(default=None, max_length=255)
    headers: str = Field(
        default="{}",
        sa_column=Column(Text, nullable=False, default="{}"),
    )
    priority: Optional[int] = Field(default=None)
    expires: Optional[datetime] = Field(default=None)
    expire_seconds: Optional[int] = Field(default=None)
    start_time: Optional[datetime] = Field(default=None)
    description: Optional[str] = Field(default=None)
    enabled: bool = Field(default=True)
    one_off: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=sa_false()),
    )
    last_run_at: Optional[datetime] = Field(default=None)
    total_run_count: int = Field(default=0)
    date_changed: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )
    discriminator: str = Field(max_length=32)
    schedule_id: int

    __table_args__ = (
        Index("ix_periodic_task_discriminator_schedule", "discriminator", "schedule_id"),
    )

    def __init__(self, **data):
        super().__init__(**data)
        self._validate()

    def _validate(self) -> None:
        if self.discriminator not in VALID_DISCRIMINATORS:
            raise ValueError(
                f"Invalid discriminator: {self.discriminator!r}. "
                f"Must be one of {sorted(VALID_DISCRIMINATORS)}"
            )
        if self.one_off and self.discriminator != "clocked":
            raise ValueError("one_off=True requires discriminator='clocked'")
        if self.expires is not None and self.expire_seconds is not None:
            raise ValueError("expires and expire_seconds are mutually exclusive")
        if self.expire_seconds is not None and self.expire_seconds <= 0:
            raise ValueError("expire_seconds must be positive")


# ──────────────────────────────────────────────────────────────────────
# PeriodicTaskChanged (single-row marker, id = 1)
# ──────────────────────────────────────────────────────────────────────

class PeriodicTaskChanged(SQLModel, table=True):
    __tablename__ = "celery_periodic_task_changed"

    id: int = Field(default=1, primary_key=True)
    last_update: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def update_changed(cls, session) -> None:
        """Bump the marker. Does **not** commit; the caller controls the transaction."""
        now = datetime.now(timezone.utc)
        try:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(cls.__table__).values(id=1, last_update=now)
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"], set_={"last_update": now}
            )
            session.execute(stmt)
        except Exception:
            row = session.get(cls, 1)
            if row is None:
                session.add(cls(id=1, last_update=now))
            else:
                row.last_update = now
                session.add(row)

    @classmethod
    def update_from_session(cls, session) -> None:
        cls.update_changed(session)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def validate_schedule_exists(session, task: PeriodicTask) -> None:
    if task.discriminator not in VALID_DISCRIMINATORS:
        raise ValueError(f"Invalid discriminator: {task.discriminator!r}")
    model_cls = _MODEL_CLASSES[task.discriminator]
    sched = session.get(model_cls, task.schedule_id)
    if sched is None:
        raise ValueError(
            f"Task {task.name!r} references missing "
            f"{task.discriminator} schedule id={task.schedule_id}"
        )


def cleanup_orphan_schedules(session) -> int:
    total = 0
    for discriminator, model_cls in _MODEL_CLASSES.items():
        used_ids = {
            sid for (sid,) in session.execute(
                select(PeriodicTask.schedule_id).where(
                    PeriodicTask.discriminator == discriminator
                )
            ).all()
        }
        for sched in session.exec(select(model_cls)).all():
            if sched.id not in used_ids:
                session.delete(sched)
                total += 1
    return total


# ──────────────────────────────────────────────────────────────────────
# Events
# ──────────────────────────────────────────────────────────────────────

def _bump_marker(connection) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    now = datetime.now(timezone.utc)
    table = PeriodicTaskChanged.__table__
    try:
        stmt = pg_insert(table).values(id=1, last_update=now)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"], set_={"last_update": now}
        )
        connection.execute(stmt)
    except Exception:
        r = connection.execute(
            table.update().where(table.c.id == 1).values(last_update=now)
        )
        if r.rowcount == 0:
            connection.execute(table.insert().values(id=1, last_update=now))


def _touch_changed_row(mapper, connection, target):
    _bump_marker(connection)


for _model in (PeriodicTask, IntervalSchedule, CrontabSchedule, SolarSchedule, ClockedSchedule):
    for _evt in ("after_insert", "after_update", "after_delete"):
        event.listen(_model, _evt, _touch_changed_row)


@event.listens_for(PeriodicTask, "after_delete")
def _cleanup_orphan_after_delete(mapper, connection, target):
    model_cls = _MODEL_CLASSES.get(target.discriminator)
    if model_cls is None:
        return
    from sqlalchemy import func
    task_tbl = PeriodicTask.__table__
    count = connection.execute(
        select(func.count()).select_from(task_tbl).where(
            task_tbl.c.discriminator == target.discriminator,
            task_tbl.c.schedule_id == target.schedule_id,
        )
    ).scalar()
    if count == 0:
        sched_tbl = model_cls.__table__
        connection.execute(
            sched_tbl.delete().where(sched_tbl.c.id == target.schedule_id)
        )


# --- write-time validation for ORM/admin (bypasses __init__) --------------

@event.listens_for(PeriodicTask, "before_insert")
@event.listens_for(PeriodicTask, "before_update")
def _validate_periodic_task(mapper, connection, target):
    target._validate()


@event.listens_for(CrontabSchedule, "before_insert")
@event.listens_for(CrontabSchedule, "before_update")
def _validate_crontab(mapper, connection, target):
    target._validate_expressions()


@event.listens_for(SolarSchedule, "before_insert")
@event.listens_for(SolarSchedule, "before_update")
def _validate_solar(mapper, connection, target):
    target._validate()