import logging
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_current_user
from app.audit import actions
from app.core.config import get_settings
from app.db.session import get_async_session
from app.llm.errors import LLMConfigurationError
from app.llm.providers import get_llm_provider
from app.llm.runs import (
    apply_generation_failure,
    apply_generation_success,
    create_generation_run,
)
from app.llm.types import GenerationContext
from app.models.audit_log import AuditLog
from app.models.background_job import BackgroundJob
from app.models.enums import (
    BackgroundJobStatus,
    LLMRequestType,
    UserRole,
    WorkItemStatus,
)
from app.models.idempotency_key import IdempotencyKey
from app.models.lead_work_item import LeadWorkItem
from app.models.llm_generation_run import LLMGenerationRun
from app.models.user import User
from app.schemas.work_items import (
    AdminUserResponse,
    AdminUsersResponse,
    AuditLogListResponse,
    AuditLogResponse,
    BackgroundJobSummary,
    DecisionRequest,
    DraftUpdateRequest,
    GenerationRunListResponse,
    GenerationRunSummary,
    RegenerateRequest,
    WorkItemDetail,
    WorkItemListResponse,
    WorkItemSummary,
)
from app.work_items.access import get_accessible_work_item
from app.work_items.errors import conflict
from app.work_items.state_machine import WorkItemAction, can_perform_action
from app.workers.approvals import enqueue_process_approval

router = APIRouter()
admin_router = APIRouter()
logger = logging.getLogger(__name__)


def _full_name(item: LeadWorkItem) -> str:
    return f"{item.lead_first_name} {item.lead_last_name}"


def _assigned_reviewer_payload(user: User | None) -> dict | None:
    if user is None:
        return None
    return {"id": user.id, "name": user.name, "email": user.email}


def _summary(item: LeadWorkItem) -> WorkItemSummary:
    return WorkItemSummary(
        id=item.id,
        status=item.status,
        priority=item.priority,
        version=item.version,
        lead_name=_full_name(item),
        lead_email=item.lead_email,
        lead_title=item.lead_title,
        company_name=item.company_name,
        company_domain=item.company_domain,
        lead_source=item.lead_source,
        source_event_type=item.source_event_type,
        buying_stage=item.buying_stage,
        intent_score=item.intent_score,
        fit_score=item.fit_score,
        assigned_reviewer=_assigned_reviewer_payload(item.assigned_reviewer),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _generation_run(run: LLMGenerationRun | None) -> GenerationRunSummary | None:
    if run is None:
        return None
    return GenerationRunSummary(
        id=run.id,
        provider=run.provider,
        provider_mode=run.provider_mode,
        model=run.model,
        request_type=run.request_type,
        status=run.status,
        structured_output=run.structured_output,
        decision_trace=run.decision_trace,
        token_usage=run.token_usage,
        latency_ms=run.latency_ms,
        error_message=run.error_message,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


def _background_job(job: BackgroundJob) -> BackgroundJobSummary:
    return BackgroundJobSummary(
        id=job.id,
        task_name=job.task_name,
        status=job.status,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
    )


def _detail(item: LeadWorkItem, jobs: list[BackgroundJob]) -> WorkItemDetail:
    summary = _summary(item)
    return WorkItemDetail(
        **summary.model_dump(),
        reviewer_note=item.reviewer_note,
        ai_draft=item.ai_draft,
        final_draft=item.final_draft,
        regeneration_count=item.regeneration_count,
        approved_draft_snapshot=item.approved_draft_snapshot,
        approved_at=item.approved_at,
        sent_at=item.sent_at,
        source_event_summary=item.source_event_summary,
        source_event_at=item.source_event_at,
        lead_profile=item.lead_profile,
        latest_generation_run=_generation_run(item.latest_generation_run),
        background_jobs=[_background_job(job) for job in jobs],
    )


def _audit_log(log: AuditLog, actor: User | None) -> AuditLogResponse:
    return AuditLogResponse(
        id=log.id,
        actor_user_id=log.actor_user_id,
        actor_name=actor.name if actor else None,
        action=log.action,
        metadata=log.metadata_json,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        created_at=log.created_at,
    )


def _request_meta(request: Request) -> dict:
    forwarded_for = request.headers.get("x-forwarded-for")
    client_ip = forwarded_for.split(",", 1)[0].strip() if forwarded_for else None
    return {
        "ip_address": client_ip or (request.client.host if request.client else None),
        "user_agent": request.headers.get("user-agent"),
    }


def _audit(
    item: LeadWorkItem,
    action: str,
    *,
    actor: User | None,
    metadata: dict | None = None,
    request: Request | None = None,
) -> AuditLog:
    request_meta = _request_meta(request) if request else {}
    return AuditLog(
        organization_id=item.organization_id,
        work_item_id=item.id,
        actor_user_id=actor.id if actor else None,
        action=action,
        metadata_json=metadata or {},
        ip_address=request_meta.get("ip_address"),
        user_agent=request_meta.get("user_agent"),
    )


def _action_metadata(
    item: LeadWorkItem,
    actor: User,
    metadata: dict | None = None,
) -> dict:
    payload = dict(metadata or {})
    if (
        actor.role == UserRole.ADMIN
        and item.assigned_reviewer_id is not None
        and item.assigned_reviewer_id != actor.id
    ):
        payload["override"] = True
        payload["originally_assigned_to"] = str(item.assigned_reviewer_id)
    return payload


def _check_version(item: LeadWorkItem, last_seen_version: int) -> None:
    if item.version != last_seen_version:
        raise conflict(code="STALE_VERSION")


def _check_action(item: LeadWorkItem, action: WorkItemAction) -> None:
    if not can_perform_action(item.status, action):
        raise conflict(
            f"Cannot perform {action.value} while item is {item.status.value}.",
            code="INVALID_ACTION",
        )


async def _load_detail_jobs(session: AsyncSession, item_id: UUID) -> list[BackgroundJob]:
    return list(
        await session.scalars(
            select(BackgroundJob)
            .where(BackgroundJob.work_item_id == item_id)
            .order_by(BackgroundJob.created_at.desc())
        )
    )


async def _load_item_for_detail(
    session: AsyncSession,
    user: User,
    work_item_id: UUID,
) -> LeadWorkItem:
    item = await get_accessible_work_item(session, user, work_item_id)
    await session.refresh(item, attribute_names=["assigned_reviewer", "latest_generation_run"])
    return item


async def _current_detail(
    session: AsyncSession,
    user: User,
    work_item_id: UUID,
) -> WorkItemDetail:
    item = await _load_item_for_detail(session, user, work_item_id)
    return _detail(item, await _load_detail_jobs(session, item.id))


def _approval_request_hash(work_item_id: UUID, payload: DecisionRequest) -> str:
    return sha256(f"{work_item_id}:{payload.model_dump_json()}".encode()).hexdigest()


async def _get_idempotency_key(
    session: AsyncSession,
    user: User,
    endpoint: str,
    idempotency_key: str,
) -> IdempotencyKey | None:
    return await session.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.user_id == user.id,
            IdempotencyKey.endpoint == endpoint,
            IdempotencyKey.idempotency_key == idempotency_key,
        )
    )


async def _cache_idempotency_response(
    session: AsyncSession,
    user: User,
    endpoint: str,
    idempotency_key: str,
    detail: WorkItemDetail,
) -> None:
    existing_key = await _get_idempotency_key(session, user, endpoint, idempotency_key)
    if existing_key is None:
        return
    existing_key.response_body = jsonable_encoder(detail)
    existing_key.status_code = status.HTTP_200_OK
    await session.commit()


async def _create_processing_job(
    session: AsyncSession,
    item: LeadWorkItem,
) -> BackgroundJob:
    existing = await session.scalar(
        select(BackgroundJob).where(
            BackgroundJob.work_item_id == item.id,
            BackgroundJob.task_name == "process_approval",
            BackgroundJob.status.in_([BackgroundJobStatus.QUEUED, BackgroundJobStatus.RUNNING]),
        )
    )
    if existing is not None:
        raise conflict(
            "This item already has an active processing job.",
            code="ACTIVE_PROCESSING_JOB",
        )

    job = BackgroundJob(
        organization_id=item.organization_id,
        work_item_id=item.id,
        task_name="process_approval",
        status=BackgroundJobStatus.QUEUED,
    )
    session.add(job)
    await session.flush()
    return job


async def _active_processing_job(
    session: AsyncSession,
    item_id: UUID,
) -> BackgroundJob | None:
    return await session.scalar(
        select(BackgroundJob)
        .where(
            BackgroundJob.work_item_id == item_id,
            BackgroundJob.task_name == "process_approval",
            BackgroundJob.status.in_([BackgroundJobStatus.QUEUED, BackgroundJobStatus.RUNNING]),
        )
        .with_for_update()
    )


def _processing_job_is_stale(job: BackgroundJob) -> bool:
    reference_time = job.started_at or job.created_at
    stale_after = timedelta(seconds=get_settings().approval_job_stale_after_seconds)
    return datetime.now(UTC) - reference_time > stale_after


async def _prepare_processing_retry(
    session: AsyncSession,
    item: LeadWorkItem,
    request: Request,
) -> None:
    _check_action(item, WorkItemAction.RETRY_PROCESSING)
    if item.status == WorkItemStatus.FAILED:
        return

    active_job = await _active_processing_job(session, item.id)
    if active_job is None:
        session.add(
            _audit(
                item,
                actions.JOB_FAILED,
                actor=None,
                metadata={
                    "phase": "missing_job_recovery",
                    "task_name": "process_approval",
                    "error_message": "Processing item had no active approval job.",
                },
                request=request,
            )
        )
        await session.flush()
        return

    if not _processing_job_is_stale(active_job):
        raise conflict(
            "This item already has an active processing job.",
            code="ACTIVE_PROCESSING_JOB",
        )

    error_message = "Processing job exceeded stale threshold and was failed for retry."
    active_job.status = BackgroundJobStatus.FAILED
    active_job.error_message = error_message
    active_job.completed_at = datetime.now(UTC)
    session.add(
        _audit(
            item,
            actions.JOB_FAILED,
            actor=None,
            metadata={
                "job_id": str(active_job.id),
                "phase": "stale_job_recovery",
                "task_name": active_job.task_name,
                "error_message": error_message,
            },
            request=request,
        )
    )
    await session.flush()


async def _mark_processing_enqueue_failed(
    session: AsyncSession,
    job_id: UUID,
    exc: Exception,
    request: Request,
) -> None:
    error_message = str(exc)[:500] or "Approval job could not be enqueued."
    job = await session.get(BackgroundJob, job_id, with_for_update=True)
    if job is None:
        return
    item = await session.get(LeadWorkItem, job.work_item_id, with_for_update=True)
    job.status = BackgroundJobStatus.FAILED
    job.error_message = error_message
    job.completed_at = datetime.now(UTC)
    if item is not None and item.status == WorkItemStatus.PROCESSING:
        item.status = WorkItemStatus.FAILED
        item.version += 1
        session.add(
            _audit(
                item,
                actions.JOB_FAILED,
                actor=None,
                metadata={
                    "job_id": str(job.id),
                    "task_name": job.task_name,
                    "phase": "enqueue",
                    "error_message": error_message,
                },
                request=request,
            )
        )
    await session.commit()


async def _enqueue_processing_job(
    session: AsyncSession,
    job_id: UUID,
    request: Request,
) -> None:
    try:
        celery_task_id = enqueue_process_approval(job_id)
    except Exception as exc:
        logger.exception("Celery enqueue failed for approval job %s", job_id)
        await _mark_processing_enqueue_failed(session, job_id, exc, request)
        return

    job = await session.get(BackgroundJob, job_id, with_for_update=True)
    if job is None or job.celery_task_id:
        return
    # The worker can start before the API records the task id; if it does,
    # it converges by writing the same field from the worker side.
    job.celery_task_id = celery_task_id
    await session.commit()


async def _handle_approval_integrity_error(
    session: AsyncSession,
    user: User,
    work_item_id: UUID,
    endpoint: str,
    idempotency_key: str,
    request_hash: str,
) -> WorkItemDetail:
    existing_key = await _get_idempotency_key(session, user, endpoint, idempotency_key)
    if existing_key is not None:
        if existing_key.request_hash != request_hash:
            raise conflict(
                "Idempotency-Key was reused with a different request.",
                code="IDEMPOTENCY_KEY_REUSED",
            )
        return await _current_detail(session, user, work_item_id)

    active_job = await session.scalar(
        select(BackgroundJob).where(
            BackgroundJob.work_item_id == work_item_id,
            BackgroundJob.task_name == "process_approval",
            BackgroundJob.status.in_([BackgroundJobStatus.QUEUED, BackgroundJobStatus.RUNNING]),
        )
    )
    if active_job is not None:
        raise conflict(
            "This item already has an active processing job.",
            code="ACTIVE_PROCESSING_JOB",
        )

    raise conflict(
        "Approval could not be completed because another request changed this item.",
        code="CONCURRENT_APPROVAL",
    )


async def _mark_regeneration_failed(
    session: AsyncSession,
    user: User,
    work_item_id: UUID,
    run_id: UUID,
    exc: Exception,
    request: Request,
) -> None:
    error_message = str(exc)[:500] or "Provider failed."
    item = await get_accessible_work_item(session, user, work_item_id, for_update=True)
    run = await session.get(LLMGenerationRun, run_id, with_for_update=True)

    if item.status == WorkItemStatus.REGENERATING:
        item.status = WorkItemStatus.PENDING_REVIEW
        item.version += 1

    apply_generation_failure(run, exc)

    session.add(
        _audit(
            item,
            actions.DRAFT_REGENERATION_FAILED,
            actor=user,
            metadata=_action_metadata(
                item,
                user,
                {
                    "generation_run_id": str(run_id),
                    "error_message": error_message,
                },
            ),
            request=request,
        )
    )
    await session.commit()


@router.get("/work-items", response_model=WorkItemListResponse)
async def list_work_items(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> WorkItemListResponse:
    stmt = (
        select(LeadWorkItem)
        .options(selectinload(LeadWorkItem.assigned_reviewer))
        .where(LeadWorkItem.organization_id == current_user.organization_id)
        .order_by(LeadWorkItem.created_at.desc())
    )
    if current_user.role != UserRole.ADMIN:
        stmt = stmt.where(LeadWorkItem.assigned_reviewer_id == current_user.id)

    items = list(await session.scalars(stmt))
    return WorkItemListResponse(items=[_summary(item) for item in items])


@router.get("/work-items/{work_item_id}", response_model=WorkItemDetail)
async def get_work_item(
    work_item_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> WorkItemDetail:
    return await _current_detail(session, current_user, work_item_id)


@router.patch("/work-items/{work_item_id}/draft", response_model=WorkItemDetail)
async def update_draft(
    work_item_id: UUID,
    payload: DraftUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> WorkItemDetail:
    item = await get_accessible_work_item(session, current_user, work_item_id, for_update=True)
    _check_version(item, payload.last_seen_version)
    _check_action(item, WorkItemAction.EDIT_DRAFT)

    item.final_draft = payload.final_draft
    item.version += 1
    session.add(
        _audit(
            item,
            actions.DRAFT_EDITED,
            actor=current_user,
            metadata=_action_metadata(item, current_user),
            request=request,
        )
    )
    await session.commit()

    return await _current_detail(session, current_user, work_item_id)


@router.post("/work-items/{work_item_id}/reject", response_model=WorkItemDetail)
async def reject_work_item(
    work_item_id: UUID,
    payload: DecisionRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> WorkItemDetail:
    item = await get_accessible_work_item(session, current_user, work_item_id, for_update=True)
    _check_version(item, payload.last_seen_version)
    _check_action(item, WorkItemAction.REJECT)

    item.status = WorkItemStatus.REJECTED
    item.reviewer_note = payload.reviewer_note
    item.version += 1
    session.add(
        _audit(
            item,
            actions.ITEM_REJECTED,
            actor=current_user,
            metadata=_action_metadata(
                item,
                current_user,
                {"reviewer_note": payload.reviewer_note},
            ),
            request=request,
        )
    )
    await session.commit()

    return await _current_detail(session, current_user, work_item_id)


@router.post("/work-items/{work_item_id}/reopen", response_model=WorkItemDetail)
async def reopen_work_item(
    work_item_id: UUID,
    payload: DecisionRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> WorkItemDetail:
    item = await get_accessible_work_item(session, current_user, work_item_id, for_update=True)
    _check_version(item, payload.last_seen_version)
    _check_action(item, WorkItemAction.REOPEN)

    item.status = WorkItemStatus.PENDING_REVIEW
    if payload.reviewer_note is not None:
        item.reviewer_note = payload.reviewer_note
    item.version += 1
    session.add(
        _audit(
            item,
            actions.ITEM_REOPENED,
            actor=current_user,
            metadata=_action_metadata(
                item,
                current_user,
                {"reviewer_note": payload.reviewer_note},
            ),
            request=request,
        )
    )
    await session.commit()

    return await _current_detail(session, current_user, work_item_id)


@router.post("/work-items/{work_item_id}/approve", response_model=WorkItemDetail)
async def approve_work_item(
    work_item_id: UUID,
    payload: DecisionRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> WorkItemDetail:
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required.",
        )

    endpoint = f"POST /work-items/{work_item_id}/approve"
    request_hash = _approval_request_hash(work_item_id, payload)
    existing_key = await _get_idempotency_key(session, current_user, endpoint, idempotency_key)
    if existing_key is not None:
        if existing_key.request_hash != request_hash:
            raise conflict(
                "Idempotency-Key was reused with a different request.",
                code="IDEMPOTENCY_KEY_REUSED",
            )
        return await _current_detail(session, current_user, work_item_id)

    item = await get_accessible_work_item(session, current_user, work_item_id, for_update=True)
    _check_version(item, payload.last_seen_version)
    _check_action(item, WorkItemAction.APPROVE)

    item.status = WorkItemStatus.PROCESSING
    item.reviewer_note = payload.reviewer_note
    item.approved_draft_snapshot = item.final_draft
    item.approved_by_user_id = current_user.id
    item.approved_at = datetime.now(UTC)
    item.version += 1
    job = await _create_processing_job(session, item)
    session.add(
        _audit(
            item,
            actions.ITEM_APPROVED,
            actor=current_user,
            metadata=_action_metadata(
                item,
                current_user,
                {"idempotency_key": idempotency_key},
            ),
            request=request,
        )
    )
    session.add(
        IdempotencyKey(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            endpoint=endpoint,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_body=None,
            status_code=status.HTTP_200_OK,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return await _handle_approval_integrity_error(
            session,
            current_user,
            work_item_id,
            endpoint,
            idempotency_key,
            request_hash,
        )

    await _enqueue_processing_job(session, job.id, request)
    detail = await _current_detail(session, current_user, work_item_id)
    await _cache_idempotency_response(session, current_user, endpoint, idempotency_key, detail)
    return detail


@router.post("/work-items/{work_item_id}/retry-processing", response_model=WorkItemDetail)
async def retry_processing(
    work_item_id: UUID,
    payload: DecisionRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> WorkItemDetail:
    item = await get_accessible_work_item(session, current_user, work_item_id, for_update=True)
    _check_version(item, payload.last_seen_version)
    await _prepare_processing_retry(session, item, request)

    item.status = WorkItemStatus.PROCESSING
    item.reviewer_note = payload.reviewer_note or item.reviewer_note
    item.approved_draft_snapshot = item.approved_draft_snapshot or item.final_draft
    item.approved_by_user_id = item.approved_by_user_id or current_user.id
    item.approved_at = item.approved_at or datetime.now(UTC)
    item.version += 1
    job = await _create_processing_job(session, item)
    session.add(
        _audit(
            item,
            actions.ITEM_APPROVED,
            actor=current_user,
            metadata=_action_metadata(item, current_user, {"retry": True}),
            request=request,
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise conflict(
            "This item already has an active processing job.",
            code="ACTIVE_PROCESSING_JOB",
        ) from exc

    await _enqueue_processing_job(session, job.id, request)
    return await _current_detail(session, current_user, work_item_id)


@router.post("/work-items/{work_item_id}/regenerate", response_model=WorkItemDetail)
async def regenerate_work_item(
    work_item_id: UUID,
    payload: RegenerateRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> WorkItemDetail:
    item = await get_accessible_work_item(session, current_user, work_item_id, for_update=True)
    _check_version(item, payload.last_seen_version)
    _check_action(item, WorkItemAction.REGENERATE)
    try:
        provider = get_llm_provider(organization_id=item.organization_id)
    except LLMConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI provider is not configured.",
        ) from exc

    context = GenerationContext(
        organization_id=item.organization_id,
        work_item_id=item.id,
        lead_profile=item.lead_profile,
        existing_draft=item.final_draft,
        reviewer_feedback=payload.reviewer_feedback,
        request_type=LLMRequestType.REGENERATION,
    )

    item.status = WorkItemStatus.REGENERATING
    item.version += 1
    run = create_generation_run(item, provider, context)
    session.add(run)
    session.add(
        _audit(
            item,
            actions.DRAFT_REGENERATION_STARTED,
            actor=current_user,
            metadata=_action_metadata(
                item,
                current_user,
                {"reviewer_feedback": payload.reviewer_feedback},
            ),
            request=request,
        )
    )
    await session.commit()

    run_id = run.id
    try:
        generation_result = await provider.generate_followup(context)
    except Exception as exc:
        await _mark_regeneration_failed(session, current_user, work_item_id, run_id, exc, request)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI regeneration failed. Review the existing draft and try again.",
        ) from exc

    item = await get_accessible_work_item(session, current_user, work_item_id, for_update=True)
    run = await session.get(LLMGenerationRun, run_id, with_for_update=True)
    if item.status != WorkItemStatus.REGENERATING or run is None:
        raise conflict(code="REGENERATION_STATE_CHANGED")

    generated = generation_result.output
    draft = f"Subject: {generated.subject}\n\n{generated.email_body}"
    item.ai_draft = draft
    item.final_draft = draft
    item.latest_generation_run_id = run.id
    item.regeneration_count += 1
    item.status = WorkItemStatus.PENDING_REVIEW
    item.version += 1
    apply_generation_success(run, generation_result)
    session.add(
        _audit(
            item,
            actions.DRAFT_REGENERATED,
            actor=current_user,
            metadata=_action_metadata(
                item,
                current_user,
                {"generation_run_id": str(run.id)},
            ),
            request=request,
        )
    )
    await session.commit()

    return await _current_detail(session, current_user, work_item_id)


@router.get("/work-items/{work_item_id}/audit", response_model=AuditLogListResponse)
async def list_work_item_audit(
    work_item_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> AuditLogListResponse:
    item = await get_accessible_work_item(session, current_user, work_item_id)
    rows = await session.execute(
        select(AuditLog, User)
        .outerjoin(User, AuditLog.actor_user_id == User.id)
        .where(
            AuditLog.work_item_id == item.id,
            AuditLog.organization_id == current_user.organization_id,
        )
        .order_by(AuditLog.created_at.desc())
    )
    return AuditLogListResponse(items=[_audit_log(log, actor) for log, actor in rows.all()])


@router.get("/work-items/{work_item_id}/llm-runs", response_model=GenerationRunListResponse)
async def list_work_item_llm_runs(
    work_item_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> GenerationRunListResponse:
    item = await get_accessible_work_item(session, current_user, work_item_id)
    runs = list(
        await session.scalars(
            select(LLMGenerationRun)
            .where(
                LLMGenerationRun.work_item_id == item.id,
                LLMGenerationRun.organization_id == current_user.organization_id,
            )
            .order_by(LLMGenerationRun.created_at.desc())
        )
    )
    return GenerationRunListResponse(
        items=[run for run in (_generation_run(run) for run in runs) if run]
    )


def _require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")


@admin_router.get("/admin/work-items", response_model=WorkItemListResponse)
async def admin_work_items(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> WorkItemListResponse:
    _require_admin(current_user)
    items = list(
        await session.scalars(
            select(LeadWorkItem)
            .options(selectinload(LeadWorkItem.assigned_reviewer))
            .where(LeadWorkItem.organization_id == current_user.organization_id)
            .order_by(LeadWorkItem.created_at.desc())
        )
    )
    return WorkItemListResponse(items=[_summary(item) for item in items])


@admin_router.get("/admin/audit-logs", response_model=AuditLogListResponse)
async def admin_audit_logs(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> AuditLogListResponse:
    _require_admin(current_user)
    rows = await session.execute(
        select(AuditLog, User)
        .outerjoin(User, AuditLog.actor_user_id == User.id)
        .where(AuditLog.organization_id == current_user.organization_id)
        .order_by(AuditLog.created_at.desc())
        .limit(200)
    )
    return AuditLogListResponse(items=[_audit_log(log, actor) for log, actor in rows.all()])


@admin_router.get("/admin/users", response_model=AdminUsersResponse)
async def admin_users(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> AdminUsersResponse:
    _require_admin(current_user)
    users = list(
        await session.scalars(
            select(User)
            .where(User.organization_id == current_user.organization_id)
            .order_by(User.created_at.asc())
        )
    )
    return AdminUsersResponse(
        items=[
            AdminUserResponse(
                id=user.id,
                organization_id=user.organization_id,
                email=user.email,
                name=user.name,
                role=user.role.value,
                is_active=user.is_active,
                last_login_at=user.last_login_at,
                created_at=user.created_at,
            )
            for user in users
        ]
    )
