"""ORM model: notification settings — a single-row store for alert destinations.

Unlike the other integrations (driven by env/config), these are edited from the
Settings page at runtime, so they need a persistence layer. One row holds them.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamped, UUIDPk


class NotificationSettings(Base, UUIDPk, Timestamped):
    __tablename__ = "notification_settings"

    # Where to deliver "minutes ready" / "bot couldn't join" alerts. Null = unset.
    slack_webhook_url: Mapped[str | None] = mapped_column(String, nullable=True)
    notification_email: Mapped[str | None] = mapped_column(String, nullable=True)
