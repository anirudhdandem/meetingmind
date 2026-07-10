"""google_oauth_credentials.purpose: separate calendar vs bot connections

Revision ID: 0012_oauth_purpose
Revises: 0011_team_member_source
Create Date: 2026-07-02

The bot's own Google account now also connects via OAuth ("bot" purpose) so we can
read each finished meeting's participant list (Meet REST API) and resolve signed-in
participants to emails (People API) — the deterministic internal-vs-client source.
Email uniqueness is dropped (the same account may serve both purposes); the app
keeps one row per purpose instead.
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_oauth_purpose"
down_revision = "0011_team_member_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "google_oauth_credentials",
        sa.Column("purpose", sa.String(), server_default="calendar", nullable=False),
    )
    op.create_index(
        "ix_google_oauth_credentials_purpose", "google_oauth_credentials", ["purpose"]
    )
    op.drop_index("ix_google_oauth_credentials_email", table_name="google_oauth_credentials")
    op.create_index("ix_google_oauth_credentials_email", "google_oauth_credentials", ["email"])


def downgrade() -> None:
    op.drop_index("ix_google_oauth_credentials_email", table_name="google_oauth_credentials")
    op.create_index(
        "ix_google_oauth_credentials_email", "google_oauth_credentials", ["email"], unique=True
    )
    op.drop_index("ix_google_oauth_credentials_purpose", table_name="google_oauth_credentials")
    op.drop_column("google_oauth_credentials", "purpose")
