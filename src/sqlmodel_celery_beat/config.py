from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BeatConfig:
    dburi: str
    schema: Optional[str] = None
    engine_options: Optional[dict] = field(default_factory=dict)
    use_timezone: str = "UTC"

    def apply_to_celery(self, app) -> None:
        app.conf.beat_scheduler = "sqlmodel_celery_beat.schedulers:DatabaseScheduler"
        app.conf.beat_dburi = self.dburi
        if self.schema:
            app.conf.beat_schema = self.schema
        if self.engine_options:
            app.conf.beat_engine_options = dict(self.engine_options)
        app.conf.beat_max_loop_interval = 5
        if self.use_timezone:
            app.conf.timezone = self.use_timezone


_global: Optional[BeatConfig] = None


def configure(dburi: str, **kwargs) -> BeatConfig:
    global _global
    _global = BeatConfig(dburi=dburi, **kwargs)
    return _global


def get_config() -> BeatConfig:
    if _global is None:
        raise RuntimeError(
            "sqlmodel_celery_beat is not configured. "
            "Pass --dburi, set app.conf.beat_dburi, or call "
            "sqlmodel_celery_beat.configure(dburi=...)."
        )
    return _global