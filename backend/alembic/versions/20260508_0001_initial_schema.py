"""Initial database schema.

Revision ID: 20260508_0001
Revises:
Create Date: 2026-05-08 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260508_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def string_enum(name: str, values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "users",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role", string_enum("user_role", ("ADMIN", "REVIEWER")), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_organization_id"), "users", ["organization_id"], unique=False)

    op.create_table(
        "lead_work_items",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            string_enum(
                "work_item_status",
                ("PENDING_REVIEW", "REGENERATING", "PROCESSING", "SENT", "FAILED", "REJECTED"),
            ),
            nullable=False,
        ),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("ai_draft", sa.Text(), nullable=False),
        sa.Column("final_draft", sa.Text(), nullable=False),
        sa.Column("regeneration_count", sa.Integer(), nullable=False),
        sa.Column("approved_draft_snapshot", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("lead_first_name", sa.String(length=120), nullable=False),
        sa.Column("lead_last_name", sa.String(length=120), nullable=False),
        sa.Column("lead_email", sa.String(length=320), nullable=False),
        sa.Column("lead_phone", sa.String(length=60), nullable=True),
        sa.Column("lead_title", sa.String(length=255), nullable=True),
        sa.Column("lead_linkedin_url", sa.String(length=500), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("company_domain", sa.String(length=255), nullable=True),
        sa.Column("company_industry", sa.String(length=255), nullable=False),
        sa.Column("company_size", sa.String(length=50), nullable=False),
        sa.Column("company_region", sa.String(length=120), nullable=False),
        sa.Column("lead_source", sa.String(length=80), nullable=False),
        sa.Column("source_event_type", sa.String(length=80), nullable=False),
        sa.Column("source_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_event_summary", sa.Text(), nullable=False),
        sa.Column("buying_stage", sa.String(length=80), nullable=False),
        sa.Column("intent_score", sa.Integer(), nullable=False),
        sa.Column("fit_score", sa.Integer(), nullable=False),
        sa.Column(
            "priority",
            string_enum("work_item_priority", ("LOW", "MEDIUM", "HIGH", "URGENT")),
            nullable=False,
        ),
        sa.Column("lead_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latest_generation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lead_work_items_org_assigned_status",
        "lead_work_items",
        ["organization_id", "assigned_reviewer_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_lead_work_items_org_company_domain",
        "lead_work_items",
        ["organization_id", "company_domain"],
        unique=False,
    )
    op.create_index(
        "ix_lead_work_items_org_priority_status",
        "lead_work_items",
        ["organization_id", "priority", "status"],
        unique=False,
    )
    op.create_index(
        "ix_lead_work_items_org_source_event",
        "lead_work_items",
        ["organization_id", "lead_source", "source_event_type"],
        unique=False,
    )
    op.create_index(
        "ix_lead_work_items_org_status_created",
        "lead_work_items",
        ["organization_id", "status", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_lead_work_items_org_updated",
        "lead_work_items",
        ["organization_id", sa.text("updated_at DESC")],
        unique=False,
    )

    op.create_table(
        "llm_generation_runs",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", string_enum("llm_provider", ("anthropic", "mock")), nullable=False),
        sa.Column(
            "provider_mode", string_enum("llm_provider_mode", ("real", "mock")), nullable=False
        ),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=60), nullable=False),
        sa.Column("schema_version", sa.String(length=60), nullable=False),
        sa.Column(
            "request_type",
            string_enum("llm_request_type", ("INITIAL_DRAFT", "REGENERATION")),
            nullable=False,
        ),
        sa.Column(
            "status",
            string_enum("llm_run_status", ("STARTED", "COMPLETED", "FAILED")),
            nullable=False,
        ),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("structured_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decision_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provider_thinking_summary", sa.Text(), nullable=True),
        sa.Column("provider_raw_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_item_id"], ["lead_work_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_llm_generation_runs_org_provider_created",
        "llm_generation_runs",
        ["organization_id", "provider", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_llm_generation_runs_org_status_created",
        "llm_generation_runs",
        ["organization_id", "status", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_llm_generation_runs_work_item_created",
        "llm_generation_runs",
        ["work_item_id", sa.text("created_at DESC")],
        unique=False,
    )

    op.create_foreign_key(
        "fk_lead_work_items_latest_generation_run_id",
        "lead_work_items",
        "llm_generation_runs",
        ["latest_generation_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "audit_logs",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_item_id"], ["lead_work_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_logs_org_created", "audit_logs", ["organization_id", sa.text("created_at DESC")]
    )
    op.create_index(
        "ix_audit_logs_work_item_created",
        "audit_logs",
        ["work_item_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "background_jobs",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("task_name", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            string_enum("background_job_status", ("QUEUED", "RUNNING", "COMPLETED", "FAILED")),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_item_id"], ["lead_work_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_background_jobs_org_status_created",
        "background_jobs",
        ["organization_id", "status", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_background_jobs_work_item_task_status",
        "background_jobs",
        ["work_item_id", "task_name", "status"],
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=128), nullable=False),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "endpoint", "idempotency_key", name="uq_idempotency_keys_user_endpoint_key"
        ),
    )
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_expires_at", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_background_jobs_work_item_task_status", table_name="background_jobs")
    op.drop_index("ix_background_jobs_org_status_created", table_name="background_jobs")
    op.drop_table("background_jobs")
    op.drop_index("ix_audit_logs_work_item_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_org_created", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_constraint(
        "fk_lead_work_items_latest_generation_run_id", "lead_work_items", type_="foreignkey"
    )
    op.drop_index("ix_llm_generation_runs_work_item_created", table_name="llm_generation_runs")
    op.drop_index("ix_llm_generation_runs_org_status_created", table_name="llm_generation_runs")
    op.drop_index("ix_llm_generation_runs_org_provider_created", table_name="llm_generation_runs")
    op.drop_table("llm_generation_runs")
    op.drop_index("ix_lead_work_items_org_updated", table_name="lead_work_items")
    op.drop_index("ix_lead_work_items_org_status_created", table_name="lead_work_items")
    op.drop_index("ix_lead_work_items_org_source_event", table_name="lead_work_items")
    op.drop_index("ix_lead_work_items_org_priority_status", table_name="lead_work_items")
    op.drop_index("ix_lead_work_items_org_company_domain", table_name="lead_work_items")
    op.drop_index("ix_lead_work_items_org_assigned_status", table_name="lead_work_items")
    op.drop_table("lead_work_items")
    op.drop_index(op.f("ix_users_organization_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")
