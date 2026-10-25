from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class BeatConfig:
    dburi: str
    schema: Optional[str] = None
    table_prefix: str = "celery_"
    use_timezone: str = "UTC"

    def apply_to_celery(self, app) -> None:
        from .session import SessionManager
        app.conf.beat_dburi = self.dburi
        app.conf.beat_scheduler = "sqlmodel_celery_beat.schedulers:DatabaseScheduler"
        app.conf.beat_scheduler_kwargs = {
            "session_manager": SessionManager(self.dburi, schema=self.schema),
        }
        if self.schema:
            app.conf.beat_schema = self.schema

_global: Optional[BeatConfig] = None

def configure(dburi: str, **kwargs) -> BeatConfig:
    global _global
    _global = BeatConfig(dburi=dburi, **kwargs)
    return _global

def get_config() -> BeatConfig:
    if _global is None:
        raise RuntimeError("sqlmodel_celery_beat is not configured. Call configure(dburi=...) first.")
    return _global