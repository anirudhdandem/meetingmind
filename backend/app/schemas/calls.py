"""API schemas for companies, calls, transcripts."""

import datetime
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.call import CallStatus, MeetingPlatform


class CompanyCreate(BaseModel):
    name: str
    segment: str | None = None
    kind: str = "external"
    presented_by: str | None = None
    product_pitched: str | None = None


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    segment: str | None
    kind: str = "external"
    # Who on our team led the pitch, and what was pitched (user-entered).
    presented_by: str | None = None
    product_pitched: str | None = None
    created_at: datetime.datetime


class AssignCompany(BaseModel):
    """Re-file a call under a company (external) or an internal-meeting label.

    Sent from the post-summary prompt: the user names who the meeting was with,
    or marks it internal and gives it a memorable label. presented_by /
    product_pitched are asked in the same dialog and stored on the company;
    omitted (None) fields leave existing values untouched.
    """

    name: str
    kind: str = "external"  # "external" | "internal"
    segment: str | None = None
    presented_by: str | None = None
    product_pitched: str | None = None


class CallStart(BaseModel):
    """Paste a meeting URL and go — the bot is created and launched in one call."""

    meeting_url: str
    company_name: str | None = None
    meeting_platform: MeetingPlatform = MeetingPlatform.meet


class CallCreate(BaseModel):
    company_id: uuid.UUID
    meeting_url: str
    meeting_platform: MeetingPlatform = MeetingPlatform.meet
    sales_rep_id: uuid.UUID | None = None
    scheduled_at: datetime.datetime | None = None


class CallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID
    sales_rep_id: uuid.UUID | None
    meeting_platform: MeetingPlatform
    meeting_url: str | None
    livekit_room: str | None
    # Real participant names read from the Meet roster (MOM attendees source).
    participants: list | None
    status: CallStatus
    scheduled_at: datetime.datetime | None
    started_at: datetime.datetime | None
    ended_at: datetime.datetime | None
    created_at: datetime.datetime


class TranscriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    speaker_label: str | None
    # "internal" (our team) | "client" | "unknown" | null (not yet computed)
    role: str | None = None
    text: str
    start_ts: float
    end_ts: float
    confidence: float | None
