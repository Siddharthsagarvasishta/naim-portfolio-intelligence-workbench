"""SQLAlchemy models for durable mutable workflow state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base shared by local SQLite and optional PostgreSQL profiles."""


class WorkflowObject(Base):
    """Current materialized state for one governed business object."""

    __tablename__ = "workflow_object"
    __table_args__ = (
        UniqueConstraint("object_type", "external_id", name="uq_workflow_object_type_id"),
        Index("ix_workflow_object_type_deleted", "object_type", "deleted_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    approval_state: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    modified_by: Mapped[str] = mapped_column(String(128), nullable=False)

    versions: Mapped[list[WorkflowObjectVersion]] = relationship(
        back_populates="workflow_object",
        cascade="all, delete-orphan",
        order_by="WorkflowObjectVersion.version",
    )


class WorkflowObjectVersion(Base):
    """Append-only version history for a workflow object."""

    __tablename__ = "workflow_object_version"
    __table_args__ = (UniqueConstraint("object_id", "version", name="uq_workflow_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    object_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_object.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    approval_state: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    workflow_object: Mapped[WorkflowObject] = relationship(back_populates="versions")


class AuditEvent(Base):
    """Hash-chained append-only audit event."""

    __tablename__ = "audit_event"
    __table_args__ = (Index("ix_audit_object_time", "object_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    object_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_object.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)


class UserAccount(Base):
    """Local demonstration identity; passwords are stored only as modern hashes."""

    __tablename__ = "user_account"

    username: Mapped[str] = mapped_column(String(128), primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class RevokedToken(Base):
    """Explicitly logged-out access token identifier."""

    __tablename__ = "revoked_token"

    token_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
