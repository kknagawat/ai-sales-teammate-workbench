from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.lead_work_item import LeadWorkItem
from app.models.user import User
from app.work_items.errors import not_found


def can_access_work_item(user: User, item: LeadWorkItem) -> bool:
    if item.organization_id != user.organization_id:
        return False
    if user.role == UserRole.ADMIN:
        return True
    return item.assigned_reviewer_id == user.id


async def get_accessible_work_item(
    session: AsyncSession,
    user: User,
    work_item_id: UUID,
    *,
    for_update: bool = False,
) -> LeadWorkItem:
    stmt = select(LeadWorkItem).where(
        LeadWorkItem.id == work_item_id,
        LeadWorkItem.organization_id == user.organization_id,
    )
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)

    item = await session.scalar(stmt)
    if item is None or not can_access_work_item(user, item):
        raise not_found()
    return item
