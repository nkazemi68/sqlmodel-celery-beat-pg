def test_import():
    import sqlmodel_celery_beat
    assert sqlmodel_celery_beat.__version__ == "0.1.0"

def test_cli_help():
    from typer.testing import CliRunner
    from sqlmodel_celery_beat.cli import app
    r = CliRunner().invoke(app, ["--help"])
    assert r.exit_code == 0