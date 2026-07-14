"""add calendar_events: meetings discovered on the bot's calendar for auto-join

Revision ID: 0017_calendar_events
Revises: 0016_password_reset
Create Date: 2026-07-13

Users already invite the bot's email to their meetings (that's how it gets
auto-admitted), which puts every meeting on the bot account's own Google
Calendar. The auto-join poller mirrors upcoming events into this table and
launches a bot when each one starts — the unique google_event_id is what makes
"join each meeting exactly once" survive poll ticks and server restarts.
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_calendar_events"
down_revision = "0016_password_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("google_event_id", sa.String(), nullable=False),
        sa.Column("meet_code", sa.String(), nullable=False),
        sa.Column("meeting_url", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("organizer_email", sa.String(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column(
            "call_id", sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("calls.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index(
        "ix_calendar_events_google_event_id",
        "calendar_events", ["google_event_id"], unique=True,
    )
    op.create_index("ix_calendar_events_meet_code", "calendar_events", ["meet_code"])
    op.create_index("ix_calendar_events_start_at", "calendar_events", ["start_at"])
    op.create_index("ix_calendar_events_status", "calendar_events", ["status"])


def downgrade() -> None:
    op.drop_index("ix_calendar_events_status", table_name="calendar_events")
    op.drop_index("ix_calendar_events_start_at", table_name="calendar_events")
    op.drop_index("ix_calendar_events_meet_code", table_name="calendar_events")
    op.drop_index("ix_calendar_events_google_event_id", table_name="calendar_events")
    op.drop_table("calendar_events")
