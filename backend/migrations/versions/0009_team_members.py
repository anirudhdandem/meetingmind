"""add team_members: internal-team roster for role classification

Revision ID: 0009_team_members
Revises: 0008_call_metrics
Create Date: 2026-07-02

Names of our own team, managed in-app. Speakers matching an active member are
classified "internal"; other named speakers are the "client". No Google admin
needed — this replaces the calendar/email approach for role attribution.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_team_members"
down_revision = "0008_call_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_members",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("team_members")
