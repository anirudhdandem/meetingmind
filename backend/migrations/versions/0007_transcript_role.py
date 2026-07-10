"""add role (internal/client) to call_transcripts; merge migration heads

Revision ID: 0007_transcript_role
Revises: 0006_mom_coaching, 0002_notification_settings
Create Date: 2026-07-02

Phase 1 of performance metrics: each transcript segment gets a `role`
("internal" = our team, "client", or "unknown") so downstream metrics (talk-time
per side, per-side coaching) can split the conversation. Roles are assigned in
call_processor by matching the resolved speaker name to the meeting's calendar
attendees (see app.services.participant_roles).

This revision also MERGES the two dangling heads that existed before it
(0006_mom_coaching on the main chain, and the orphaned 0002_notification_settings
branch) so `alembic upgrade head` resolves to a single head again.
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_transcript_role"
down_revision = ("0006_mom_coaching", "0002_notification_settings")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("call_transcripts", sa.Column("role", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("call_transcripts", "role")
