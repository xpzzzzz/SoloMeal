from uuid import uuid4

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


def new_id() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class UserPreference(Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    equipment: Mapped[list[str]] = mapped_column(JSON, default=list)
    excluded_ingredients: Mapped[list[str]] = mapped_column(JSON, default=list)
    default_servings: Mapped[int] = mapped_column(Integer, default=1)
    max_minutes: Mapped[int] = mapped_column(Integer, default=30)
    # Stored on the server, not in the browser, so another device cannot silently re-open it.
    personal_time_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    personalization_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
