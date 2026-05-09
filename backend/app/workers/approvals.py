import logging
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from celery import Task
from sqlalchemy import select

from app.audit import actions
from app.core.config import get_settings
from app.db import base as model_registry  # noqa: F401
from app.db.sync_session import sync_session_factory
from app.models.audit_log import AuditLog
from app.models.background_job import BackgroundJob
from app.models.enums import BackgroundJobStatus, WorkItemStatus
from app.models.lead_work_item import LeadWorkItem
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class ApprovalProcessingError(Exception):
    """Raised when approval processing failed but should be retried."""


def enqueue_process_approval(job_id: UUID) -> str:
    result = process_approval.delay(str(job_id))
    logger.info("Approval job enqueued job_id=%s celery_task_id=%s", job_id, result.id)
    return str(result.id)


@celery_app.task(
    bind=True,
    name="process_approval",
    autoretry_for=(),
    max_retries=3,
)
def process_approval(self: Task, job_id: str) -> str:
    logger.info(
        "Approval task received job_id=%s celery_task_id=%s retry=%s",
        job_id,
        self.request.id,
        self.request.retries,
    )
    try:
        status = process_approval_job(UUID(job_id), celery_task_id=self.request.id)
    except ApprovalProcessingError as exc:
        countdown = min(2 ** max(self.request.retries, 0), 60)
        logger.warning(
            "Approval task retry scheduled job_id=%s celery_task_id=%s countdown=%s error=%s",
            job_id,
            self.request.id,
            countdown,
            exc,
        )
        raise self.retry(exc=exc, countdown=countdown) from exc
    return status.value


def process_approval_job(
    job_id: UUID,
    *,
    celery_task_id: str | None = None,
) -> BackgroundJobStatus:
    logger.info("Approval processing started job_id=%s", job_id)
    snapshot, lead_email, work_item_id = _start_processing_attempt(job_id, celery_task_id)
    if snapshot is None or lead_email is None or work_item_id is None:
        status = _job_status(job_id)
        logger.info("Approval processing job %s finished without work: %s", job_id, status.value)
        return status

    try:
        email_metadata = _fake_email_send(lead_email, snapshot)
        logger.info(
            "Fake email send simulated job_id=%s message_id=%s body_sha256=%s",
            job_id,
            email_metadata["message_id"],
            email_metadata["body_sha256"],
        )
        crm_metadata = _fake_crm_sync(work_item_id, snapshot)
        logger.info(
            "Fake CRM sync/activity simulated job_id=%s activity_id=%s work_item_id=%s",
            job_id,
            crm_metadata["activity_id"],
            work_item_id,
        )
    except Exception as exc:
        logger.exception("Approval processing job %s failed during side effects", job_id)
        return _record_processing_error(job_id, exc)

    status = _complete_processing(job_id, email_metadata, crm_metadata)
    logger.info("Approval processing completed job_id=%s status=%s", job_id, status.value)
    return status


def _start_processing_attempt(
    job_id: UUID,
    celery_task_id: str | None,
) -> tuple[str | None, str | None, UUID | None]:
    now = datetime.now(UTC)
    with sync_session_factory() as session:
        job = session.scalar(
            select(BackgroundJob).where(BackgroundJob.id == job_id).with_for_update()
        )
        if job is None:
            return None, None, None
        if celery_task_id and not job.celery_task_id:
            job.celery_task_id = celery_task_id
        if job.status == BackgroundJobStatus.COMPLETED:
            return None, None, None

        item = session.scalar(
            select(LeadWorkItem).where(LeadWorkItem.id == job.work_item_id).with_for_update()
        )
        if item is None:
            _mark_job_failed(session, job, None, "Work item no longer exists.")
            session.commit()
            return None, None, None

        if item.status == WorkItemStatus.SENT:
            job.status = BackgroundJobStatus.COMPLETED
            job.completed_at = now
            session.commit()
            return None, None, None

        if item.status != WorkItemStatus.PROCESSING:
            _mark_job_failed(
                session,
                job,
                item,
                f"Cannot process item while status is {item.status.value}.",
            )
            session.commit()
            return None, None, None

        job.attempt_count += 1
        if job.attempt_count > job.max_attempts:
            _mark_job_failed(session, job, item, "Maximum approval attempts exceeded.")
            session.commit()
            return None, None, None

        job.status = BackgroundJobStatus.RUNNING
        job.error_message = None
        job.started_at = job.started_at or now
        session.add(
            _audit_log(
                job,
                actions.JOB_STARTED,
                {
                    "attempt_count": job.attempt_count,
                    "task_name": job.task_name,
                    "worker_log_event": "approval_job_started",
                },
            )
        )
        session.commit()
        logger.info(
            "Approval job marked RUNNING job_id=%s work_item_id=%s attempt=%s",
            job.id,
            item.id,
            job.attempt_count,
        )
        return item.approved_draft_snapshot, item.lead_email, item.id


def _complete_processing(
    job_id: UUID,
    email_metadata: dict,
    crm_metadata: dict,
) -> BackgroundJobStatus:
    now = datetime.now(UTC)
    with sync_session_factory() as session:
        job = session.scalar(
            select(BackgroundJob).where(BackgroundJob.id == job_id).with_for_update()
        )
        if job is None:
            return BackgroundJobStatus.FAILED
        item = session.scalar(
            select(LeadWorkItem).where(LeadWorkItem.id == job.work_item_id).with_for_update()
        )
        if item is None:
            _mark_job_failed(session, job, None, "Work item no longer exists.")
            session.commit()
            return BackgroundJobStatus.FAILED
        if item.status == WorkItemStatus.SENT:
            job.status = BackgroundJobStatus.COMPLETED
            job.completed_at = job.completed_at or now
            session.commit()
            return BackgroundJobStatus.COMPLETED
        if item.status != WorkItemStatus.PROCESSING:
            _mark_job_failed(
                session,
                job,
                item,
                f"Cannot complete item while status is {item.status.value}.",
            )
            session.commit()
            return BackgroundJobStatus.FAILED

        item.status = WorkItemStatus.SENT
        item.sent_at = now
        item.version += 1
        job.status = BackgroundJobStatus.COMPLETED
        job.completed_at = now
        session.add(
            _audit_log(
                job,
                actions.JOB_COMPLETED,
                {
                    "approved_draft_snapshot_used": True,
                    "email": email_metadata,
                    "crm": crm_metadata,
                    "worker_log_event": "approval_job_completed",
                },
            )
        )
        session.commit()
        return BackgroundJobStatus.COMPLETED


def _record_processing_error(job_id: UUID, exc: Exception) -> BackgroundJobStatus:
    error_message = str(exc)[:500] or "Approval processing failed."
    with sync_session_factory() as session:
        job = session.scalar(
            select(BackgroundJob).where(BackgroundJob.id == job_id).with_for_update()
        )
        if job is None:
            return BackgroundJobStatus.FAILED
        item = session.scalar(
            select(LeadWorkItem).where(LeadWorkItem.id == job.work_item_id).with_for_update()
        )
        job.error_message = error_message
        if item is None or job.attempt_count >= job.max_attempts:
            _mark_job_failed(session, job, item, error_message)
            session.commit()
            return BackgroundJobStatus.FAILED

        job.status = BackgroundJobStatus.QUEUED
        session.commit()
        logger.info(
            "Approval processing queued for retry job_id=%s error=%s",
            job_id,
            error_message,
        )
        raise ApprovalProcessingError(error_message)


def _mark_job_failed(
    session,
    job: BackgroundJob,
    item: LeadWorkItem | None,
    error_message: str,
) -> None:
    now = datetime.now(UTC)
    job.status = BackgroundJobStatus.FAILED
    job.error_message = error_message[:500]
    job.completed_at = now
    if item is not None and item.status == WorkItemStatus.PROCESSING:
        item.status = WorkItemStatus.FAILED
        item.version += 1
    session.add(
        _audit_log(
            job,
            actions.JOB_FAILED,
            {
                "error_message": job.error_message,
                "attempt_count": job.attempt_count,
                "task_name": job.task_name,
                "worker_log_event": "approval_job_failed",
            },
        )
    )
    logger.error(
        "Approval job marked FAILED job_id=%s work_item_id=%s error=%s",
        job.id,
        job.work_item_id,
        job.error_message,
    )


def _audit_log(job: BackgroundJob, action: str, metadata: dict) -> AuditLog:
    return AuditLog(
        organization_id=job.organization_id,
        work_item_id=job.work_item_id,
        actor_user_id=None,
        action=action,
        metadata_json={"job_id": str(job.id), **metadata},
    )


def _fake_email_send(lead_email: str, approved_draft_snapshot: str) -> dict:
    settings = get_settings()
    if settings.approval_worker_failure_mode == "email":
        raise RuntimeError("Fake email send failed.")
    body_hash = sha256(approved_draft_snapshot.encode()).hexdigest()
    return {
        "email_send_simulated": True,
        "message_id": f"fake-email-{body_hash[:12]}",
        "to": lead_email,
        "body_sha256": body_hash,
    }


def _fake_crm_sync(work_item_id: UUID, approved_draft_snapshot: str) -> dict:
    settings = get_settings()
    if settings.approval_worker_failure_mode == "crm":
        raise RuntimeError("Fake CRM sync failed.")
    return {
        "crm_sync_simulated": True,
        "crm_activity_created": True,
        "activity_id": f"fake-crm-{str(work_item_id)[:8]}",
        "draft_length": len(approved_draft_snapshot),
    }


def _job_status(job_id: UUID) -> BackgroundJobStatus:
    with sync_session_factory() as session:
        job = session.get(BackgroundJob, job_id)
        return job.status if job else BackgroundJobStatus.FAILED
