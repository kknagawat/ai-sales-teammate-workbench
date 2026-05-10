from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import actions
from app.db.seed import _generation_result, _scenario_data
from app.models.audit_log import AuditLog
from app.models.enums import (
    LLMProvider,
    LLMProviderMode,
    LLMRequestType,
    LLMRunStatus,
    UserRole,
    WorkItemStatus,
)
from app.models.lead_work_item import LeadWorkItem
from app.models.llm_generation_run import LLMGenerationRun
from app.models.organization import Organization
from app.models.user import User


def _signup_demo_work_item_ids(organization: Organization):
    return (
        select(LLMGenerationRun.work_item_id)
        .where(
            LLMGenerationRun.organization_id == organization.id,
            LLMGenerationRun.provider_raw_metadata.contains({"signup_demo": True}),
        )
        .distinct()
    )


async def ensure_signup_demo_work_items(
    session: AsyncSession,
    *,
    organization: Organization,
    actor: User,
    count: int = 5,
) -> None:
    existing_demo_item_id = await session.scalar(
        select(LeadWorkItem.id)
        .where(
            LeadWorkItem.organization_id == organization.id,
            LeadWorkItem.id.in_(_signup_demo_work_item_ids(organization)),
        )
        .limit(1)
    )
    if existing_demo_item_id is not None:
        return

    scenarios = _scenario_data()[:count]
    for index, scenario in enumerate(scenarios, start=1):
        profile = deepcopy(scenario["profile"])
        result = _generation_result(profile)
        draft = f"Subject: {result['subject']}\n\n{result['email_body']}"

        item = LeadWorkItem(
            organization_id=organization.id,
            assigned_reviewer_id=None,
            # New signup orgs should begin with actionable review work, even when seed
            # scenarios later include SENT/FAILED/REJECTED examples for richer demos.
            status=WorkItemStatus.PENDING_REVIEW,
            ai_draft=draft,
            final_draft=draft,
            lead_first_name=profile["contact"]["first_name"],
            lead_last_name=profile["contact"]["last_name"],
            lead_email=profile["contact"]["email"],
            lead_phone=profile["contact"]["phone"],
            lead_title=profile["contact"]["title"],
            lead_linkedin_url=profile["contact"]["linkedin_url"],
            company_name=profile["company"]["name"],
            company_domain=profile["company"]["domain"],
            company_industry=profile["company"]["industry"],
            company_size=profile["company"]["size_band"],
            company_region=profile["company"]["region"],
            lead_source=profile["source_signal"]["source"],
            source_event_type=profile["source_signal"]["event_type"],
            source_event_at=datetime.fromisoformat(profile["source_signal"]["event_at"]),
            source_event_summary=profile["source_signal"]["summary"],
            buying_stage=profile["qualification"]["buying_stage"],
            intent_score=profile["qualification"]["intent_score"],
            fit_score=profile["qualification"]["fit_score"],
            priority=scenario["priority"],
            lead_profile=profile,
        )
        session.add(item)
        await session.flush()

        generation_run = LLMGenerationRun(
            organization_id=organization.id,
            work_item_id=item.id,
            provider=LLMProvider.MOCK,
            provider_mode=LLMProviderMode.MOCK,
            model="mock-sales-followup-v1",
            prompt_version="signup-demo-v1",
            schema_version="generation-result-v1",
            request_type=LLMRequestType.INITIAL_DRAFT,
            status=LLMRunStatus.COMPLETED,
            input_snapshot=profile,
            structured_output=result,
            decision_trace=result["decision_trace"],
            provider_raw_metadata={"signup_demo": True, "scenario_number": index},
            token_usage={"input_tokens": 850, "output_tokens": 360},
            latency_ms=120,
            completed_at=datetime.now(UTC),
        )
        session.add(generation_run)
        await session.flush()
        item.latest_generation_run_id = generation_run.id

        session.add(
            AuditLog(
                organization_id=organization.id,
                work_item_id=item.id,
                actor_user_id=actor.id,
                action=actions.ITEM_CREATED,
                metadata_json={"source": "signup_demo"},
                ip_address="127.0.0.1",
                user_agent="signup-demo-bootstrap",
            )
        )
        session.add(
            AuditLog(
                organization_id=organization.id,
                work_item_id=item.id,
                actor_user_id=actor.id,
                action=actions.AI_DRAFT_GENERATED,
                metadata_json={
                    "generation_run_id": str(generation_run.id),
                    "source": "signup_demo",
                },
                ip_address="127.0.0.1",
                user_agent="signup-demo-bootstrap",
            )
        )


async def assign_signup_demo_work_items_to_reviewer(
    session: AsyncSession,
    *,
    organization: Organization,
    reviewer: User,
) -> int:
    admin_user_ids = select(User.id).where(
        User.organization_id == organization.id,
        User.role == UserRole.ADMIN,
    )
    stmt = (
        select(LeadWorkItem)
        .where(
            LeadWorkItem.organization_id == organization.id,
            LeadWorkItem.id.in_(_signup_demo_work_item_ids(organization)),
            or_(
                LeadWorkItem.assigned_reviewer_id.is_(None),
                LeadWorkItem.assigned_reviewer_id.in_(admin_user_ids),
            ),
        )
        .order_by(LeadWorkItem.created_at.asc())
        .with_for_update()
    )
    items = list(await session.scalars(stmt))
    for item in items:
        item.assigned_reviewer_id = reviewer.id
    return len(items)
