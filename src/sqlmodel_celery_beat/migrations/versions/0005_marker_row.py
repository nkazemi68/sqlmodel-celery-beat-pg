"""normalize celery_periodic_task_changed to a single row (id = 1)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Collapse multiple marker rows to the most recent one
    op.execute(
        """
        DELETE FROM celery_periodic_task_changed
        WHERE id NOT IN (
            SELECT id FROM celery_periodic_task_changed
            ORDER BY last_update DESC LIMIT 1
        )
        """
    )
    # Rename the surviving row to id = 1
    op.execute(
        "UPDATE celery_periodic_task_changed SET id = 1 WHERE id != 1"
    )
    # Guarantee the row exists
    op.execute(
        """
        INSERT INTO celery_periodic_task_changed (id, last_update)
        SELECT 1, NOW()
        WHERE NOT EXISTS (SELECT 1 FROM celery_periodic_task_changed)
        """
    )


def downgrade() -> None:
    # Marker row semantics are non-destructive; nothing to undo.
    pass