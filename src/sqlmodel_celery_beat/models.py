from __future__ import annotations
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Enum, Index, UniqueConstraint, event
from sqlmodel import Field, SQLModel, select

class Period(str, enum.Enum):
    DAYS = "days"
    HOURS = "hours"
    MINUTES = "minutes"
    SECONDS = "seconds"
    MICROSECONDS = "microseconds"

class IntervalSchedule(SQLModel, table=True):
    __tablename__ = "celery_interval_schedule"
    __table_args__ = (UniqueConstraint("every", "period", name="uq_interval_every_period"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    every: int = Field(gt=0)
    period: Period = Field(sa_column=Column(Enum(Period), nullable=False))

    def schedule(self):
        import celery.schedules as s
        from datetime import timedelta
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

    def schedule(self):
        import celery.schedules as s
        return s.crontab(
            minute=self.minute, hour=self.hour, day_of_week=self.day_of_week,
            day_of_month=self.day_of_month, month_of_year=self.month_of_year,
            nowfun=lambda: datetime.now(timezone.utc), timezone=self.timezone,
        )

class SolarSchedule(SQLModel, table=True):
    __tablename__ = "celery_solar_schedule"
    id: Optional[int] = Field(default=None, primary_key=True)
    event: str = Field(max_length=64)
    latitude: float
    longitude: float

    def schedule(self):
        import celery.schedules as s
        return s.solar(event=self.event, lat=self.latitude, lon=self.longitude,
                       nowfun=lambda: datetime.now(timezone.utc))

class ClockedSchedule(SQLModel, table=True):
    __tablename__ = "celery_clocked_schedule"
    id: Optional[int] = Field(default=None, primary_key=True)
    clocked_time: datetime

    def schedule(self):
        import celery.schedules as s
        return s.clocked(self.clocked_time)

class PeriodicTask(SQLModel, table=True):
    __tablename__ = "celery_periodic_task"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True, max_length=255)
    task: str = Field(max_length=255)
    args: str = Field(default="[]", max_length=1024)
    kwargs: str = Field(default="{}", max_length=1024)
    queue: Optional[str] = Field(default=None, max_length=255)
    exchange: Optional[str] = Field(default=None, max_length=255)
    routing_key: Optional[str] = Field(default=None, max_length=255)
    headers: str = Field(default="{}", max_length=1024)
    priority: Optional[int] = Field(default=None)
    expires: Optional[datetime] = Field(default=None)
    enabled: bool = Field(default=True)
    last_run_at: Optional[datetime] = Field(default=None)
    total_run_count: int = Field(default=0)
    date_changed: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    discriminator: str = Field(max_length=32)
    schedule_id: int

    __table_args__ = (Index("ix_periodic_task_discriminator_schedule", "discriminator", "schedule_id"),)

class PeriodicTaskChanged(SQLModel, table=True):
    __tablename__ = "celery_periodic_task_changed"
    id: Optional[int] = Field(default=None, primary_key=True)
    last_update: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def update_changed(cls, session) -> None:
        row = session.exec(select(cls).limit(1)).first()
        if row is None:
            session.add(cls())
        else:
            row.last_update = datetime.now(timezone.utc)
            session.add(row)
        session.commit()

    @classmethod
    def update_from_session(cls, session) -> None:
        cls.update_changed(session)

@event.listens_for(PeriodicTask, "after_insert")
@event.listens_for(PeriodicTask, "after_update")
@event.listens_for(PeriodicTask, "after_delete")
def _touch_changed_row(mapper, connection, target):
    connection.execute(
        PeriodicTaskChanged.__table__.update().values(last_update=datetime.now(timezone.utc))
    )