from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.strategy import validate_strategy_keys


class ProductBase(BaseModel):
    manager_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=255)
    product_type: str | None = Field(default=None, max_length=100)
    established_date: date | None = None
    strategy_keys: list[str] = Field(default_factory=list)

    @field_validator("strategy_keys")
    @classmethod
    def valid_strategy_keys(cls, value: list[str]) -> list[str]:
        return validate_strategy_keys(value)


class ProductCreate(ProductBase):
    pass


class ProductBatchItem(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    established_date: date | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()


class ProductBatchCreate(BaseModel):
    manager_id: int = Field(gt=0)
    product_type: str | None = Field(default=None, max_length=100)
    strategy_keys: list[str] = Field(min_length=1)
    products: list[ProductBatchItem] = Field(min_length=1, max_length=100)

    @field_validator("strategy_keys")
    @classmethod
    def valid_strategy_keys(cls, value: list[str]) -> list[str]:
        return validate_strategy_keys(value)

    @model_validator(mode="after")
    def unique_product_names(self):
        names = [item.name for item in self.products]
        if len(names) != len(set(names)):
            raise ValueError("批量产品名称不能重复")
        return self


class ProductUpdate(BaseModel):
    manager_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    product_type: str | None = Field(default=None, max_length=100)
    established_date: date | None = None
    strategy_keys: list[str] | None = None

    @field_validator("strategy_keys")
    @classmethod
    def valid_strategy_keys(cls, value: list[str] | None) -> list[str] | None:
        return validate_strategy_keys(value) if value is not None else None


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
