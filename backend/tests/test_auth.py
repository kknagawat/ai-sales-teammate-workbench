import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth.rate_limit import login_rate_limiter, signup_rate_limiter
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.sync_session import sync_session_factory
from app.main import app
from app.models.enums import UserRole, WorkItemStatus
from app.models.lead_work_item import LeadWorkItem
from app.models.llm_generation_run import LLMGenerationRun
from app.models.organization import Organization
from app.models.user import User


def _client() -> TestClient:
    client = TestClient(app)
    client.headers.update({"Origin": "http://localhost:3000"})
    return client


def test_login_me_logout_flow(seeded_database) -> None:
    client = _client()

    login_response = client.post(
        "/auth/login",
        json={
            "email": "reviewer@acme.example",
            "password": "ReviewerPass123!",
        },
    )

    assert login_response.status_code == 200
    assert login_response.json()["user"]["email"] == "reviewer@acme.example"
    assert get_settings().auth_cookie_name in client.cookies
    assert "httponly" in login_response.headers["set-cookie"].lower()

    me_response = client.get("/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["user"]["role"] == "REVIEWER"

    logout_response = client.post("/auth/logout")
    assert logout_response.status_code == 204
    assert get_settings().auth_cookie_name not in client.cookies

    logged_out_response = client.get("/auth/me")
    assert logged_out_response.status_code == 401


def test_signup_creates_new_organization_admin_and_logs_in(seeded_database) -> None:
    client = _client()

    response = client.post(
        "/auth/signup",
        json={
            "mode": "CREATE_ORG_ADMIN",
            "organization_name": "Northwind Revenue",
            "organization_slug": "Northwind-Revenue",
            "name": "Nora Admin",
            "email": "nora.admin@example.com",
            "password": "StrongPass123!",
        },
    )
    me_response = client.get("/auth/me")

    assert response.status_code == 201, response.text
    assert response.json()["user"]["role"] == "ADMIN"
    assert response.json()["user"]["email"] == "nora.admin@example.com"
    assert get_settings().auth_cookie_name in client.cookies
    assert "httponly" in response.headers["set-cookie"].lower()
    assert me_response.status_code == 200
    with sync_session_factory() as session:
        org = session.scalar(select(Organization).where(Organization.slug == "northwind-revenue"))
        assert org is not None
        user = session.scalar(
            select(User).where(
                User.organization_id == org.id,
                User.email == "nora.admin@example.com",
            )
        )
        assert user is not None
        assert user.role == UserRole.ADMIN
        item_count = session.scalar(
            select(func.count())
            .select_from(LeadWorkItem)
            .where(LeadWorkItem.organization_id == org.id)
        )
        assigned_item_count = session.scalar(
            select(func.count())
            .select_from(LeadWorkItem)
            .where(
                LeadWorkItem.organization_id == org.id,
                LeadWorkItem.assigned_reviewer_id.is_not(None),
            )
        )
        run_count = session.scalar(
            select(func.count())
            .select_from(LLMGenerationRun)
            .join(LeadWorkItem, LLMGenerationRun.work_item_id == LeadWorkItem.id)
            .where(LeadWorkItem.organization_id == org.id)
        )
        assert item_count == 5
        assert assigned_item_count == 0
        assert run_count == 5


def test_signup_demo_data_can_be_disabled(seeded_database, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "signup_demo_data_enabled", False)
    client = _client()

    response = client.post(
        "/auth/signup",
        json={
            "mode": "CREATE_ORG_ADMIN",
            "organization_name": "No Demo Co",
            "organization_slug": "no-demo-co",
            "name": "No Demo Admin",
            "email": "no.demo.admin@example.com",
            "password": "StrongPass123!",
        },
    )

    assert response.status_code == 201, response.text
    with sync_session_factory() as session:
        org = session.scalar(select(Organization).where(Organization.slug == "no-demo-co"))
        assert org is not None
        item_count = session.scalar(
            select(func.count())
            .select_from(LeadWorkItem)
            .where(LeadWorkItem.organization_id == org.id)
        )
        assert item_count == 0


def test_signup_reviewer_joins_existing_org_with_invite_code(seeded_database) -> None:
    admin_client = _client()
    admin_response = admin_client.post(
        "/auth/signup",
        json={
            "mode": "CREATE_ORG_ADMIN",
            "organization_name": "Shared Demo Co",
            "organization_slug": "shared-demo-co",
            "name": "Shared Admin",
            "email": "shared.admin@example.com",
            "password": "StrongPass123!",
        },
    )
    assert admin_response.status_code == 201, admin_response.text

    with sync_session_factory() as session:
        org = session.scalar(select(Organization).where(Organization.slug == "shared-demo-co"))
        assert org is not None
        original_items = list(
            session.scalars(
                select(LeadWorkItem)
                .where(LeadWorkItem.organization_id == org.id)
                .order_by(LeadWorkItem.created_at.asc())
            )
        )
        assert len(original_items) == 5
        sent_item = original_items[0]
        sent_item.status = WorkItemStatus.SENT
        original_item_ids = {item.id for item in original_items}
        sent_item_id = sent_item.id
        sent_item_email = sent_item.lead_email
        before_count = len(original_items)
        session.commit()

    client = _client()
    response = client.post(
        "/auth/signup",
        json={
            "mode": "JOIN_ORG_REVIEWER",
            "organization_slug": "shared-demo-co",
            "invite_code": "demo-reviewer-code",
            "name": "New Reviewer",
            "email": "new.reviewer@shared-demo.example",
            "password": "StrongPass123!",
        },
    )
    queue_response = client.get("/work-items")

    assert response.status_code == 201, response.text
    assert response.json()["user"]["role"] == "REVIEWER"
    assert queue_response.status_code == 200
    with sync_session_factory() as session:
        org = session.scalar(select(Organization).where(Organization.slug == "shared-demo-co"))
        assert org is not None
        user = session.scalar(
            select(User).where(
                User.organization_id == org.id,
                User.email == "new.reviewer@shared-demo.example",
            )
        )
        assert user is not None
        assert user.role == UserRole.REVIEWER
        after_count = session.scalar(
            select(func.count())
            .select_from(LeadWorkItem)
            .where(LeadWorkItem.organization_id == org.id)
        )
        assigned_items = list(
            session.scalars(
                select(LeadWorkItem).where(
                    LeadWorkItem.organization_id == org.id,
                    LeadWorkItem.assigned_reviewer_id == user.id,
                )
            )
        )
        duplicate_lead_count = session.scalar(
            select(func.count())
            .select_from(LeadWorkItem)
            .where(
                LeadWorkItem.organization_id == org.id,
                LeadWorkItem.lead_email == sent_item_email,
            )
        )
        sent_item_after_signup = session.get(LeadWorkItem, sent_item_id)
        assert after_count == before_count
        assert {item.id for item in assigned_items} == original_item_ids
        assert sent_item_after_signup is not None
        assert sent_item_after_signup.status == WorkItemStatus.SENT
        assert duplicate_lead_count == 1

    queue_items = queue_response.json()["items"]
    assert any(item["id"] == str(sent_item_id) and item["status"] == "SENT" for item in queue_items)


def test_second_signup_reviewer_does_not_steal_assigned_demo_items(seeded_database) -> None:
    admin_client = _client()
    admin_response = admin_client.post(
        "/auth/signup",
        json={
            "mode": "CREATE_ORG_ADMIN",
            "organization_name": "Stable Assignment Co",
            "organization_slug": "stable-assignment-co",
            "name": "Stable Admin",
            "email": "stable.admin@example.com",
            "password": "StrongPass123!",
        },
    )
    assert admin_response.status_code == 201, admin_response.text

    first_reviewer_client = _client()
    first_response = first_reviewer_client.post(
        "/auth/signup",
        json={
            "mode": "JOIN_ORG_REVIEWER",
            "organization_slug": "stable-assignment-co",
            "invite_code": "demo-reviewer-code",
            "name": "First Reviewer",
            "email": "first.reviewer@stable.example",
            "password": "StrongPass123!",
        },
    )
    second_reviewer_client = _client()
    second_response = second_reviewer_client.post(
        "/auth/signup",
        json={
            "mode": "JOIN_ORG_REVIEWER",
            "organization_slug": "stable-assignment-co",
            "invite_code": "demo-reviewer-code",
            "name": "Second Reviewer",
            "email": "second.reviewer@stable.example",
            "password": "StrongPass123!",
        },
    )

    assert first_response.status_code == 201, first_response.text
    assert second_response.status_code == 201, second_response.text
    with sync_session_factory() as session:
        org = session.scalar(
            select(Organization).where(Organization.slug == "stable-assignment-co")
        )
        assert org is not None
        first_reviewer = session.scalar(
            select(User).where(
                User.organization_id == org.id,
                User.email == "first.reviewer@stable.example",
            )
        )
        second_reviewer = session.scalar(
            select(User).where(
                User.organization_id == org.id,
                User.email == "second.reviewer@stable.example",
            )
        )
        assert first_reviewer is not None
        assert second_reviewer is not None
        first_assigned_count = session.scalar(
            select(func.count())
            .select_from(LeadWorkItem)
            .where(
                LeadWorkItem.organization_id == org.id,
                LeadWorkItem.assigned_reviewer_id == first_reviewer.id,
            )
        )
        second_assigned_count = session.scalar(
            select(func.count())
            .select_from(LeadWorkItem)
            .where(
                LeadWorkItem.organization_id == org.id,
                LeadWorkItem.assigned_reviewer_id == second_reviewer.id,
            )
        )
        total_item_count = session.scalar(
            select(func.count())
            .select_from(LeadWorkItem)
            .where(LeadWorkItem.organization_id == org.id)
        )

        assert first_assigned_count == 5
        assert second_assigned_count == 0
        assert total_item_count == 5


def test_signup_reviewer_repairs_old_admin_assigned_demo_items(seeded_database) -> None:
    admin_client = _client()
    admin_response = admin_client.post(
        "/auth/signup",
        json={
            "mode": "CREATE_ORG_ADMIN",
            "organization_name": "Legacy Demo Co",
            "organization_slug": "legacy-demo-co",
            "name": "Legacy Admin",
            "email": "legacy.admin@example.com",
            "password": "StrongPass123!",
        },
    )
    assert admin_response.status_code == 201, admin_response.text

    with sync_session_factory() as session:
        org = session.scalar(select(Organization).where(Organization.slug == "legacy-demo-co"))
        assert org is not None
        admin = session.scalar(
            select(User).where(
                User.organization_id == org.id,
                User.email == "legacy.admin@example.com",
            )
        )
        assert admin is not None
        demo_items = list(
            session.scalars(select(LeadWorkItem).where(LeadWorkItem.organization_id == org.id))
        )
        for item in demo_items:
            item.assigned_reviewer_id = admin.id
        session.commit()

    reviewer_client = _client()
    response = reviewer_client.post(
        "/auth/signup",
        json={
            "mode": "JOIN_ORG_REVIEWER",
            "organization_slug": "legacy-demo-co",
            "invite_code": "demo-reviewer-code",
            "name": "Legacy Reviewer",
            "email": "legacy.reviewer@example.com",
            "password": "StrongPass123!",
        },
    )

    assert response.status_code == 201, response.text
    with sync_session_factory() as session:
        org = session.scalar(select(Organization).where(Organization.slug == "legacy-demo-co"))
        assert org is not None
        reviewer = session.scalar(
            select(User).where(
                User.organization_id == org.id,
                User.email == "legacy.reviewer@example.com",
            )
        )
        assert reviewer is not None
        assigned_count = session.scalar(
            select(func.count())
            .select_from(LeadWorkItem)
            .where(
                LeadWorkItem.organization_id == org.id,
                LeadWorkItem.assigned_reviewer_id == reviewer.id,
            )
        )
        assert assigned_count == 5


def test_signup_reviewer_rejects_invalid_invite_code(seeded_database) -> None:
    client = _client()

    response = client.post(
        "/auth/signup",
        json={
            "mode": "JOIN_ORG_REVIEWER",
            "organization_slug": "acme",
            "invite_code": "wrong-code",
            "name": "New Reviewer",
            "email": "new.reviewer@acme.example",
            "password": "StrongPass123!",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid organization or invite code."


def test_signup_rejects_invalid_mode_field_combinations(seeded_database) -> None:
    client = _client()

    missing_org_name = client.post(
        "/auth/signup",
        json={
            "mode": "CREATE_ORG_ADMIN",
            "organization_slug": "missing-org-name",
            "name": "Missing Admin",
            "email": "missing.admin@example.com",
            "password": "StrongPass123!",
        },
    )
    admin_with_invite = client.post(
        "/auth/signup",
        json={
            "mode": "CREATE_ORG_ADMIN",
            "organization_name": "Admin Invite Co",
            "organization_slug": "admin-invite-co",
            "invite_code": "demo-reviewer-code",
            "name": "Admin Invite",
            "email": "admin.invite@example.com",
            "password": "StrongPass123!",
        },
    )
    reviewer_without_invite = client.post(
        "/auth/signup",
        json={
            "mode": "JOIN_ORG_REVIEWER",
            "organization_slug": "acme",
            "name": "Missing Invite",
            "email": "missing.invite@acme.example",
            "password": "StrongPass123!",
        },
    )

    assert missing_org_name.status_code == 422
    assert admin_with_invite.status_code == 422
    assert reviewer_without_invite.status_code == 422


def test_signup_rejects_duplicate_org_slug(seeded_database) -> None:
    client = _client()

    response = client.post(
        "/auth/signup",
        json={
            "mode": "CREATE_ORG_ADMIN",
            "organization_name": "Acme Duplicate",
            "organization_slug": "acme",
            "name": "Duplicate Admin",
            "email": "duplicate.admin@example.com",
            "password": "StrongPass123!",
        },
    )

    assert response.status_code == 409
    assert "Organization slug" in response.json()["detail"]


def test_signup_rejects_duplicate_email_in_same_org(seeded_database) -> None:
    client = _client()

    response = client.post(
        "/auth/signup",
        json={
            "mode": "JOIN_ORG_REVIEWER",
            "organization_slug": "acme",
            "invite_code": "demo-reviewer-code",
            "name": "Duplicate Reviewer",
            "email": "reviewer@acme.example",
            "password": "StrongPass123!",
        },
    )

    assert response.status_code == 409
    assert "email already exists" in response.json()["detail"]


def test_signup_rejects_weak_passwords_and_extra_fields(seeded_database) -> None:
    client = _client()

    weak_response = client.post(
        "/auth/signup",
        json={
            "mode": "CREATE_ORG_ADMIN",
            "organization_name": "Weak Password Co",
            "organization_slug": "weak-password-co",
            "name": "Weak Admin",
            "email": "weak.admin@example.com",
            "password": "password",
        },
    )
    common_response = client.post(
        "/auth/signup",
        json={
            "mode": "CREATE_ORG_ADMIN",
            "organization_name": "Common Password Co",
            "organization_slug": "common-password-co",
            "name": "Common Admin",
            "email": "common.admin@example.com",
            "password": "Password123!",
        },
    )
    extra_response = client.post(
        "/auth/signup",
        json={
            "mode": "CREATE_ORG_ADMIN",
            "organization_name": "Extra Field Co",
            "organization_slug": "extra-field-co",
            "name": "Extra Admin",
            "email": "extra.admin@example.com",
            "password": "StrongPass123!",
            "role": "ADMIN",
        },
    )

    assert weak_response.status_code == 422
    assert common_response.status_code == 422
    assert extra_response.status_code == 422


@pytest.mark.parametrize("slug", ["-bad", "bad-", "bad--slug", "bad_slug"])
def test_signup_rejects_invalid_organization_slug(slug: str, seeded_database) -> None:
    client = _client()

    response = client.post(
        "/auth/signup",
        json={
            "mode": "CREATE_ORG_ADMIN",
            "organization_name": "Invalid Slug Co",
            "organization_slug": slug,
            "name": "Invalid Slug",
            "email": "invalid.slug@example.com",
            "password": "StrongPass123!",
        },
    )

    assert response.status_code == 422


def test_signup_rejects_invalid_email(seeded_database) -> None:
    client = _client()

    response = client.post(
        "/auth/signup",
        json={
            "mode": "CREATE_ORG_ADMIN",
            "organization_name": "Invalid Email Co",
            "organization_slug": "invalid-email-co",
            "name": "Invalid Email",
            "email": "not-an-email",
            "password": "StrongPass123!",
        },
    )

    assert response.status_code == 422


def test_signup_rate_limit_returns_429(seeded_database) -> None:
    signup_rate_limiter.clear()
    client = _client()

    response = None
    for _ in range(get_settings().signup_rate_limit_attempts + 1):
        response = client.post(
            "/auth/signup",
            json={
                "mode": "JOIN_ORG_REVIEWER",
                "organization_slug": "acme",
                "invite_code": "wrong-code",
                "name": "Rate Limited",
                "email": "rate.limited@acme.example",
                "password": "StrongPass123!",
            },
        )

    assert response is not None
    assert response.status_code == 429
    assert "Too many signup attempts" in response.json()["detail"]


def test_login_accepts_organization_slug(seeded_database) -> None:
    client = _client()

    response = client.post(
        "/auth/login",
        json={
            "email": "admin@globex.example",
            "password": "AdminPass123!",
            "organization_slug": "globex",
        },
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "admin@globex.example"


def test_login_rejects_wrong_organization_slug(seeded_database) -> None:
    client = _client()

    response = client.post(
        "/auth/login",
        json={
            "email": "admin@acme.example",
            "password": "AdminPass123!",
            "organization_slug": "globex",
        },
    )

    assert response.status_code == 401


def test_ambiguous_email_login_requires_organization_slug(seeded_database) -> None:
    with sync_session_factory() as session:
        globex = session.scalar(select(Organization).where(Organization.slug == "globex"))
        assert globex is not None
        session.add(
            User(
                organization_id=globex.id,
                email="reviewer@acme.example",
                name="Duplicate Email User",
                role=UserRole.REVIEWER,
                password_hash=hash_password("ReviewerPass123!"),
                is_active=True,
            )
        )
        session.commit()

    client = _client()
    ambiguous_response = client.post(
        "/auth/login",
        json={
            "email": "reviewer@acme.example",
            "password": "ReviewerPass123!",
        },
    )
    scoped_response = client.post(
        "/auth/login",
        json={
            "email": "reviewer@acme.example",
            "password": "ReviewerPass123!",
            "organization_slug": "acme",
        },
    )

    assert ambiguous_response.status_code == 400
    assert "Specify organization_slug" in ambiguous_response.json()["detail"]
    assert scoped_response.status_code == 200


def test_invalid_login_is_rejected(seeded_database) -> None:
    client = _client()

    response = client.post(
        "/auth/login",
        json={
            "email": "reviewer@acme.example",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


def test_inactive_user_cannot_login(seeded_database) -> None:
    client = _client()

    response = client.post(
        "/auth/login",
        json={
            "email": "inactive@acme.example",
            "password": "InactivePass123!",
        },
    )

    assert response.status_code == 401


def test_existing_session_is_rejected_after_user_deactivation(seeded_database) -> None:
    client = _client()
    login_response = client.post(
        "/auth/login",
        json={
            "email": "reviewer@acme.example",
            "password": "ReviewerPass123!",
        },
    )
    assert login_response.status_code == 200

    with sync_session_factory() as session:
        user = session.scalar(select(User).where(User.email == "reviewer@acme.example"))
        assert user is not None
        user.is_active = False
        session.commit()

    response = client.get("/auth/me")

    assert response.status_code == 401


def test_tampered_jwt_cookie_is_rejected(seeded_database) -> None:
    client = _client()
    client.cookies.set(get_settings().auth_cookie_name, "not-a-valid-token")

    response = client.get("/auth/me")

    assert response.status_code == 401


def test_login_rejects_extra_fields(seeded_database) -> None:
    client = _client()

    response = client.post(
        "/auth/login",
        json={
            "email": "reviewer@acme.example",
            "password": "ReviewerPass123!",
            "role": "ADMIN",
        },
    )

    assert response.status_code == 422


def test_login_rate_limit_returns_429(seeded_database) -> None:
    login_rate_limiter.clear()
    client = _client()

    response = None
    for _ in range(get_settings().login_rate_limit_attempts + 1):
        response = client.post(
            "/auth/login",
            json={
                "email": "missing@example.com",
                "password": "wrong-password",
            },
        )

    assert response is not None
    assert response.status_code == 429
    assert "Too many login attempts" in response.json()["detail"]


def test_user_email_is_unique_per_org_but_allowed_across_orgs(seeded_database) -> None:
    with sync_session_factory() as session:
        acme = session.scalar(select(Organization).where(Organization.slug == "acme"))
        globex = session.scalar(select(Organization).where(Organization.slug == "globex"))
        assert acme is not None
        assert globex is not None

        session.add(
            User(
                organization_id=globex.id,
                email="shared@example.com",
                name="Globex Shared",
                role=UserRole.REVIEWER,
                password_hash=hash_password("SharedPass123!"),
                is_active=True,
            )
        )
        session.add(
            User(
                organization_id=acme.id,
                email="shared@example.com",
                name="Acme Shared",
                role=UserRole.REVIEWER,
                password_hash=hash_password("SharedPass123!"),
                is_active=True,
            )
        )
        session.commit()

        session.add(
            User(
                organization_id=acme.id,
                email="shared@example.com",
                name="Duplicate Acme Shared",
                role=UserRole.REVIEWER,
                password_hash=hash_password("SharedPass123!"),
                is_active=True,
            )
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("Expected duplicate email in same org to fail.")
