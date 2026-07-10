"""ORM model: google_oauth_credentials — connected Google accounts, by purpose.

Stores the long-lived refresh token from the per-user OAuth flow (no Workspace
admin needed). We mint short-lived access tokens from it on demand. One row per
purpose: "calendar" (the organizer's calendar → attendee emails from events) and
"bot" (the bot's own account → Meet participant list + People API email lookup).
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamped, UUIDPk


class GoogleOAuthCredential(Base, UUIDPk, Timestamped):
    __tablename__ = "google_oauth_credentials"

    # The Google account that granted access. Not unique: the same account may be
    # connected for both purposes; exchange_code keeps one row per purpose.
    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # What this connection is used for: "calendar" or "bot".
    purpose: Mapped[str] = mapped_column(
        String, nullable=False, default="calendar", server_default="calendar", index=True
    )
