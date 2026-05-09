"""Harden Batch 1 database schema.

Revision ID: 20260509_0002
Revises: 20260508_0001
Create Date: 2026-05-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260509_0002"
down_revision: str | None = "20260508_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


AUDIT_ACTIONS = (
    "ITEM_CREATED",
    "AI_DRAFT_GENERATION_STARTED",
    "AI_DRAFT_GENERATED",
    "AI_DRAFT_GENERATION_FAILED",
    "DRAFT_REGENERATION_STARTED",
    "DRAFT_REGENERATED",
    "DRAFT_REGENERATION_FAILED",
    "DRAFT_EDITED",
    "ITEM_APPROVED",
    "ITEM_REJECTED",
    "JOB_STARTED",
    "JOB_COMPLETED",
    "JOB_FAILED",
)


def audit_action_check_sql() -> str:
    allowed_values = ", ".join(f"'{action}'" for action in AUDIT_ACTIONS)
    return f"action IN ({allowed_values})"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_users_organization_email",
        "users",
        ["organization_id", "email"],
    )
    op.alter_column(
        "users",
        "is_active",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.text("true"),
    )

    op.alter_column(
        "lead_work_items",
        "status",
        existing_type=sa.String(),
        existing_nullable=False,
        server_default=sa.text("'PENDING_REVIEW'"),
    )
    op.alter_column(
        "lead_work_items",
        "regeneration_count",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("0"),
    )
    op.alter_column(
        "lead_work_items",
        "version",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("1"),
    )
    op.alter_column(
        "lead_work_items",
        "priority",
        existing_type=sa.String(),
        existing_nullable=False,
        server_default=sa.text("'MEDIUM'"),
    )

    op.alter_column(
        "llm_generation_runs",
        "provider_raw_metadata",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )

    op.alter_column(
        "audit_logs",
        "metadata",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    op.create_check_constraint(
        "ck_audit_logs_action",
        "audit_logs",
        audit_action_check_sql(),
    )

    op.alter_column(
        "background_jobs",
        "status",
        existing_type=sa.String(),
        existing_nullable=False,
        server_default=sa.text("'QUEUED'"),
    )
    op.alter_column(
        "background_jobs",
        "attempt_count",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("0"),
    )
    op.alter_column(
        "background_jobs",
        "max_attempts",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("3"),
    )
    op.create_index(
        "uq_background_jobs_active",
        "background_jobs",
        ["work_item_id", "task_name"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED','RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index("uq_background_jobs_active", table_name="background_jobs")
    op.alter_column(
        "background_jobs",
        "max_attempts",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "background_jobs",
        "attempt_count",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "background_jobs",
        "status",
        existing_type=sa.String(),
        existing_nullable=False,
        server_default=None,
    )

    op.drop_constraint("ck_audit_logs_action", "audit_logs", type_="check")
    op.alter_column(
        "audit_logs",
        "metadata",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=False,
        server_default=None,
    )

    op.alter_column(
        "llm_generation_runs",
        "provider_raw_metadata",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=False,
        server_default=None,
    )

    op.alter_column(
        "lead_work_items",
        "priority",
        existing_type=sa.String(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "lead_work_items",
        "version",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "lead_work_items",
        "regeneration_count",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "lead_work_items",
        "status",
        existing_type=sa.String(),
        existing_nullable=False,
        server_default=None,
    )

    op.alter_column(
        "users",
        "is_active",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )
    op.drop_constraint("uq_users_organization_email", "users", type_="unique")
