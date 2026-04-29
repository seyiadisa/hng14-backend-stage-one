from uuid import UUID
from sqlalchemy import Enum, DateTime, text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import Role


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, index=True, server_default=func.uuidv7()
    )
    github_id: Mapped[str] = mapped_column(unique=True, index=True)
    username: Mapped[str] = mapped_column(unique=True)
    email: Mapped[str] = mapped_column(unique=True)
    avatar_url: Mapped[str]
    role: Mapped[Role] = mapped_column(
        Enum(Role), server_default=text(f"'{Role.analyst.value}'")
    )
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    last_login_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(
        DateTime(timezone=True),
        server_default=text("TIMEZONE('utc', CURRENT_TIMESTAMP)"),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(
        primary_key=True, index=True, server_default=func.uuidv7()
    )
    user_id: Mapped[UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at = mapped_column(DateTime(timezone=True))
