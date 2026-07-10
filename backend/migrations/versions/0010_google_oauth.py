"""add google_oauth_credentials: per-user calendar connection tokens

Revision ID: 0010_google_oauth
Revises: 0009_team_members
Create Date: 2026-07-02

Stores the refresh token from the per-user Google OAuth flow so we can read a
meeting's calendar attendees (emails) and classify sides by domain — without any
Workspace admin / domain-wide delegation.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_google_oauth"
down_revision = "0009_team_members"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_oauth_credentials",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_google_oauth_credentials_email", "google_oauth_credentials", ["email"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_google_oauth_credentials_email", table_name="google_oauth_credentials")
    op.drop_table("google_oauth_credentials")
