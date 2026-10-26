from __future__ import annotations
import code
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from sqlmodel import select

from .config import get_config
from .models import (
    ClockedSchedule, CrontabSchedule, IntervalSchedule, Period,
    PeriodicTask, PeriodicTaskChanged, SolarSchedule,
)
from .session import SessionManager, init_db

app = typer.Typer(help="sqlmodel-celery-beat CLI", no_args_is_help=True)
console = Console()


def _mgr(dburi: Optional[str], schema: Optional[str] = None) -> SessionManager:
    return SessionManager(dburi or get_config().dburi, schema=schema)


@app.command()
def init(dburi: Optional[str] = typer.Option(None, "--dburi"),
         schema: Optional[str] = typer.Option(None, "--schema")):
    init_db(_mgr(dburi, schema).engine)
    console.print("[green]Tables created.[/green]")


@app.command()
def migrate(
    revision: str = typer.Option("head", "--rev"),
    dburi: Optional[str] = typer.Option(None, "--dburi"),
    schema: Optional[str] = typer.Option(None, "--schema"),
):
    from .migrate import run_alembic
    run_alembic(
        "upgrade",
        revision,
        dburi=dburi or get_config().dburi,
        schema=schema,
    )


@app.command(name="list-tasks")
def list_tasks(dburi: Optional[str] = typer.Option(None, "--dburi"),
               schema: Optional[str] = typer.Option(None, "--schema")):
    with _mgr(dburi, schema).session_scope() as s:
        tasks = s.exec(select(PeriodicTask)).all()
    t = Table(title="Periodic Tasks")
    for c in ("id", "name", "task", "schedule", "enabled", "one_off", "last_run_at"):
        t.add_column(c)
    for r in tasks:
        t.add_row(
            str(r.id), r.name, r.task,
            f"{r.discriminator}#{r.schedule_id}",
            "yes" if r.enabled else "no",
            "yes" if r.one_off else "no",
            r.last_run_at.isoformat() if r.last_run_at else "-",
        )
    console.print(t)


@app.command()
def shell(dburi: Optional[str] = typer.Option(None, "--dburi"),
          schema: Optional[str] = typer.Option(None, "--schema")):
    ns = {
        "session": _mgr(dburi, schema).session_factory(),
        "PeriodicTask": PeriodicTask,
        "IntervalSchedule": IntervalSchedule,
        "CrontabSchedule": CrontabSchedule,
        "SolarSchedule": SolarSchedule,
        "ClockedSchedule": ClockedSchedule,
        "PeriodicTaskChanged": PeriodicTaskChanged,
        "Period": Period,
        "select": select,
    }
    code.interact(banner="sqlmodel-celery-beat shell", local=ns)


@app.command()
def admin(dburi: Optional[str] = typer.Option(None, "--dburi"),
          schema: Optional[str] = typer.Option(None, "--schema"),
          host: str = typer.Option("127.0.0.1", "--host"),
          port: int = typer.Option(8000, "--port")):
    try:
        from .admin import build_app
    except ImportError:
        console.print("[red]Install admin extras:[/red] pip install 'sqlmodel-celery-beat-pg[admin]'")
        raise typer.Exit(1)
    import uvicorn
    uvicorn.run(build_app(_mgr(dburi, schema)), host=host, port=port)


if __name__ == "__main__":
    app()