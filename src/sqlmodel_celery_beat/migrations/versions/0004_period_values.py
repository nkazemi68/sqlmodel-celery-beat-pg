"""convert period enum storage from names to values

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE period_new AS ENUM "
        "('days','hours','minutes','seconds','microseconds')"
    )
    op.execute(
        "ALTER TABLE celery_interval_schedule "
        "ALTER COLUMN period TYPE period_new "
        "USING LOWER(period::text)::period_new"
    )
    op.execute("DROP TYPE period")
    op.execute("ALTER TYPE period_new RENAME TO period")


def downgrade() -> None:
    op.execute(
        "CREATE TYPE period_old AS ENUM "
        "('DAYS','HOURS','MINUTES','SECONDS','MICROSECONDS')"
    )
    op.execute(
        "ALTER TABLE celery_interval_schedule "
        "ALTER COLUMN period TYPE period_old "
        "USING UPPER(period::text)::period_old"
    )
    op.execute("DROP TYPE period")
    op.execute("ALTER TYPE period_old RENAME TO period")