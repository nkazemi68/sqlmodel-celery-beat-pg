import importlib.metadata
import tomllib
from pathlib import Path

# Repo root is the parent of the tests directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    path = _REPO_ROOT / "pyproject.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))["project"]["version"]


def test_version_sources_match():
    import sqlmodel_celery_beat
    assert sqlmodel_celery_beat.__version__ == "0.1.3"
    assert sqlmodel_celery_beat.__version__ == _pyproject_version()
    # Installed distribution version must match as well.
    assert importlib.metadata.version("sqlmodel-celery-beat-pg") == "0.1.3"


def test_cli_help():
    from typer.testing import CliRunner
    from sqlmodel_celery_beat.cli import app
    r = CliRunner().invoke(app, ["--help"])
    assert r.exit_code == 0