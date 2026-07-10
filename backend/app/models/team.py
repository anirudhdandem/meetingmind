"""ORM model: team_members — our internal-team roster.

Used to split speakers into "our team" vs "the client" without any Google Workspace
admin access: a speaker whose resolved name matches an active roster member is
internal. The company is too large to register everyone by hand, so the roster is
SELF-LEARNING from evidence: rows are added manually in Settings (source="manual"),
from email-verified Meet participants on our domain (source="meet"), and from
attendees of user-declared internal meetings (source="auto"). Never from LLM guesses.
"""

from sqlalchemy import Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamped, UUIDPk


class TeamMember(Base, UUIDPk, Timestamped):
    __tablename__ = "team_members"

    # Display name as it appears in the meeting (used for matching, case/space-insensitive).
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Optional, for reference only (e.g. the person's @company address).
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    # Soft on/off so a former member can be excluded without deleting history.
    # Deactivating an auto-added row also blocks it from being re-added.
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # "manual" = added in Settings; "meet" = email-verified Meet participant on our
    # domain; "auto" = attendee of a user-declared internal meeting.
    source: Mapped[str] = mapped_column(
        String, nullable=False, default="manual", server_default="manual"
    )
