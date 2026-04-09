"""
ORVANTA Cloud — FastAPI Dependencies
Common dependencies for route handlers: auth, DB session, org context.
"""

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID

from app.db.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.models.organization import Organization, OrgMember

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the current user from JWT token."""
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


async def get_current_org(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple:
    """Get the user's organization and membership. Returns (user, org, membership)."""
    result = await db.execute(
        select(OrgMember, Organization)
        .join(Organization, OrgMember.organization_id == Organization.id)
        .where(OrgMember.user_id == user.id)
        .limit(1)
    )
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a member of any organization",
        )

    membership, org = row
    return user, org, membership


async def get_api_key_org(
    x_api_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Authenticate via API key header."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header required",
        )

    result = await db.execute(
        select(Organization).where(Organization.api_key == x_api_key)
    )
    org = result.scalar_one_or_none()

    if not org or not org.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return org


def require_admin(org_context: tuple = Depends(get_current_org)):
    """Require admin role for the current organization."""
    user, org, membership = org_context
    role_value = getattr(membership.role, "value", membership.role)
    if str(role_value).lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user, org, membership
