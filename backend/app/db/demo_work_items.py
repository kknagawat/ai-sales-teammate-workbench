from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import actions
from app.db.seed import _generation_result, _scenario_data
from app.models.audit_log import AuditLog
from app.models.enums import (
    LLMProvider,
    LLMProviderMode,
    LLMRequestType,
    LLMRunStatus,
    WorkItemStatus,
)
from app.models.lead_work_item import LeadWorkItem
from app.models.llm_generation_run import LLMGenerationRun
from app.models.organization import Organization
from app.models.user import User


async def create_signup_demo_work_items(
    session: AsyncSession,
    *,
    organization: Organization,
    assignee: User,
    count: int = 5,
) -> None:
    scenarios = _scenario_data()[:count]
    for index, scenario in enumerate(scenarios, start=1):
        profile = deepcopy(scenario["profile"])
        profile["crm"]["owner_name"] = assignee.name
        result = _generation_result(profile)
        draft = f"Subject: {result['subject']}\n\n{result['email_body']}"

        item = LeadWorkItem(
            organization_id=organization.id,
            assigned_reviewer_id=assignee.id,
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
                actor_user_id=assignee.id,
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
                actor_user_id=assignee.id,
                action=actions.AI_DRAFT_GENERATED,
                metadata_json={
                    "generation_run_id": str(generation_run.id),
                    "source": "signup_demo",
                },
                ip_address="127.0.0.1",
                user_agent="signup-demo-bootstrap",
            )
        )
