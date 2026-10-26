from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Optional

from sqlmodel import Session, create_engine


class SessionManager:
    def __init__(self, dburi: str, schema: Optional[str] = None, **engine_kwargs):
        self.schema = schema
        self._dburi = dburi
        self._overrides: dict[str, "object"] = {}

        if schema:
            connect_args = engine_kwargs.setdefault("connect_args", {})
            existing = connect_args.get("options", "")
            sep = " " if existing else ""
            connect_args["options"] = f"{existing}{sep}-c search_path={schema},public"

        self.engine = create_engine(dburi, **engine_kwargs)

    def session_factory(self, dburi: Optional[str] = None) -> Session:
        if dburi is None or dburi == self._dburi:
            return Session(self.engine)
        if dburi not in self._overrides:
            self._overrides[dburi] = create_engine(dburi)
        return Session(self._overrides[dburi])

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self) -> None:
        for engine in self._overrides.values():
            engine.dispose()
        self._overrides.clear()


def init_db(engine, tables=None) -> None:
    from sqlmodel import SQLModel
    import sqlmodel_celery_beat.models  # noqa: F401

    if tables is None:
        from .models import (
            IntervalSchedule, CrontabSchedule, SolarSchedule,
            ClockedSchedule, PeriodicTask, PeriodicTaskChanged,
        )
        tables = [
            IntervalSchedule.__table__,
            CrontabSchedule.__table__,
            SolarSchedule.__table__,
            ClockedSchedule.__table__,
            PeriodicTask.__table__,
            PeriodicTaskChanged.__table__,
        ]
    SQLModel.metadata.create_all(engine, tables=tables)