"""add participants (Meet roster names) to calls

Revision ID: 0003_call_participants
Revises: 0002_mom_template
Create Date: 2026-06-18

Stores the real participant names read from the Meet roster, used as MOM attendees.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_call_participants"
down_revision = "0002_mom_template"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("participants", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("calls", "participants")
