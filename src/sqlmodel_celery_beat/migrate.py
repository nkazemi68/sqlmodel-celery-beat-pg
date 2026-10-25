from pathlib import Path
from alembic import command
from alembic.config import Config

_HERE = Path(__file__).parent
_INI = _HERE / "migrations" / "alembic.ini"

def run_alembic(cmd: str, *args: str, dburi: str | None = None) -> None:
    cfg = Config(str(_INI))
    cfg.set_main_option("script_location", str(_HERE / "migrations"))
    if dburi:
        cfg.set_main_option("sqlalchemy.url", dburi)
    commands = {
        "upgrade":   lambda: command.upgrade(cfg, args[0] if args else "head"),
        "downgrade": lambda: command.downgrade(cfg, args[0] if args else "-1"),
        "revision":  lambda: command.revision(cfg, *args),
        "stamp":     lambda: command.stamp(cfg, args[0] if args else "head"),
    }
    if cmd not in commands:
        raise SystemExit(f"unknown migration command {cmd!r}; use: {', '.join(commands)}")
    commands[cmd]()


def main() -> None:
    import sys
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(
            "usage: scb-migrate <upgrade|downgrade|revision|stamp> [args...]\n"
            "\n"
            "commands:\n"
            "  upgrade [rev]    apply migrations (default: head)\n"
            "  downgrade [rev]  roll back (default: -1)\n"
            "  revision -m MSG  autogenerate a new migration\n"
            "  stamp [rev]      mark revision without running it\n"
        )
        sys.exit(0 if len(sys.argv) >= 2 else 1)
    run_alembic(sys.argv[1], *sys.argv[2:])