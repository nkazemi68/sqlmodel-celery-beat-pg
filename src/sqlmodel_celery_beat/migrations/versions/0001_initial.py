"""initial

Revision ID: 0001
Revises:
Create Date: 2025-01-01
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "celery_interval_schedule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("every", sa.Integer(), nullable=False),
        sa.Column("period", sa.Enum("DAYS", "HOURS", "MINUTES", "SECONDS", "MICROSECONDS",
                                    name="period"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("every", "period", name="uq_interval_every_period"),
    )
    op.create_table(
        "celery_crontab_schedule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("minute", sa.String(240), nullable=False),
        sa.Column("hour", sa.String(96), nullable=False),
        sa.Column("day_of_week", sa.String(64), nullable=False),
        sa.Column("day_of_month", sa.String(124), nullable=False),
        sa.Column("month_of_year", sa.String(64), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "celery_solar_schedule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "celery_clocked_schedule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clocked_time", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "celery_periodic_task",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("task", sa.String(255), nullable=False),
        sa.Column("args", sa.String(1024), nullable=False),
        sa.Column("kwargs", sa.String(1024), nullable=False),
        sa.Column("queue", sa.String(255), nullable=True),
        sa.Column("exchange", sa.String(255), nullable=True),
        sa.Column("routing_key", sa.String(255), nullable=True),
        sa.Column("headers", sa.String(1024), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_run_count", sa.Integer(), nullable=False),
        sa.Column("date_changed", sa.DateTime(timezone=True), nullable=False),
        sa.Column("discriminator", sa.String(32), nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_periodic_task_discriminator_schedule",
                    "celery_periodic_task", ["discriminator", "schedule_id"])
    op.create_table(
        "celery_periodic_task_changed",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("last_update", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

def downgrade() -> None:
    op.drop_table("celery_periodic_task_changed")
    op.drop_index("ix_periodic_task_discriminator_schedule", table_name="celery_periodic_task")
    op.drop_table("celery_periodic_task")
    op.drop_table("celery_clocked_schedule")
    op.drop_table("celery_solar_schedule")
    op.drop_table("celery_crontab_schedule")
    op.drop_table("celery_interval_schedule")
    op.execute("DROP TYPE IF EXISTS period")