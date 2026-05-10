from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.sync_session import sync_session_factory
from app.main import app
from app.models.background_job import BackgroundJob
from app.models.enums import BackgroundJobStatus, LLMRunStatus, WorkItemStatus
from app.models.lead_work_item import LeadWorkItem
from app.models.user import User
from app.work_items.state_machine import WorkItemAction, can_perform_action, can_transition


@pytest.fixture(autouse=True)
def fake_approval_enqueue(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.work_items.enqueue_process_approval",
        lambda job_id: "celery-test-task-id",
    )


def _login(client: TestClient, email: str, password: str = "ReviewerPass123!") -> None:
    client.headers.update({"Origin": "http://localhost:3000"})
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


def _first_item_for_user(email: str, status: WorkItemStatus | None = None) -> LeadWorkItem:
    with sync_session_factory() as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        stmt = select(LeadWorkItem).where(LeadWorkItem.assigned_reviewer_id == user.id)
        if status is not None:
            stmt = stmt.where(LeadWorkItem.status == status)
        item = session.scalar(stmt.order_by(LeadWorkItem.created_at.desc()))
        assert item is not None
        session.expunge(item)
        return item


def _item_not_assigned_to(email: str) -> LeadWorkItem:
    with sync_session_factory() as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        item = session.scalar(
            select(LeadWorkItem)
            .where(
                LeadWorkItem.organization_id == user.organization_id,
                LeadWorkItem.assigned_reviewer_id != user.id,
            )
            .order_by(LeadWorkItem.created_at.desc())
        )
        assert item is not None
        session.expunge(item)
        return item


def _set_item_status(item_id, status: WorkItemStatus) -> LeadWorkItem:
    with sync_session_factory() as session:
        item = session.get(LeadWorkItem, item_id)
        assert item is not None
        item.status = status
        session.commit()
        session.refresh(item)
        session.expunge(item)
        return item


def _make_processing_item(
    email: str = "reviewer@acme.example",
    *,
    with_job: bool = False,
    job_status: BackgroundJobStatus = BackgroundJobStatus.RUNNING,
    stale: bool = False,
) -> LeadWorkItem:
    with sync_session_factory() as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        item = session.scalar(
            select(LeadWorkItem)
            .where(
                LeadWorkItem.assigned_reviewer_id == user.id,
                LeadWorkItem.status == WorkItemStatus.PENDING_REVIEW,
            )
            .order_by(LeadWorkItem.created_at.desc())
        )
        assert item is not None
        item.status = WorkItemStatus.PROCESSING
        item.approved_draft_snapshot = item.final_draft
        item.approved_by_user_id = user.id
        item.approved_at = datetime.now(UTC)
        item.version += 1
        if with_job:
            reference_time = (
                datetime.now(UTC) - timedelta(minutes=10)
                if stale
                else datetime.now(UTC)
            )
            started_at = (
                reference_time
                if job_status == BackgroundJobStatus.RUNNING
                else None
            )
            session.add(
                BackgroundJob(
                    organization_id=item.organization_id,
                    work_item_id=item.id,
                    task_name="process_approval",
                    status=job_status,
                    started_at=started_at,
                    completed_at=None,
                )
            )
        session.commit()
        session.refresh(item)
        session.expunge(item)
        return item


def test_reviewer_queue_only_returns_assigned_items(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")

    response = client.get("/work-items")

    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    assert all(item["assigned_reviewer"]["email"] == "reviewer@acme.example" for item in items)


def test_reviewer_cannot_access_unassigned_same_org_item(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _item_not_assigned_to("reviewer@acme.example")

    response = client.get(f"/work-items/{item.id}")

    assert response.status_code == 404


def test_admin_can_access_all_org_items_and_admin_endpoints(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "admin@acme.example", "AdminPass123!")

    response = client.get("/admin/work-items")
    users_response = client.get("/admin/users")

    assert response.status_code == 200
    assert len(response.json()["items"]) == 8
    assert users_response.status_code == 200
    assert len(users_response.json()["items"]) == 4


def test_cross_org_access_returns_404(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    globex_item = _first_item_for_user("reviewer@globex.example")

    response = client.get(f"/work-items/{globex_item.id}")

    assert response.status_code == 404


def test_save_draft_updates_version_and_audit(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    response = client.patch(
        f"/work-items/{item.id}/draft",
        json={"final_draft": "Subject: Updated\n\nUpdated body", "last_seen_version": item.version},
    )
    audit_response = client.get(f"/work-items/{item.id}/audit")

    assert response.status_code == 200
    assert response.json()["version"] == item.version + 1
    assert audit_response.status_code == 200
    assert any(log["action"] == "DRAFT_EDITED" for log in audit_response.json()["items"])


def test_mutation_rejects_foreign_origin(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    response = client.patch(
        f"/work-items/{item.id}/draft",
        json={"final_draft": "Subject: Origin\n\nBody", "last_seen_version": item.version},
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403


def test_mutation_rejects_missing_origin(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    client.headers.pop("origin", None)
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    response = client.patch(
        f"/work-items/{item.id}/draft",
        json={"final_draft": "Subject: Missing Origin\n\nBody", "last_seen_version": item.version},
    )

    assert response.status_code == 403


def test_audit_uses_forwarded_client_ip(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    response = client.patch(
        f"/work-items/{item.id}/draft",
        json={"final_draft": "Subject: Forwarded\n\nBody", "last_seen_version": item.version},
        headers={
            "Origin": "http://localhost:3000",
            "X-Forwarded-For": "203.0.113.7, 10.0.0.1",
        },
    )
    audit_response = client.get(f"/work-items/{item.id}/audit")

    assert response.status_code == 200
    edited = next(log for log in audit_response.json()["items"] if log["action"] == "DRAFT_EDITED")
    assert edited["ip_address"] == "203.0.113.7"


def test_stale_mutation_returns_409(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    response = client.patch(
        f"/work-items/{item.id}/draft",
        json={"final_draft": "Subject: Stale\n\nBody", "last_seen_version": item.version + 1},
    )

    assert response.status_code == 409


def test_mutation_rejects_extra_fields(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    response = client.patch(
        f"/work-items/{item.id}/draft",
        json={
            "final_draft": "Subject: Extra\n\nBody",
            "last_seen_version": item.version,
            "role": "ADMIN",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_approve_creates_processing_job_and_is_idempotent(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)
    key = str(uuid4())
    payload = {"last_seen_version": item.version, "reviewer_note": "Looks good."}

    response = client.post(
        f"/work-items/{item.id}/approve",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    repeat = client.post(
        f"/work-items/{item.id}/approve",
        json=payload,
        headers={"Idempotency-Key": key},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "PROCESSING"
    assert len(response.json()["background_jobs"]) == 1
    assert repeat.status_code == 200
    assert repeat.json()["status"] == "PROCESSING"


def test_approve_enqueues_processing_job(seeded_database, monkeypatch) -> None:
    enqueued_job_ids = []

    def fake_enqueue(job_id):
        enqueued_job_ids.append(job_id)
        return "celery-test-task-id"

    monkeypatch.setattr("app.api.routes.work_items.enqueue_process_approval", fake_enqueue)
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    response = client.post(
        f"/work-items/{item.id}/approve",
        json={"last_seen_version": item.version},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 200
    assert len(enqueued_job_ids) == 1
    with sync_session_factory() as session:
        job = session.get(BackgroundJob, enqueued_job_ids[0])
        assert job is not None
        assert job.celery_task_id == "celery-test-task-id"


def test_approve_marks_item_failed_when_enqueue_fails(seeded_database, monkeypatch) -> None:
    def fail_enqueue(job_id):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr("app.api.routes.work_items.enqueue_process_approval", fail_enqueue)
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    response = client.post(
        f"/work-items/{item.id}/approve",
        json={"last_seen_version": item.version},
        headers={"Idempotency-Key": str(uuid4())},
    )
    audit_response = client.get(f"/work-items/{item.id}/audit")

    assert response.status_code == 200
    assert response.json()["status"] == "FAILED"
    assert response.json()["background_jobs"][0]["status"] == "FAILED"
    assert "redis unavailable" in response.json()["background_jobs"][0]["error_message"]
    failed_log = next(
        log for log in audit_response.json()["items"] if log["action"] == "JOB_FAILED"
    )
    assert failed_log["actor_user_id"] is None
    assert failed_log["metadata"]["phase"] == "enqueue"


def test_failed_item_can_be_retried(seeded_database, monkeypatch) -> None:
    def fail_enqueue(job_id):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr("app.api.routes.work_items.enqueue_process_approval", fail_enqueue)
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)
    failed = client.post(
        f"/work-items/{item.id}/approve",
        json={"last_seen_version": item.version},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "FAILED"

    monkeypatch.setattr(
        "app.api.routes.work_items.enqueue_process_approval",
        lambda job_id: "retry-celery-task-id",
    )
    retry = client.post(
        f"/work-items/{item.id}/retry-processing",
        json={"last_seen_version": failed.json()["version"]},
    )

    assert retry.status_code == 200
    assert retry.json()["status"] == "PROCESSING"
    assert retry.json()["background_jobs"][0]["status"] == "QUEUED"
    assert retry.json()["background_jobs"][1]["status"] == "FAILED"


def test_retry_processing_recovers_missing_active_job(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _make_processing_item()

    response = client.post(
        f"/work-items/{item.id}/retry-processing",
        json={"last_seen_version": item.version, "reviewer_note": "Recover missing job."},
    )
    audit_response = client.get(f"/work-items/{item.id}/audit")

    assert response.status_code == 200
    assert response.json()["status"] == "PROCESSING"
    assert response.json()["background_jobs"][0]["status"] == "QUEUED"
    assert any(
        log["action"] == "JOB_FAILED"
        and log["metadata"]["phase"] == "missing_job_recovery"
        for log in audit_response.json()["items"]
    )


def test_retry_processing_recovers_stale_active_job(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _make_processing_item(with_job=True, stale=True)

    response = client.post(
        f"/work-items/{item.id}/retry-processing",
        json={"last_seen_version": item.version},
    )
    audit_response = client.get(f"/work-items/{item.id}/audit")

    assert response.status_code == 200
    assert response.json()["status"] == "PROCESSING"
    assert response.json()["background_jobs"][0]["status"] == "QUEUED"
    assert response.json()["background_jobs"][1]["status"] == "FAILED"
    assert any(
        log["action"] == "JOB_FAILED"
        and log["metadata"]["phase"] == "stale_job_recovery"
        for log in audit_response.json()["items"]
    )


def test_retry_processing_rejects_fresh_active_job(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _make_processing_item(with_job=True, stale=False)

    response = client.post(
        f"/work-items/{item.id}/retry-processing",
        json={"last_seen_version": item.version},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ACTIVE_PROCESSING_JOB"


def test_state_machine_allows_retry_processing_for_processing_recovery() -> None:
    assert can_perform_action(WorkItemStatus.PROCESSING, WorkItemAction.RETRY_PROCESSING)


def test_state_machine_allows_reopening_rejected_items() -> None:
    assert can_perform_action(WorkItemStatus.REJECTED, WorkItemAction.REOPEN)
    assert can_transition(WorkItemStatus.REJECTED, WorkItemStatus.PENDING_REVIEW)


def test_approve_requires_idempotency_key(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    response = client.post(
        f"/work-items/{item.id}/approve",
        json={"last_seen_version": item.version},
    )

    assert response.status_code == 400


def test_approve_rejects_idempotency_key_reused_with_different_payload(
    seeded_database,
) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)
    key = str(uuid4())

    first = client.post(
        f"/work-items/{item.id}/approve",
        json={"last_seen_version": item.version, "reviewer_note": "first"},
        headers={"Idempotency-Key": key},
    )
    second = client.post(
        f"/work-items/{item.id}/approve",
        json={"last_seen_version": item.version, "reviewer_note": "changed"},
        headers={"Idempotency-Key": key},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_idempotent_approve_replay_returns_current_state(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)
    key = str(uuid4())
    payload = {"last_seen_version": item.version, "reviewer_note": "Looks good."}

    first = client.post(
        f"/work-items/{item.id}/approve",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    with sync_session_factory() as session:
        current = session.get(LeadWorkItem, item.id)
        assert current is not None
        current.status = WorkItemStatus.SENT
        current.version += 1
        session.commit()

    replay = client.post(
        f"/work-items/{item.id}/approve",
        json=payload,
        headers={"Idempotency-Key": key},
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["status"] == "SENT"


def test_approve_rejects_active_processing_job(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)
    with sync_session_factory() as session:
        session.add(
            BackgroundJob(
                organization_id=item.organization_id,
                work_item_id=item.id,
                task_name="process_approval",
                status=BackgroundJobStatus.QUEUED,
            )
        )
        session.commit()

    response = client.post(
        f"/work-items/{item.id}/approve",
        json={"last_seen_version": item.version},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ACTIVE_PROCESSING_JOB"


def test_admin_approval_override_is_audited(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "admin@acme.example", "AdminPass123!")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    response = client.post(
        f"/work-items/{item.id}/approve",
        json={"last_seen_version": item.version},
        headers={"Idempotency-Key": str(uuid4())},
    )
    audit_response = client.get(f"/work-items/{item.id}/audit")

    assert response.status_code == 200
    approved = next(
        log for log in audit_response.json()["items"] if log["action"] == "ITEM_APPROVED"
    )
    assert approved["metadata"]["override"] is True
    assert approved["metadata"]["originally_assigned_to"] == str(item.assigned_reviewer_id)


def test_invalid_state_actions_return_409(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)
    sent_item = _set_item_status(item.id, WorkItemStatus.SENT)

    approve_response = client.post(
        f"/work-items/{sent_item.id}/approve",
        json={"last_seen_version": sent_item.version},
        headers={"Idempotency-Key": str(uuid4())},
    )
    edit_response = client.patch(
        f"/work-items/{sent_item.id}/draft",
        json={"final_draft": "Subject: Sent\n\nBody", "last_seen_version": sent_item.version},
    )

    assert approve_response.status_code == 409
    assert approve_response.json()["detail"]["code"] == "INVALID_ACTION"
    assert edit_response.status_code == 409
    assert edit_response.json()["detail"]["code"] == "INVALID_ACTION"


def test_regenerate_adds_llm_run_and_returns_pending(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    response = client.post(
        f"/work-items/{item.id}/regenerate",
        json={"last_seen_version": item.version, "reviewer_feedback": "Tighter CTA please."},
    )
    runs_response = client.get(f"/work-items/{item.id}/llm-runs")

    assert response.status_code == 200
    assert response.json()["status"] == "PENDING_REVIEW"
    assert response.json()["regeneration_count"] == item.regeneration_count + 1
    assert runs_response.status_code == 200
    run = runs_response.json()["items"][0]
    assert run["request_type"] == "REGENERATION"
    assert run["provider"] == "mock"
    assert run["model"] == "mock-sales-followup-v1"
    assert run["decision_trace"]["selected_strategy"]
    assert run["structured_output"]["quality_checks"]["has_clear_cta"] is True
    assert run["latency_ms"] is not None
    assert run["token_usage"]["input_tokens"] > 0
    assert "I also incorporated this reviewer feedback" not in response.json()["final_draft"]
    assert "Tighter CTA please." not in response.json()["final_draft"]


def test_regeneration_failure_restores_pending_and_records_failed_run(
    seeded_database,
    monkeypatch,
) -> None:
    async def fail_generation(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("app.llm.providers.mock.MockLLMProvider.generate_followup", fail_generation)
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    response = client.post(
        f"/work-items/{item.id}/regenerate",
        json={"last_seen_version": item.version, "reviewer_feedback": "Try again."},
    )
    detail_response = client.get(f"/work-items/{item.id}")
    runs_response = client.get(f"/work-items/{item.id}/llm-runs")
    audit_response = client.get(f"/work-items/{item.id}/audit")

    assert response.status_code == 502
    assert detail_response.json()["status"] == "PENDING_REVIEW"
    assert runs_response.json()["items"][0]["status"] == LLMRunStatus.FAILED
    assert any(
        log["action"] == "DRAFT_REGENERATION_FAILED"
        for log in audit_response.json()["items"]
    )


def test_regeneration_state_change_returns_409(seeded_database, monkeypatch) -> None:
    from app.llm.providers.mock import MockLLMProvider

    original_generate_followup = MockLLMProvider.generate_followup

    async def change_state_during_provider_call(self, context):
        with sync_session_factory() as session:
            item = session.get(LeadWorkItem, context.work_item_id)
            assert item is not None
            item.status = WorkItemStatus.PENDING_REVIEW
            session.commit()
        return await original_generate_followup(self, context)

    monkeypatch.setattr(
        "app.llm.providers.mock.MockLLMProvider.generate_followup",
        change_state_during_provider_call,
    )
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    response = client.post(
        f"/work-items/{item.id}/regenerate",
        json={"last_seen_version": item.version, "reviewer_feedback": "Try again."},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REGENERATION_STATE_CHANGED"


def test_reject_moves_item_to_rejected(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    response = client.post(
        f"/work-items/{item.id}/reject",
        json={"last_seen_version": item.version, "reviewer_note": "Not relevant."},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"


def test_reopen_rejected_item_returns_it_to_pending_review(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")
    item = _first_item_for_user("reviewer@acme.example", WorkItemStatus.PENDING_REVIEW)

    rejected = client.post(
        f"/work-items/{item.id}/reject",
        json={"last_seen_version": item.version, "reviewer_note": "Needs another pass."},
    )
    reopened = client.post(
        f"/work-items/{item.id}/reopen",
        json={
            "last_seen_version": rejected.json()["version"],
            "reviewer_note": "Reopened after reviewer reconsidered.",
        },
    )
    edit = client.patch(
        f"/work-items/{item.id}/draft",
        json={
            "last_seen_version": reopened.json()["version"],
            "final_draft": "Subject: Reopened\n\nUpdated draft",
        },
    )
    audit_response = client.get(f"/work-items/{item.id}/audit")

    assert rejected.status_code == 200
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "PENDING_REVIEW"
    assert edit.status_code == 200
    assert edit.json()["final_draft"] == "Subject: Reopened\n\nUpdated draft"
    assert any(log["action"] == "ITEM_REOPENED" for log in audit_response.json()["items"])


def test_non_admin_cannot_access_admin_endpoints(seeded_database) -> None:
    client = TestClient(app)
    _login(client, "reviewer@acme.example")

    response = client.get("/admin/users")

    assert response.status_code == 403
