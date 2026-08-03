from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.notification import NotificationStatus


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: int
    generation_job_id: int | None
    status: NotificationStatus
    filename: str
    manager_name: str
    product_name: str
    report_date: str
    download_url: str | None
    attempt_count: int
    max_attempts: int
    last_error: str | None
    response_status: int | None
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None


class NotificationConfigRead(BaseModel):
    enabled: bool
    ready: bool
    missing_settings: list[str]
    gateway_host: str | None
    recipient_configured: bool
    payload_template_configured: bool
