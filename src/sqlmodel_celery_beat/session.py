from contextlib import contextmanager
from typing import Generator, Optional
from sqlmodel import Session, create_engine

class SessionManager:
    def __init__(self, dburi: str, schema: Optional[str] = None, **engine_kwargs):
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