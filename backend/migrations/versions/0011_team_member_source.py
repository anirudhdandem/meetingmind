"""team_members.source: distinguish auto-learned members from manual entries

Revision ID: 0011_team_member_source
Revises: 0010_google_oauth
Create Date: 2026-07-02

The company is too large to register every employee by hand, so the roster now
self-learns: the call processor auto-adds speakers the LLM classified as internal
with high confidence (source="auto"). Existing rows were all hand-entered ("manual").
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_team_member_source"
down_revision = "0010_google_oauth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "team_members",
        sa.Column("source", sa.String(), server_default="manual", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("team_members", "source")
