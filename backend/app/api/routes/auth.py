from datetime import UTC, datetime
from hmac import compare_digest

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.auth.rate_limit import login_rate_limiter, signup_rate_limiter
from app.core.config import get_settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.demo_work_items import create_signup_demo_work_items
from app.db.session import get_async_session
from app.models.enums import UserRole
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, SignupRequest, user_response_from_model

router = APIRouter()


def _rate_limit_key(request: Request, email: str, *, purpose: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{purpose}:{client_host}:{email.lower().strip()}"


def _set_auth_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        max_age=settings.auth_cookie_max_age_seconds,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    settings = get_settings()
    # Deliberately host-only: the Next.js proxy will own the browser-facing origin.
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_async_session),
) -> AuthResponse:
    normalized_email = str(payload.email).lower().strip()
    rate_limit_key = _rate_limit_key(request, normalized_email, purpose="login")
    retry_after = login_rate_limiter.check(rate_limit_key)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    user_query = select(User).where(User.email == normalized_email, User.is_active.is_(True))
    if payload.organization_slug:
        user_query = user_query.join(Organization).where(
            Organization.slug == payload.organization_slug
        )

    users = list(await session.scalars(user_query))
    if len(users) > 1 and not payload.organization_slug:
        verify_password(payload.password, DUMMY_PASSWORD_HASH)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multiple organizations use this email. Specify organization_slug.",
        )

    user = users[0] if len(users) == 1 else None
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    if not verify_password(payload.password, password_hash) or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    user.last_login_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(user)

    token = create_access_token(user.id)
    _set_auth_cookie(response, token)
    login_rate_limiter.reset(rate_limit_key)
    return AuthResponse(user=user_response_from_model(user))


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_async_session),
) -> AuthResponse:
    settings = get_settings()
    normalized_email = str(payload.email).lower().strip()
    rate_limit_key = _rate_limit_key(request, normalized_email, purpose="signup")
    retry_after = signup_rate_limiter.check(
        rate_limit_key,
        attempts_limit=settings.signup_rate_limit_attempts,
        window_seconds=settings.signup_rate_limit_window_seconds,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many signup attempts. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    if payload.mode == "CREATE_ORG_ADMIN":
        organization_exists = await session.scalar(
            select(Organization.id).where(Organization.slug == payload.organization_slug)
        )
        if organization_exists is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Organization slug is already in use.",
            )
        organization = Organization(
            name=payload.organization_name or payload.organization_slug,
            slug=payload.organization_slug,
        )
        session.add(organization)
        await session.flush()
        role = UserRole.ADMIN
    else:
        expected_invite_code = settings.reviewer_invite_code.get_secret_value()
        invite_valid = compare_digest(payload.invite_code or "", expected_invite_code)
        organization = await session.scalar(
            select(Organization).where(Organization.slug == payload.organization_slug)
        )
        if organization is None or not invite_valid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid organization or invite code.",
            )
        role = UserRole.REVIEWER

    existing_user = await session.scalar(
        select(User.id).where(
            User.organization_id == organization.id,
            User.email == normalized_email,
        )
    )
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists in this organization.",
        )

    user = User(
        organization_id=organization.id,
        email=normalized_email,
        name=payload.name,
        role=role,
        password_hash=hash_password(payload.password),
        is_active=True,
        last_login_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    if settings.signup_demo_data_enabled:
        await create_signup_demo_work_items(
            session,
            organization=organization,
            assignee=user,
        )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Signup could not be completed because this organization or user already exists."
            ),
        ) from exc

    await session.refresh(user)
    token = create_access_token(user.id)
    _set_auth_cookie(response, token)
    signup_rate_limiter.reset(rate_limit_key)
    return AuthResponse(user=user_response_from_model(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    _clear_auth_cookie(response)


@router.get("/me", response_model=AuthResponse)
async def me(current_user: User = Depends(get_current_user)) -> AuthResponse:
    return AuthResponse(user=user_response_from_model(current_user))
