from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DeletionRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=500)


class DeletionRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int
    display_name: str
    reason: str
    snapshot: dict[str, Any]
    deleted_at: datetime
