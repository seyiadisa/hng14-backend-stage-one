from uuid import uuid7, UUID
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, Enum, Numeric, String
from sqlalchemy.orm import mapped_column, Mapped

from db import Base
from enums import AgeGroup, Gender


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(nullable=False, index=True, unique=True)
    gender: Mapped[str] = mapped_column(Enum(Gender))
    gender_probability: Mapped[Decimal] = mapped_column(
        Numeric(precision=3, scale=2),
        CheckConstraint(
            "gender_probability >= 0 AND gender_probability <= 1",
            name="gender_probability_range",
        ),
    )
    age: Mapped[int]
    age_group: Mapped[str] = mapped_column(Enum(AgeGroup))
    country_id: Mapped[str] = mapped_column(String(2))
    country_name: Mapped[str]
    country_probability: Mapped[Decimal] = mapped_column(
        Numeric(precision=3, scale=2),
        CheckConstraint(
            "country_probability >= 0 AND country_probability <= 1",
            name="country_probability_range",
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
