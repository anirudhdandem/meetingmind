"""add points_discussed + action_items to moms (MOM template)

Revision ID: 0002_mom_template
Revises: 0001_initial
Create Date: 2026-06-18

Adds the two core MOM-template columns so minutes follow:
attendees -> points_discussed -> action_items.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_mom_template"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("moms", sa.Column("points_discussed", JSONB, nullable=True))
    op.add_column("moms", sa.Column("action_items", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("moms", "action_items")
    op.drop_column("moms", "points_discussed")
