from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from utils import AgeGroup


class ProfileCreate(BaseModel):
    name: str


class Profile(ProfileCreate):
    id: UUID | None = None
    gender: str
    gender_probability: Decimal = Field(decimal_places=2, le=1, ge=0)
    sample_size: int
    age: int
    age_group: AgeGroup
    country_id: str
    country_probability: Decimal = Field(decimal_places=2, le=1, ge=0)
    created_at: datetime | None = None


class ProfileResponse(Profile):
    model_config = ConfigDict(from_attributes=True)
