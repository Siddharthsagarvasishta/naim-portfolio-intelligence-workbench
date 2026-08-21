"""Create durable workflow, identity, and audit tables.

Revision ID: 20260801_0001
Revises: none
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260801_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_object",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("approval_state", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("modified_by", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_type", "external_id", name="uq_workflow_object_type_id"),
    )
    op.create_index(
        "ix_workflow_object_type_deleted",
        "workflow_object",
        ["object_type", "deleted_at"],
        unique=False,
    )
    op.create_table(
        "workflow_object_version",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("approval_state", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["object_id"], ["workflow_object.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_id", "version", name="uq_workflow_version"),
    )
    op.create_index(
        "ix_workflow_object_version_object_id",
        "workflow_object_version",
        ["object_id"],
        unique=False,
    )
    op.create_table(
        "audit_event",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=True),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["object_id"], ["workflow_object.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_hash"),
    )
    op.create_index(
        "ix_audit_object_time",
        "audit_event",
        ["object_id", "occurred_at"],
        unique=False,
    )
    op.create_table(
        "user_account",
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("username"),
    )
    op.create_table(
        "revoked_token",
        sa.Column("token_id", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_id"),
    )
    op.create_index(
        "ix_revoked_token_username",
        "revoked_token",
        ["username"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_revoked_token_username", table_name="revoked_token")
    op.drop_table("revoked_token")
    op.drop_table("user_account")
    op.drop_index("ix_audit_object_time", table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_index("ix_workflow_object_version_object_id", table_name="workflow_object_version")
    op.drop_table("workflow_object_version")
    op.drop_index("ix_workflow_object_type_deleted", table_name="workflow_object")
    op.drop_table("workflow_object")
