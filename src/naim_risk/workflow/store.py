"""Transactional versioned state store for mutable nAIM workflow objects."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from naim_risk.workflow.models import AuditEvent, WorkflowObject, WorkflowObjectVersion

ALLOWED_OBJECT_TYPES = {
    "investigation",
    "investigation_note",
    "basket",
    "basket_membership",
    "workspace",
    "workspace_version",
    "approval",
    "commentary",
    "export_job",
    "scenario_run",
    "rating_methodology",
    "configuration_change",
    "alert",
}
APPROVAL_STATES = {"DRAFT", "PENDING", "APPROVED", "REJECTED", "WITHDRAWN"}
_AUDIT_PREVIOUS_UNSET = object()


class WorkflowStoreError(RuntimeError):
    """Base class for workflow-store errors."""


class ObjectNotFound(WorkflowStoreError):
    """Raised when an object is missing or soft-deleted."""


class DuplicateObject(WorkflowStoreError):
    """Raised when an object type/external-id pair already exists."""


class ConcurrencyConflict(WorkflowStoreError):
    """Raised when an update uses a stale expected version."""


def default_database_url(repository_root: Path) -> str:
    state_path = (repository_root / "data" / "state" / "naim_workflow.sqlite3").resolve()
    return f"sqlite+pysqlite:///{state_path}"


def database_url_from_environment(repository_root: Path) -> str:
    """Resolve SQLite by default and accept a production-style PostgreSQL URL."""

    return os.getenv("NAIM_DATABASE_URL", default_database_url(repository_root))


def _json_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(dict(value), sort_keys=True, default=str))
    except (TypeError, ValueError) as exc:
        raise ValueError("Workflow state must be JSON serializable") from exc


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


class WorkflowStore:
    """SQLAlchemy-backed store with versions, soft deletion and audit chaining."""

    def __init__(self, database_url: str, *, initialize: bool = True) -> None:
        self.database_url = database_url
        url = make_url(database_url)
        connect_args: dict[str, Any] = {}
        if url.get_backend_name() == "sqlite":
            connect_args["check_same_thread"] = False
            if url.database and url.database != ":memory:":
                Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(
            database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            class_=Session,
        )
        if initialize:
            self.initialize_schema()

    def initialize_schema(self) -> None:
        """Initialise schema through the governed migration path.

        SQLite memory databases remain a deliberately isolated test-only exception because an
        Alembic command would connect to a different ephemeral database.  File-backed databases
        are inspected and migrated (or refused) by the same fail-closed bootstrap used by the
        command line.
        """

        from naim_risk.workflow.migrations import ensure_database_ready

        ensure_database_ready(self.database_url, engine=self.engine)

    def close(self) -> None:
        self.engine.dispose()

    @staticmethod
    def _validate_object_type(object_type: str) -> None:
        if object_type not in ALLOWED_OBJECT_TYPES:
            raise ValueError(f"Unsupported workflow object type: {object_type}")

    @staticmethod
    def _validate_approval_state(approval_state: str) -> None:
        if approval_state not in APPROVAL_STATES:
            raise ValueError(f"Unsupported approval state: {approval_state}")

    @staticmethod
    def _serialize(row: WorkflowObject) -> dict[str, Any]:
        return {
            "id": row.id,
            "object_type": row.object_type,
            "external_id": row.external_id,
            "version": row.current_version,
            "state": _json_copy(row.state),
            "approval_state": row.approval_state,
            "created_at": _utc_iso(row.created_at),
            "modified_at": _utc_iso(row.modified_at),
            "deleted_at": _utc_iso(row.deleted_at),
            "created_by": row.created_by,
            "modified_by": row.modified_by,
        }

    @staticmethod
    def _audit_event(
        session: Session,
        *,
        object_id: str | None,
        event_type: str,
        actor: str,
        payload: Mapping[str, Any],
        occurred_at: datetime,
        previous_hash_override: str | None | object = _AUDIT_PREVIOUS_UNSET,
    ) -> AuditEvent:
        if previous_hash_override is _AUDIT_PREVIOUS_UNSET:
            previous = session.scalar(
                select(AuditEvent)
                .where(AuditEvent.object_id == object_id)
                .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
                .limit(1)
            )
            previous_hash = previous.event_hash if previous else None
        else:
            previous_hash = previous_hash_override
        canonical = {
            "object_id": object_id,
            "event_type": event_type,
            "actor": actor,
            "occurred_at": occurred_at.isoformat(),
            "payload": _json_copy(payload),
            "previous_hash": previous_hash,
        }
        event_hash = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return AuditEvent(
            id=str(uuid.uuid4()),
            object_id=object_id,
            event_type=event_type,
            actor=actor,
            occurred_at=occurred_at,
            payload=canonical["payload"],
            previous_hash=previous_hash,
            event_hash=event_hash,
        )

    def create(
        self,
        object_type: str,
        external_id: str,
        state: Mapping[str, Any],
        *,
        actor: str,
        approval_state: str = "DRAFT",
        domain_events: Iterable[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self._validate_object_type(object_type)
        self._validate_approval_state(approval_state)
        if not external_id.strip():
            raise ValueError("external_id is required")
        now = datetime.now(UTC)
        state_copy = _json_copy(state)
        event_specs = [dict(event) for event in (domain_events or [])]
        if not event_specs:
            event_specs = [
                {
                    "event_type": "WORKFLOW_OBJECT_CREATED",
                    "payload": {
                        "object_type": object_type,
                        "external_id": external_id,
                    },
                }
            ]
        for event in event_specs:
            event_type = str(event.get("event_type") or "")
            if not event_type or len(event_type) > 32:
                raise ValueError("Domain event_type must contain 1 to 32 characters")
        row = WorkflowObject(
            id=str(uuid.uuid4()),
            object_type=object_type,
            external_id=external_id,
            current_version=1,
            state=state_copy,
            approval_state=approval_state,
            created_at=now,
            modified_at=now,
            created_by=actor,
            modified_by=actor,
        )
        version = WorkflowObjectVersion(
            object_id=row.id,
            version=1,
            event_type=(
                str(event_specs[0]["event_type"]) if domain_events else "CREATED"
            ),
            state=state_copy,
            approval_state=approval_state,
            actor=actor,
            created_at=now,
        )
        try:
            with self.session_factory.begin() as session:
                session.add(row)
                session.flush()
                session.add(version)
                previous_hash: str | None | object = _AUDIT_PREVIOUS_UNSET
                for index, event_spec in enumerate(event_specs):
                    audit_event = self._audit_event(
                        session,
                        object_id=row.id,
                        event_type=str(event_spec["event_type"]),
                        actor=actor,
                        payload={
                            "version": 1,
                            **dict(event_spec.get("payload") or {}),
                        },
                        occurred_at=now + timedelta(microseconds=index),
                        previous_hash_override=previous_hash,
                    )
                    session.add(audit_event)
                    previous_hash = audit_event.event_hash
        except IntegrityError as exc:
            raise DuplicateObject(f"{object_type}/{external_id} already exists") from exc
        return self._serialize(row)

    def get(
        self,
        object_type: str,
        external_id: str,
        *,
        include_deleted: bool = False,
    ) -> dict[str, Any]:
        self._validate_object_type(object_type)
        with self.session_factory() as session:
            statement = select(WorkflowObject).where(
                WorkflowObject.object_type == object_type,
                WorkflowObject.external_id == external_id,
            )
            if not include_deleted:
                statement = statement.where(WorkflowObject.deleted_at.is_(None))
            row = session.scalar(statement)
            if row is None:
                raise ObjectNotFound(f"{object_type}/{external_id} not found")
            return self._serialize(row)

    def list(
        self,
        object_type: str,
        *,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        self._validate_object_type(object_type)
        with self.session_factory() as session:
            statement = select(WorkflowObject).where(WorkflowObject.object_type == object_type)
            if not include_deleted:
                statement = statement.where(WorkflowObject.deleted_at.is_(None))
            statement = statement.order_by(WorkflowObject.created_at, WorkflowObject.external_id)
            return [self._serialize(row) for row in session.scalars(statement)]

    def update(
        self,
        object_type: str,
        external_id: str,
        changes: Mapping[str, Any],
        *,
        expected_version: int,
        actor: str,
        approval_state: str | None = None,
        replace: bool = False,
        domain_events: Iterable[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self._validate_object_type(object_type)
        if approval_state is not None:
            self._validate_approval_state(approval_state)
        with self.session_factory.begin() as session:
            row = session.scalar(
                select(WorkflowObject).where(
                    WorkflowObject.object_type == object_type,
                    WorkflowObject.external_id == external_id,
                    WorkflowObject.deleted_at.is_(None),
                )
            )
            if row is None:
                raise ObjectNotFound(f"{object_type}/{external_id} not found")
            state = (
                _json_copy(changes) if replace else {**_json_copy(row.state), **_json_copy(changes)}
            )
            event_specs = [dict(event) for event in (domain_events or [])]
            if not event_specs:
                event_specs = [
                    {
                        "event_type": "WORKFLOW_OBJECT_UPDATED",
                        "payload": {"changed_fields": sorted(changes)},
                    }
                ]
            for event in event_specs:
                event_type = str(event.get("event_type") or "")
                if not event_type or len(event_type) > 32:
                    raise ValueError("Domain event_type must contain 1 to 32 characters")
            next_version = expected_version + 1
            now = datetime.now(UTC)
            next_approval = approval_state or row.approval_state
            result = session.execute(
                update(WorkflowObject)
                .where(
                    WorkflowObject.id == row.id,
                    WorkflowObject.current_version == expected_version,
                    WorkflowObject.deleted_at.is_(None),
                )
                .values(
                    current_version=next_version,
                    state=state,
                    approval_state=next_approval,
                    modified_at=now,
                    modified_by=actor,
                )
            )
            if result.rowcount != 1:
                raise ConcurrencyConflict(
                    f"Expected {object_type}/{external_id} version {expected_version}"
                )
            session.add(
                WorkflowObjectVersion(
                    object_id=row.id,
                    version=next_version,
                    event_type=(
                        str(event_specs[0]["event_type"])
                        if domain_events
                        else "UPDATED"
                    ),
                    state=state,
                    approval_state=next_approval,
                    actor=actor,
                    created_at=now,
                )
            )
            previous_hash: str | None | object = _AUDIT_PREVIOUS_UNSET
            for index, event_spec in enumerate(event_specs):
                audit_event = self._audit_event(
                    session,
                    object_id=row.id,
                    event_type=str(event_spec["event_type"]),
                    actor=actor,
                    payload={
                        "version": next_version,
                        **dict(event_spec.get("payload") or {}),
                    },
                    occurred_at=now + timedelta(microseconds=index),
                    previous_hash_override=previous_hash,
                )
                session.add(audit_event)
                previous_hash = audit_event.event_hash
        return self.get(object_type, external_id)

    def set_approval(
        self,
        object_type: str,
        external_id: str,
        approval_state: str,
        *,
        expected_version: int,
        actor: str,
        rationale: str,
    ) -> dict[str, Any]:
        if not rationale.strip():
            raise ValueError("Approval changes require a rationale")
        return self.update(
            object_type,
            external_id,
            {"approval_rationale": rationale, "approval_actor": actor},
            expected_version=expected_version,
            actor=actor,
            approval_state=approval_state,
        )

    def soft_delete(
        self,
        object_type: str,
        external_id: str,
        *,
        expected_version: int,
        actor: str,
        reason: str,
    ) -> dict[str, Any]:
        self._validate_object_type(object_type)
        if not reason.strip():
            raise ValueError("Soft deletion requires a reason")
        with self.session_factory.begin() as session:
            row = session.scalar(
                select(WorkflowObject).where(
                    WorkflowObject.object_type == object_type,
                    WorkflowObject.external_id == external_id,
                    WorkflowObject.deleted_at.is_(None),
                )
            )
            if row is None:
                raise ObjectNotFound(f"{object_type}/{external_id} not found")
            now = datetime.now(UTC)
            next_version = expected_version + 1
            next_state = {**_json_copy(row.state), "deletion_reason": reason}
            result = session.execute(
                update(WorkflowObject)
                .where(
                    WorkflowObject.id == row.id,
                    WorkflowObject.current_version == expected_version,
                    WorkflowObject.deleted_at.is_(None),
                )
                .values(
                    current_version=next_version,
                    state=next_state,
                    modified_at=now,
                    modified_by=actor,
                    deleted_at=now,
                )
            )
            if result.rowcount != 1:
                raise ConcurrencyConflict(
                    f"Expected {object_type}/{external_id} version {expected_version}"
                )
            session.add(
                WorkflowObjectVersion(
                    object_id=row.id,
                    version=next_version,
                    event_type="SOFT_DELETED",
                    state=next_state,
                    approval_state=row.approval_state,
                    actor=actor,
                    created_at=now,
                )
            )
            session.add(
                self._audit_event(
                    session,
                    object_id=row.id,
                    event_type="WORKFLOW_OBJECT_SOFT_DELETED",
                    actor=actor,
                    payload={"version": next_version, "reason": reason},
                    occurred_at=now,
                )
            )
        return self.get(object_type, external_id, include_deleted=True)

    def history(self, object_type: str, external_id: str) -> list[dict[str, Any]]:
        current = self.get(object_type, external_id, include_deleted=True)
        with self.session_factory() as session:
            rows = session.scalars(
                select(WorkflowObjectVersion)
                .where(WorkflowObjectVersion.object_id == current["id"])
                .order_by(WorkflowObjectVersion.version)
            )
            return [
                {
                    "version": row.version,
                    "event_type": row.event_type,
                    "state": _json_copy(row.state),
                    "approval_state": row.approval_state,
                    "actor": row.actor,
                    "created_at": _utc_iso(row.created_at),
                }
                for row in rows
            ]

    def audit_events(self, object_type: str, external_id: str) -> list[dict[str, Any]]:
        current = self.get(object_type, external_id, include_deleted=True)
        with self.session_factory() as session:
            rows = session.scalars(
                select(AuditEvent)
                .where(AuditEvent.object_id == current["id"])
                .order_by(AuditEvent.occurred_at, AuditEvent.id)
            )
            return [
                {
                    "event_type": row.event_type,
                    "actor": row.actor,
                    "occurred_at": _utc_iso(row.occurred_at),
                    "payload": _json_copy(row.payload),
                    "previous_hash": row.previous_hash,
                    "event_hash": row.event_hash,
                }
                for row in rows
            ]

    def verify_audit_chain(self, object_type: str, external_id: str) -> bool:
        previous_hash: str | None = None
        for event in self.audit_events(object_type, external_id):
            canonical = {
                "object_id": self.get(object_type, external_id, include_deleted=True)["id"],
                "event_type": event["event_type"],
                "actor": event["actor"],
                "occurred_at": event["occurred_at"],
                "payload": event["payload"],
                "previous_hash": previous_hash,
            }
            expected = hashlib.sha256(
                json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if event["previous_hash"] != previous_hash or event["event_hash"] != expected:
                return False
            previous_hash = event["event_hash"]
        return True
