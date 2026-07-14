"""google_oauth_credentials.user_id: one calendar connection per app user

Revision ID: 0018_per_user_calendar
Revises: 0017_calendar_events
Create Date: 2026-07-14

"Connect Google Calendar" used to be one app-wide slot — teammate B connecting
replaced teammate A. Now each user owns their own calendar credential (user_id),
and the auto-join poller sweeps every connected calendar. The bot connection
stays app-wide (user_id NULL).

Existing calendar-purpose rows are deleted rather than migrated: they have no
owner to assign, and the OAuth client swap already invalidated their refresh
tokens — reconnecting is required either way.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_per_user_calendar"
down_revision = "0017_calendar_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "google_oauth_credentials",
        sa.Column(
            "user_id", sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True,
        ),
    )
    op.create_index(
        "ix_google_oauth_credentials_user_id", "google_oauth_credentials", ["user_id"]
    )
    op.execute("DELETE FROM google_oauth_credentials WHERE purpose = 'calendar'")


def downgrade() -> None:
    op.drop_index(
        "ix_google_oauth_credentials_user_id", table_name="google_oauth_credentials"
    )
    op.drop_column("google_oauth_credentials", "user_id")
