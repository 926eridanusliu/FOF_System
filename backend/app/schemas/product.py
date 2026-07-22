from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    manager_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=255)
    product_type: str | None = Field(default=None, max_length=100)
    established_date: date | None = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    manager_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    product_type: str | None = Field(default=None, max_length=100)
    established_date: date | None = None


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
