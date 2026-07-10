"""notification settings table

Revision ID: 0002_notification_settings
Revises: 0001_initial
Create Date: 2026-06-25

Adds the runtime-editable notification destinations (Slack webhook + email) used
by the Settings page. The baseline (0001) creates all tables registered on the
metadata via create_all, so a fresh database already has this table — hence the
checkfirst guard makes this a no-op there and a real create on existing DBs.
"""

from alembic import op

from app.models.notification import NotificationSettings

revision = "0002_notification_settings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    NotificationSettings.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    NotificationSettings.__table__.drop(bind=op.get_bind(), checkfirst=True)
