from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(24), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    sessions: Mapped[list["SessionModel"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), default="New Project")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[UserModel] = relationship(back_populates="sessions")
    messages: Mapped[list["SessionMessageModel"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionMessageModel.sequence",
    )
    runtime_state: Mapped["SessionRuntimeStateModel | None"] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        uselist=False,
    )
    publish_state: Mapped["SessionPublishStateModel | None"] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        uselist=False,
    )


class SessionMessageModel(Base):
    __tablename__ = "session_messages"
    __table_args__ = (UniqueConstraint("session_id", "sequence", name="uq_session_message_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(24))
    content: Mapped[str] = mapped_column(Text)
    reasoning_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_calls_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    session: Mapped[SessionModel] = relationship(back_populates="messages")


class SessionRuntimeStateModel(Base):
    __tablename__ = "session_runtime_state"

    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)
    workspace_files_json: Mapped[str] = mapped_column(Text)
    active_turn_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_frontend_tool_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_compile_feedback_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    session: Mapped[SessionModel] = relationship(back_populates="runtime_state")


class SessionPublishStateModel(Base):
    __tablename__ = "session_publish_state"

    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), default="idle")
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    public_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    build_log: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    session: Mapped[SessionModel] = relationship(back_populates="publish_state")
