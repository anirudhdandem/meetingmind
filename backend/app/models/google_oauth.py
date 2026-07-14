"""ORM model: google_oauth_credentials — connected Google accounts, by purpose.

Stores the long-lived refresh token from the per-user OAuth flow (no Workspace
admin needed). We mint short-lived access tokens from it on demand. Scoping
differs by purpose: "bot" (the bot's own account → Meet participant list +
People API email lookup) is one app-wide row with user_id NULL, while
"calendar" is one row PER app user — each teammate connects their own calendar
and the auto-join poller sweeps all of them.
"""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamped, UUIDPk


class GoogleOAuthCredential(Base, UUIDPk, Timestamped):
    __tablename__ = "google_oauth_credentials"

    # The Google account that granted access. Not unique: the same account may be
    # connected for both purposes; exchange_code keeps one row per purpose scope.
    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # What this connection is used for: "calendar" or "bot".
    purpose: Mapped[str] = mapped_column(
        String, nullable=False, default="calendar", server_default="calendar", index=True
    )
    # The app user who owns this connection. NULL for the app-wide bot account;
    # set for per-user calendar connections (deleting the user deletes them).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
