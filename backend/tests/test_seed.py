import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.seed import seed_database
from app.db.sync_session import sync_session_factory
from app.models.audit_log import AuditLog
from app.models.enums import WorkItemStatus
from app.models.lead_work_item import LeadWorkItem
from app.models.llm_generation_run import LLMGenerationRun
from app.models.organization import Organization
from app.models.user import User
from app.schemas.lead_profile import LeadProfile


def test_seed_database_creates_repeatable_demo_data(seeded_database) -> None:
    with sync_session_factory() as session:
        org_count = session.scalar(select(func.count()).select_from(Organization))
        user_count = session.scalar(select(func.count()).select_from(User))
        item_count = session.scalar(select(func.count()).select_from(LeadWorkItem))
        run_count = session.scalar(select(func.count()).select_from(LLMGenerationRun))
        audit_count = session.scalar(select(func.count()).select_from(AuditLog))
        pending_globex_count = session.scalar(
            select(func.count())
            .select_from(LeadWorkItem)
            .join(Organization)
            .where(
                Organization.slug == "globex",
                LeadWorkItem.status == WorkItemStatus.PENDING_REVIEW,
            )
        )
        regenerated_count = session.scalar(
            select(func.count())
            .select_from(LeadWorkItem)
            .where(LeadWorkItem.regeneration_count > 0)
        )
        acme_reviewer = session.scalar(select(User).where(User.email == "reviewer@acme.example"))
        globex_reviewer = session.scalar(
            select(User).where(User.email == "reviewer@globex.example")
        )
        non_primary_assigned_count = session.scalar(
            select(func.count())
            .select_from(LeadWorkItem)
            .where(
                LeadWorkItem.assigned_reviewer_id.notin_(
                    [acme_reviewer.id, globex_reviewer.id]
                )
            )
        )
        lead_profiles = session.scalars(select(LeadWorkItem.lead_profile)).all()

    assert org_count == 2
    assert user_count == 8
    assert item_count == 12
    assert run_count == 14
    assert audit_count == 35
    assert pending_globex_count == 2
    assert regenerated_count == 1
    assert non_primary_assigned_count >= 2
    assert all(LeadProfile.model_validate(profile) for profile in lead_profiles)


def test_seed_database_is_repeatable(seeded_database) -> None:
    seed_database()

    with sync_session_factory() as session:
        item_count = session.scalar(select(func.count()).select_from(LeadWorkItem))

    assert item_count == 12


def test_seed_database_refuses_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "a-production-secret-that-is-long-enough")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("REVIEWER_INVITE_CODE", "production-reviewer-code")
    get_settings.cache_clear()

    try:
        with pytest.raises(RuntimeError, match="Refusing to run destructive seed script"):
            seed_database()
    finally:
        get_settings.cache_clear()
