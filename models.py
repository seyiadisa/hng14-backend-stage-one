from uuid import uuid7, UUID
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import Numeric, CheckConstraint, Enum
from sqlalchemy.orm import mapped_column, Mapped

from db import Base
from utils import AgeGroup


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(nullable=False, index=True, unique=True)
    gender: Mapped[str]
    gender_probability: Mapped[Decimal] = mapped_column(
        Numeric(precision=3, scale=2),
        CheckConstraint(
            "gender_probability >= 0 AND gender_probability <= 1",
            name="gender_probability_range",
        ),
    )
    sample_size: Mapped[int]
    age: Mapped[int]
    age_group: Mapped[str] = mapped_column(Enum(AgeGroup), name="age_group_enum")
    country_id: Mapped[str]
    country_probability: Mapped[Decimal] = mapped_column(
        Numeric(precision=3, scale=2),
        CheckConstraint(
            "country_probability >= 0 AND country_probability <= 1",
            name="country_probability_range",
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.now(timezone.utc)
    )
