"""
ORVANTA Cloud - Developer management routes
"""

from collections import OrderedDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.database import get_db
from app.models.organization import OrgMember, Organization
from app.models.user import User
from app.schemas.developer import (
    DeveloperActionResponse,
    DeveloperUserListResponse,
    DeveloperUserOrganizationResponse,
    DeveloperUserResponse,
)

router = APIRouter(prefix="/developer", tags=["Developer"])


def _ensure_developer_access(user: User) -> None:
    if settings.APP_ENV == "development" or user.is_superadmin:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Developer access is available only in development or for superadmins.",
    )


def _archived_email(user_id: UUID) -> str:
    return f"archived+{user_id.hex[:12]}@warops.invalid"


def _archived_username(user_id: UUID) -> str:
    return f"archived_{user_id.hex[:12]}"


def _is_archived_user(user: User) -> bool:
    return user.email.endswith("@warops.invalid") and user.username.startswith("archived_")


def _release_user_identity(user: User) -> bool:
    archived_email = _archived_email(user.id)
    archived_username = _archived_username(user.id)
    changed = False

    if user.email != archived_email:
        user.email = archived_email
        changed = True
    if user.username != archived_username:
        user.username = archived_username
        changed = True
    if user.is_active:
        user.is_active = False
        changed = True

    return changed


@router.get("/users", response_model=DeveloperUserListResponse)
async def list_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users and their organization memberships for developer review."""
    _ensure_developer_access(current_user)

    result = await db.execute(
        select(User, OrgMember, Organization)
        .outerjoin(OrgMember, OrgMember.user_id == User.id)
        .outerjoin(Organization, Organization.id == OrgMember.organization_id)
        .order_by(User.created_at.desc())
    )
    rows = result.all()

    user_map: "OrderedDict[UUID, DeveloperUserResponse]" = OrderedDict()
    for user, membership, organization in rows:
        if user.id not in user_map:
            user_map[user.id] = DeveloperUserResponse(
                id=user.id,
                email=user.email,
                username=user.username,
                full_name=user.full_name,
                is_active=bool(user.is_active),
                is_superadmin=bool(user.is_superadmin),
                is_archived=_is_archived_user(user),
                created_at=user.created_at,
                organizations=[],
            )

        if membership and organization:
            user_map[user.id].organizations.append(
                DeveloperUserOrganizationResponse(
                    id=organization.id,
                    name=organization.name,
                    slug=organization.slug,
                    role=membership.role.value,
                    joined_at=membership.joined_at,
                )
            )

    users = list(user_map.values())
    return DeveloperUserListResponse(
        total=len(users),
        active=sum(1 for user in users if user.is_active),
        archived=sum(1 for user in users if user.is_archived),
        users=users,
    )


@router.post("/users/{user_id}/release", response_model=DeveloperActionResponse)
async def release_user_identity(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Archive one user's email and username so the credentials can be reused."""
    _ensure_developer_access(current_user)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot release the currently signed-in account. Use another admin account.",
        )

    changed = _release_user_identity(user)
    await db.commit()

    return DeveloperActionResponse(
        message="User credentials released." if changed else "User credentials were already released.",
        affected_count=1 if changed else 0,
    )


@router.post("/users/release-all", response_model=DeveloperActionResponse)
async def release_all_user_identities(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Archive all user emails and usernames so everyone can register again."""
    _ensure_developer_access(current_user)

    result = await db.execute(select(User).order_by(User.created_at.asc()))
    users = result.scalars().all()

    changed = 0
    skipped_current = 0
    for user in users:
        if user.id == current_user.id:
            skipped_current += 1
            continue
        if _release_user_identity(user):
            changed += 1

    await db.commit()

    message = "All user credentials have been released for fresh registration."
    if skipped_current:
        message += " Current signed-in account was skipped to avoid lockout."

    return DeveloperActionResponse(
        message=message,
        affected_count=changed,
    )


@router.delete("/users/released", response_model=DeveloperActionResponse)
async def clear_released_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete archived inactive users from the developer directory."""
    _ensure_developer_access(current_user)

    result = await db.execute(select(User).order_by(User.created_at.asc()))
    users = result.scalars().all()

    deleted = 0
    for user in users:
        if user.id == current_user.id:
            continue
        if _is_archived_user(user) and not user.is_active:
            await db.delete(user)
            deleted += 1

    await db.commit()

    return DeveloperActionResponse(
        message="Released inactive users cleared successfully." if deleted else "No released inactive users needed clearing.",
        affected_count=deleted,
    )
