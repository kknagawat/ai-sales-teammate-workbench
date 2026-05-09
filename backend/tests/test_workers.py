from datetime import UTC, datetime
from hashlib import sha256

import pytest
from sqlalchemy import select

from app.audit import actions
from app.db.sync_session import sync_session_factory
from app.models.audit_log import AuditLog
from app.models.background_job import BackgroundJob
from app.models.enums import BackgroundJobStatus, WorkItemStatus
from app.models.lead_work_item import LeadWorkItem
from app.workers.approvals import ApprovalProcessingError, process_approval, process_approval_job
from app.workers.celery_app import celery_app
from app.workers.logging import WORKER_LOG_FILE, configure_worker_file_logging


def _prepare_worker_log() -> None:
    WORKER_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    WORKER_LOG_FILE.write_text("", encoding="utf-8")
    configure_worker_file_logging()


def _create_processing_job(
    *,
    max_attempts: int = 3,
    snapshot: str = "Subject: Approved\n\nApproved snapshot body.",
) -> tuple:
    with sync_session_factory() as session:
        item = session.scalar(
            select(LeadWorkItem)
            .where(LeadWorkItem.status == WorkItemStatus.PENDING_REVIEW)
            .order_by(LeadWorkItem.created_at.desc())
        )
        assert item is not None
        item.status = WorkItemStatus.PROCESSING
        item.approved_draft_snapshot = snapshot
        item.final_draft = "Subject: Live Draft\n\nThis should not be sent."
        item.approved_at = datetime.now(UTC)
        item.version += 1
        job = BackgroundJob(
            organization_id=item.organization_id,
            work_item_id=item.id,
            task_name="process_approval",
            status=BackgroundJobStatus.QUEUED,
            max_attempts=max_attempts,
        )
        session.add(job)
        session.commit()
        return item.id, job.id, snapshot, item.version


def test_process_approval_job_moves_item_to_sent_and_uses_snapshot(seeded_database) -> None:
    item_id, job_id, snapshot, starting_version = _create_processing_job()
    _prepare_worker_log()

    status = process_approval_job(job_id, celery_task_id="celery-test-1")

    with sync_session_factory() as session:
        item = session.get(LeadWorkItem, item_id)
        job = session.get(BackgroundJob, job_id)
        completed_log = session.scalar(
            select(AuditLog).where(
                AuditLog.work_item_id == item_id,
                AuditLog.action == actions.JOB_COMPLETED,
            )
        )

    assert status == BackgroundJobStatus.COMPLETED
    assert item is not None
    assert item.status == WorkItemStatus.SENT
    assert item.sent_at is not None
    assert item.version == starting_version + 1
    assert job is not None
    assert job.status == BackgroundJobStatus.COMPLETED
    assert job.celery_task_id == "celery-test-1"
    assert completed_log is not None
    assert completed_log.metadata_json["approved_draft_snapshot_used"] is True
    assert completed_log.metadata_json["email"]["email_send_simulated"] is True
    assert completed_log.metadata_json["email"]["body_sha256"] == sha256(
        snapshot.encode()
    ).hexdigest()
    assert completed_log.metadata_json["crm"]["crm_sync_simulated"] is True
    assert completed_log.metadata_json["crm"]["crm_activity_created"] is True
    assert completed_log.actor_user_id is None
    assert WORKER_LOG_FILE.exists()
    worker_log_text = WORKER_LOG_FILE.read_text(encoding="utf-8")
    assert "Approval processing started" in worker_log_text
    assert "Approval job marked RUNNING" in worker_log_text
    assert "Fake email send simulated" in worker_log_text
    assert "Fake CRM sync/activity simulated" in worker_log_text
    assert "Approval processing completed" in worker_log_text
    assert snapshot not in worker_log_text


def test_process_approval_celery_task_runs_eagerly(seeded_database) -> None:
    item_id, job_id, _snapshot, _starting_version = _create_processing_job()
    _prepare_worker_log()
    previous = {
        "task_always_eager": celery_app.conf.task_always_eager,
        "task_eager_propagates": celery_app.conf.task_eager_propagates,
    }
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    try:
        result = process_approval.delay(str(job_id))
    finally:
        celery_app.conf.update(**previous)

    with sync_session_factory() as session:
        item = session.get(LeadWorkItem, item_id)
        job = session.get(BackgroundJob, job_id)

    assert result.get() == "COMPLETED"
    assert item is not None
    assert item.status == WorkItemStatus.SENT
    assert job is not None
    assert job.status == BackgroundJobStatus.COMPLETED
    worker_log_text = WORKER_LOG_FILE.read_text(encoding="utf-8")
    assert "Approval task received" in worker_log_text
    assert "Approval processing completed" in worker_log_text


def test_completed_job_does_not_double_send(seeded_database, monkeypatch) -> None:
    item_id, job_id, _snapshot, _starting_version = _create_processing_job()

    first_status = process_approval_job(job_id, celery_task_id="celery-test-1")
    with sync_session_factory() as session:
        item_after_first = session.get(LeadWorkItem, item_id)
        assert item_after_first is not None
        sent_version = item_after_first.version

    def fail_if_called(*args, **kwargs):
        raise AssertionError("completed job should not send again")

    monkeypatch.setattr("app.workers.approvals._fake_email_send", fail_if_called)
    second_status = process_approval_job(job_id, celery_task_id="celery-test-2")

    with sync_session_factory() as session:
        item_after_second = session.get(LeadWorkItem, item_id)
        job_after_second = session.get(BackgroundJob, job_id)

    assert first_status == BackgroundJobStatus.COMPLETED
    assert second_status == BackgroundJobStatus.COMPLETED
    assert item_after_second is not None
    assert item_after_second.version == sent_version
    assert job_after_second is not None
    assert job_after_second.status == BackgroundJobStatus.COMPLETED


def test_process_approval_job_records_final_failure(seeded_database, monkeypatch) -> None:
    item_id, job_id, _snapshot, _starting_version = _create_processing_job(max_attempts=1)

    def fail_email(*args, **kwargs):
        raise RuntimeError("email transport down")

    monkeypatch.setattr("app.workers.approvals._fake_email_send", fail_email)

    status = process_approval_job(job_id, celery_task_id="celery-test-fail")

    with sync_session_factory() as session:
        item = session.get(LeadWorkItem, item_id)
        job = session.get(BackgroundJob, job_id)
        failed_log = session.scalar(
            select(AuditLog).where(
                AuditLog.work_item_id == item_id,
                AuditLog.action == actions.JOB_FAILED,
            )
        )

    assert status == BackgroundJobStatus.FAILED
    assert item is not None
    assert item.status == WorkItemStatus.FAILED
    assert job is not None
    assert job.status == BackgroundJobStatus.FAILED
    assert "email transport down" in (job.error_message or "")
    assert failed_log is not None
    assert failed_log.metadata_json["attempt_count"] == 1


def test_process_approval_job_requeues_retryable_failure(seeded_database, monkeypatch) -> None:
    _item_id, job_id, _snapshot, _starting_version = _create_processing_job(max_attempts=3)

    def fail_email(*args, **kwargs):
        raise RuntimeError("temporary email outage")

    monkeypatch.setattr("app.workers.approvals._fake_email_send", fail_email)

    with pytest.raises(ApprovalProcessingError):
        process_approval_job(job_id, celery_task_id="celery-test-retry")

    with sync_session_factory() as session:
        job = session.get(BackgroundJob, job_id)

    assert job is not None
    assert job.status == BackgroundJobStatus.QUEUED
    assert job.attempt_count == 1
    assert "temporary email outage" in (job.error_message or "")
