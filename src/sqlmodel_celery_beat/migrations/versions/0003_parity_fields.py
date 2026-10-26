"""parity fields: text columns, start_time, expire_seconds, description

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "celery_periodic_task", "args",
        existing_type=sa.String(1024), type_=sa.Text(), existing_nullable=False,
    )
    op.alter_column(
        "celery_periodic_task", "kwargs",
        existing_type=sa.String(1024), type_=sa.Text(), existing_nullable=False,
    )
    op.alter_column(
        "celery_periodic_task", "headers",
        existing_type=sa.String(1024), type_=sa.Text(), existing_nullable=False,
    )
    op.add_column(
        "celery_periodic_task",
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "celery_periodic_task",
        sa.Column("expire_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "celery_periodic_task",
        sa.Column("description", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("celery_periodic_task", "description")
    op.drop_column("celery_periodic_task", "expire_seconds")
    op.drop_column("celery_periodic_task", "start_time")
    op.alter_column(
        "celery_periodic_task", "headers",
        existing_type=sa.Text(), type_=sa.String(1024), existing_nullable=False,
    )
    op.alter_column(
        "celery_periodic_task", "kwargs",
        existing_type=sa.Text(), type_=sa.String(1024), existing_nullable=False,
    )
    op.alter_column(
        "celery_periodic_task", "args",
        existing_type=sa.Text(), type_=sa.String(1024), existing_nullable=False,
    )