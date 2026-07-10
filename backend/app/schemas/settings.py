"""API schemas for editable settings (notification destinations)."""

from pydantic import BaseModel, ConfigDict


class NotificationSettingsIn(BaseModel):
    slack_webhook_url: str | None = None
    notification_email: str | None = None


class NotificationSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    slack_webhook_url: str | None
    notification_email: str | None
