"""
ORVANTA Cloud — Auth Schemas
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime


class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(None, max_length=255)
    org_name: str = Field(..., min_length=1, max_length=255)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return str(value or "").strip().lower()

    @field_validator("username", "org_name", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("full_name", mode="before")
    @classmethod
    def strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return str(value or "").strip().lower()


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return str(value or "").strip().lower()


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=16)
    new_password: str = Field(..., min_length=8, max_length=128)


class GoogleSignInRequest(BaseModel):
    credential: str = Field(..., min_length=16)


class ClerkSignInRequest(BaseModel):
    clerk_token: str = Field(..., min_length=16)
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=255)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_optional_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = str(value).strip().lower()
        return stripped or None

    @field_validator("full_name", mode="before")
    @classmethod
    def normalize_optional_full_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


class SupabaseSignInRequest(BaseModel):
    access_token: str = Field(..., min_length=16)
    username: Optional[str] = Field(None, min_length=1, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)
    org_name: Optional[str] = Field(None, min_length=1, max_length=255)

    @field_validator("username", "org_name", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    @field_validator("full_name", mode="before")
    @classmethod
    def normalize_optional_full_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


class MessageResponse(BaseModel):
    message: str
    reset_link: Optional[str] = None
    inbox_url: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"
    organization: "OrgResponse"


class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    full_name: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class OrgResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    api_key: str
    is_active: bool
    risk_threshold_low: str
    risk_threshold_medium: str
    risk_threshold_high: str
    risk_threshold_critical: str
    webhook_url: Optional[str]
    webhook_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserWithOrg(BaseModel):
    user: UserResponse
    organization: OrgResponse
    role: str
