from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ManagerBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    unified_social_credit_code: str | None = Field(default=None, max_length=18)
    contact_name: str | None = Field(default=None, max_length=100)
    contact_phone: str | None = Field(default=None, max_length=100)


class ManagerCreate(ManagerBase):
    pass


class ManagerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    unified_social_credit_code: str | None = Field(default=None, max_length=18)
    contact_name: str | None = Field(default=None, max_length=100)
    contact_phone: str | None = Field(default=None, max_length=100)


class ManagerRead(ManagerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
