from contextlib import contextmanager
from typing import Generator, Optional

from sqlmodel import Session, create_engine


class SessionManager:
    def __init__(self, dburi: str, schema: Optional[str] = None, **engine_kwargs):
        """
        Parameters
        ----------
        dburi:
            SQLAlchemy URL, e.g. ``postgresql+psycopg://user:pass@host/db``.
        schema:
            Optional PostgreSQL schema for the beat tables. Applied via
            ``search_path=<schema>,public`` so any CREATE / SELECT without an
            explicit schema qualifier is routed to that schema first.
        """
        self.schema = schema

        if schema:
            connect_args = engine_kwargs.setdefault("connect_args", {})
            existing = connect_args.get("options", "")
            sep = " " if existing else ""
            connect_args["options"] = f"{existing}{sep}-c search_path={schema},public"

        self.engine = create_engine(dburi, **engine_kwargs)

    def session_factory(self, dburi: Optional[str] = None) -> Session:
        engine = create_engine(dburi) if dburi else self.engine
        return Session(engine)

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


def init_db(engine) -> None:
    from sqlmodel import SQLModel
    import sqlmodel_celery_beat.models  # noqa: F401
    SQLModel.metadata.create_all(engine)