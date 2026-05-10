"""Allow rejected work item reopen audit action.

Revision ID: 20260510_0004
Revises: 20260509_0003
Create Date: 2026-05-10 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260510_0004"
down_revision: str | None = "20260509_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BASE_AUDIT_ACTIONS = (
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
    "RUNTIME_PROVIDER_CHANGED",
)
UPGRADED_AUDIT_ACTIONS = (*BASE_AUDIT_ACTIONS, "ITEM_REOPENED")


def audit_action_check_sql(actions: tuple[str, ...]) -> str:
    allowed_values = ", ".join(f"'{action}'" for action in actions)
    return f"action IN ({allowed_values})"


def upgrade() -> None:
    op.drop_constraint("ck_audit_logs_action", "audit_logs", type_="check")
    op.create_check_constraint(
        "ck_audit_logs_action",
        "audit_logs",
        audit_action_check_sql(UPGRADED_AUDIT_ACTIONS),
    )


def downgrade() -> None:
    op.drop_constraint("ck_audit_logs_action", "audit_logs", type_="check")
    op.create_check_constraint(
        "ck_audit_logs_action",
        "audit_logs",
        audit_action_check_sql(BASE_AUDIT_ACTIONS),
    )
