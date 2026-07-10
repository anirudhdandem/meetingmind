"""add went_well / to_improve coaching to moms

Revision ID: 0006_mom_coaching
Revises: 0005_company_kind
Create Date: 2026-06-24

Stores what went well and what could be improved in the meeting — the
"analyze what went good and what not" signal surfaced on the call page.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_mom_coaching"
down_revision = "0005_company_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("moms", sa.Column("went_well", JSONB, nullable=True))
    op.add_column("moms", sa.Column("to_improve", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("moms", "to_improve")
    op.drop_column("moms", "went_well")
