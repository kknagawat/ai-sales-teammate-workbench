from sqlalchemy import CheckConstraint, Index, UniqueConstraint, text

from app.core.config import Settings
from app.db.base import Base
from app.db.session import async_session_factory
from app.db.sync_session import sync_session_factory


def test_sync_database_url_is_derived_from_async_url() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost:5432/dbname",
    )

    assert settings.sync_database_url == "postgresql+psycopg://user:pass@localhost:5432/dbname"


def test_model_metadata_imports_all_batch_1_tables() -> None:
    assert {
        "organizations",
        "users",
        "lead_work_items",
        "llm_generation_runs",
        "audit_logs",
        "background_jobs",
        "idempotency_keys",
    }.issubset(Base.metadata.tables.keys())


def test_user_email_is_unique_per_organization() -> None:
    constraints = Base.metadata.tables["users"].constraints

    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_users_organization_email"
        for constraint in constraints
    )


def test_audit_log_action_has_check_constraint() -> None:
    constraints = Base.metadata.tables["audit_logs"].constraints

    assert any(
        isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_audit_logs_action"
        for constraint in constraints
    )


def test_background_jobs_have_partial_active_job_unique_index() -> None:
    indexes = Base.metadata.tables["background_jobs"].indexes

    assert any(
        isinstance(index, Index)
        and index.name == "uq_background_jobs_active"
        and index.unique
        and str(index.dialect_options["postgresql"]["where"])
        == "status IN ('QUEUED','RUNNING')"
        for index in indexes
    )


async def test_async_session_executes_select_one() -> None:
    async with async_session_factory() as session:
        result = await session.execute(text("select 1"))

    assert result.scalar_one() == 1


def test_sync_session_executes_select_one() -> None:
    with sync_session_factory() as session:
        result = session.execute(text("select 1"))

    assert result.scalar_one() == 1
