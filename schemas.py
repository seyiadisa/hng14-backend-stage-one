from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from utils import AgeGroup


class Profile(BaseModel):
    id: UUID
    name: str
    gender: str
    gender_probability: Decimal = Field(decimal_places=2, le=1, ge=0)
    sample_size: int
    age: int
    age_group: AgeGroup
    country_id: str
    country_probability: Decimal = Field(decimal_places=2, le=1, ge=0)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class ProfileListItem(BaseModel):
    id: UUID
    name: str
    gender: str
    age: int
    age_group: AgeGroup
    country_id: str

    model_config = ConfigDict(from_attributes=True)
