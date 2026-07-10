"""add per-attendee contributions to moms

Revision ID: 0004_mom_contributions
Revises: 0003_call_participants
Create Date: 2026-06-23

Stores [{name, summary}] — who said what in the meeting, by real attendee name.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_mom_contributions"
down_revision = "0003_call_participants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("moms", sa.Column("contributions", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("moms", "contributions")
