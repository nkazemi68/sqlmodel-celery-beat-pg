from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config

_HERE = Path(__file__).parent
_INI = _HERE / "migrations" / "alembic.ini"


def _with_search_path(dburi: str, schema: str) -> str:
    sep = "&" if "?" in dburi else "?"
    return f"{dburi}{sep}options=-c%20search_path%3D{schema}%2Cpublic"


def run_alembic(
    cmd: str,
    *args: str,
    dburi: Optional[str] = None,
    schema: Optional[str] = None,
) -> None:
    cfg = Config(str(_INI))
    cfg.set_main_option("script_location", str(_HERE / "migrations"))
    if dburi:
        url = _with_search_path(dburi, schema) if schema else dburi
        cfg.set_main_option("sqlalchemy.url", url)
    if schema:
        cfg.set_main_option("run_schema", schema)

    if cmd == "upgrade":
        command.upgrade(cfg, args[0] if args else "head")
    elif cmd == "downgrade":
        command.downgrade(cfg, args[0] if args else "-1")
    elif cmd == "stamp":
        command.stamp(cfg, args[0] if args else "head")
    elif cmd == "revision":
        message: Optional[str] = None
        autogenerate = False
        rev_id: Optional[str] = None
        i = 0
        while i < len(args):
            tok = args[i]
            if tok in ("-m", "--message") and i + 1 < len(args):
                message = args[i + 1]; i += 2; continue
            if tok.startswith("--message="):
                message = tok.split("=", 1)[1]; i += 1; continue
            if tok == "--autogenerate":
                autogenerate = True; i += 1; continue
            if tok in ("--rev-id",) and i + 1 < len(args):
                rev_id = args[i + 1]; i += 2; continue
            if tok.startswith("--rev-id="):
                rev_id = tok.split("=", 1)[1]; i += 1; continue
            i += 1
        command.revision(cfg, message=message, autogenerate=autogenerate, rev_id=rev_id)
    else:
        raise SystemExit(
            f"unknown migration command {cmd!r}; "
            "use: upgrade, downgrade, revision, stamp"
        )


def main() -> None:
    import sys
    argv = sys.argv
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(
            "usage: scb-migrate <upgrade|downgrade|revision|stamp> [args...] "
            "[--dburi URI] [--schema NAME]\n\n"
            "commands:\n"
            "  upgrade [rev]    apply migrations (default: head)\n"
            "  downgrade [rev]  roll back (default: -1)\n"
            "  revision -m MSG  autogenerate a new migration\n"
            "  stamp [rev]      mark revision without running it\n\n"
            "options:\n"
            "  --dburi URI      override the configured database URI\n"
            "  --schema NAME    target PostgreSQL schema (via search_path)\n"
        )
        sys.exit(0 if len(argv) >= 2 else 1)

    cmd = argv[1]
    rest = argv[2:]
    dburi = schema = None
    positional = []
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok == "--dburi" and i + 1 < len(rest):
            dburi = rest[i + 1]; i += 2; continue
        if tok.startswith("--dburi="):
            dburi = tok.split("=", 1)[1]; i += 1; continue
        if tok == "--schema" and i + 1 < len(rest):
            schema = rest[i + 1]; i += 2; continue
        if tok.startswith("--schema="):
            schema = tok.split("=", 1)[1]; i += 1; continue
        positional.append(tok); i += 1

    run_alembic(cmd, *positional, dburi=dburi, schema=schema)