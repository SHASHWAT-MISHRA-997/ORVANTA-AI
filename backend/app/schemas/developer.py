"""
ORVANTA Cloud - Developer management schemas
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class DeveloperUserOrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    role: str
    joined_at: Optional[datetime] = None


class DeveloperUserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    full_name: Optional[str]
    is_active: bool
    is_superadmin: bool
    is_archived: bool
    created_at: datetime
    organizations: list[DeveloperUserOrganizationResponse]


class DeveloperUserListResponse(BaseModel):
    total: int
    active: int
    archived: int
    users: list[DeveloperUserResponse]


class DeveloperActionResponse(BaseModel):
    message: str
    affected_count: int
