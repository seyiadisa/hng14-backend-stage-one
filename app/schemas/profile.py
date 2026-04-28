from typing import Literal
from typing_extensions import Self
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.models.enums import AgeGroup, Gender


class Profile(BaseModel):
    id: UUID
    name: str
    gender: str
    gender_probability: Decimal = Field(decimal_places=2, le=1, ge=0)
    # sample_size: int
    age: int
    age_group: AgeGroup
    country_id: str
    country_probability: Decimal = Field(decimal_places=2, le=1, ge=0)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class ProfileCreate(BaseModel):
    name: str


class ProfileListItem(Profile):
    pass


class ProfileListQueryParams(BaseModel):
    gender: Gender | None = None
    age_group: AgeGroup | None = None
    country_id: str | None = Field(default=None, min_length=2, max_length=2)
    min_age: int | None = Field(default=None, ge=1)
    max_age: int | None = Field(default=None, ge=1)
    min_gender_probability: Decimal | None = Field(
        default=None, decimal_places=2, le=1, ge=0
    )
    min_country_probability: Decimal | None = Field(
        default=None, decimal_places=2, le=1, ge=0
    )
    order: Literal["asc", "desc"] | None = Field(default=None)
    sort_by: Literal["age", "created_at", "gender_probability"] | None = Field(
        default=None
    )
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def validate_age_range(self) -> Self:
        min_age = self.min_age
        max_age = self.max_age
        if min_age is not None and max_age is not None and min_age > max_age:
            raise ValueError("min_age cannot be greater than max_age")
        return self

    @model_validator(mode="after")
    def validate_sorting(self) -> Self:
        if self.order is not None and self.sort_by is None:
            raise ValueError("order must be provided with sort_by")
        return self


class ProfileSearchQueryParams(BaseModel):
    q: str | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=50)
