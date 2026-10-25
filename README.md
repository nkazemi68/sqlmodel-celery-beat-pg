# sqlmodel-celery-beat-pg

Celery Beat scheduler, models, CLI and admin on **SQLModel + PostgreSQL**.
Import it as `sqlmodel_celery_beat`.

## Install
pip install sqlmodel-celery-beat-pg
pip install 'sqlmodel-celery-beat-pg[admin]'   # admin UI

## Quick start

```python
from celery import Celery
from sqlmodel_celery_beat import configure

app = Celery("app", broker="redis://localhost")
configure(dburi="postgresql+psycopg://user:pass@db/beat").apply_to_celery(app)
```

```bash
scb migrate --dburi postgresql+psycopg://user:pass@db/beat
celery -A app beat -S sqlmodel_celery_beat.schedulers:DatabaseScheduler -l info
```

### Windows / PowerShell

`scb` is a built-in alias for `Set-Clipboard` in PowerShell. Any of these work:

    sbeat --help                 # alias-free name
    scb.exe --help               # force the file, bypasses the alias
    Remove-Item Alias:scb        # remove for the current session