from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AgeGroup, Gender


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.uuidv7())
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
    country_id: Mapped[str] = mapped_column(String(2), index=True)
    country_name: Mapped[str]
    country_probability: Mapped[Decimal] = mapped_column(
        Numeric(precision=3, scale=2),
        CheckConstraint(
            "country_probability >= 0 AND country_probability <= 1",
            name="country_probability_range",
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)"),
    )
