from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AgeGroup, Gender


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        Index("ix_profiles_country_gender_age", "country_id", "gender", "age"),
        Index("ix_profiles_country_age_group", "country_id", "age_group"),
        Index("ix_profiles_gender_age", "gender", "age"),
        Index("ix_profiles_created_at_id", "created_at", "id"),
    )

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
