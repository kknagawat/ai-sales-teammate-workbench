from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_async_session
from app.models.user import User


async def get_current_user(
    session: AsyncSession = Depends(get_async_session),
    session_cookie: str | None = Cookie(default=None, alias=get_settings().auth_cookie_name),
) -> User:
    if not session_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    try:
        user_id: UUID = decode_access_token(session_cookie)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session.",
        ) from exc

    user = await session.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session.")
    return user


async def get_optional_current_user(
    session: AsyncSession = Depends(get_async_session),
    session_cookie: str | None = Cookie(default=None, alias=get_settings().auth_cookie_name),
) -> User | None:
    if not session_cookie:
        return None
    try:
        user_id: UUID = decode_access_token(session_cookie)
    except InvalidTokenError:
        return None
    return await session.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
