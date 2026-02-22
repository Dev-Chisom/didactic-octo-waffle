"""script scenes (scene-based video pipeline)

Revision ID: 003
Revises: 002
Create Date: 2026-02-22

Stores structured scenes per script for FacelessReels-style pipeline:
one image + one voice segment per scene, then concat with Ken Burns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scripts",
        sa.Column("scenes", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scripts", "scenes")
