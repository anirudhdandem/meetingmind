"""Per-user meeting visibility: record who a call/event belongs to

Revision ID: 0019_call_ownership
Revises: 0018_per_user_calendar
Create Date: 2026-07-16

Every dashboard used to show every teammate's meetings because nothing recorded
ownership: calls had no creator and calendar_events discarded the attendee list.
Now manual calls stamp the user who started them (created_by_user_id) and the
calendar sweep stores the event's attendee/organizer emails (attendee_emails),
so the API can scope lists to "meetings you were part of".

Existing rows keep NULLs and stay visible to everyone — there is no ownership
to backfill, and hiding historical meetings from the whole team would be worse
than the status quo.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_call_ownership"
down_revision = "0018_per_user_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calls",
        sa.Column(
            "created_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index("ix_calls_created_by_user_id", "calls", ["created_by_user_id"])
    op.add_column(
        "calendar_events",
        sa.Column("attendee_emails", sa.dialects.postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("calendar_events", "attendee_emails")
    op.drop_index("ix_calls_created_by_user_id", table_name="calls")
    op.drop_column("calls", "created_by_user_id")
