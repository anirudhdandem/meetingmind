"""API schemas for the internal-team roster."""

import datetime
import uuid

from pydantic import BaseModel, ConfigDict


class TeamMemberCreate(BaseModel):
    name: str
    email: str | None = None


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    email: str | None
    active: bool
    # "manual" (added in Settings) or "auto" (learned from a call's side analysis).
    source: str
    created_at: datetime.datetime
