"""
ORVANTA Cloud — Auth Service
Handles user registration, login, and organization management.
"""

import re
import time
import uuid
from datetime import timedelta
from email.message import EmailMessage
import aiosmtplib
from google.oauth2 import id_token
from google.auth.transport.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from fastapi import HTTPException, status
import httpx
from jose import jwt, jwk
from jose.utils import base64url_decode

from app.models.user import User
from app.models.organization import Organization, OrgMember, OrgRole
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
    UserResponse,
    OrgResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    MessageResponse,
    GoogleSignInRequest,
    ClerkSignInRequest,
    SupabaseSignInRequest,
)
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
SMTP_USER_PLACEHOLDERS = {"your-email@gmail.com", "example@example.com"}
SMTP_PASSWORD_PLACEHOLDERS = {"your-app-password", "changeme"}


def _slugify(name: str) -> str:
    """Convert organization name to URL-safe slug."""
    slug = re.sub(r'[^\w\s-]', '', name.lower())
    slug = re.sub(r'[\s_]+', '-', slug)
    return slug.strip('-')


def _normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def _normalize_username(value: str) -> str:
    return str(value or "").strip()


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


async def _create_default_org_for_user(
    user: User,
    db: AsyncSession,
    org_name: str | None = None,
) -> Organization:
    """Create a default admin org for users missing organization membership."""
    name_seed = _normalize_optional_text(org_name) or user.full_name or user.username or user.email
    org_name_value = f"{name_seed}'s ORVANTA Workspace"
    slug = _slugify(org_name_value)
    existing_org = await db.execute(select(Organization).where(Organization.slug == slug))
    if existing_org.scalar_one_or_none():
        slug = f"{slug}-{str(user.id)[:8]}"

    org = Organization(name=org_name_value, slug=slug)
    db.add(org)
    await db.flush()

    membership = OrgMember(user_id=user.id, organization_id=org.id, role=OrgRole.ADMIN)
    db.add(membership)
    await db.commit()
    await db.refresh(org)
    return org


async def _verify_supabase_access_token(supabase_token: str) -> dict:
    """Verify Supabase access token signature and required claims."""
    if not settings.SUPABASE_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase authentication is not configured",
        )

    try:
        header = jwt.get_unverified_header(supabase_token)
        claims = jwt.get_unverified_claims(supabase_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase access token",
        )

    expected_issuer = (
        str(settings.SUPABASE_JWT_ISSUER or "").strip().rstrip("/")
        or f"{str(settings.SUPABASE_URL).strip().rstrip('/')}/auth/v1"
    )
    issuer = str(claims.get("iss") or "").strip().rstrip("/")
    if issuer != expected_issuer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Supabase token issuer mismatch",
        )

    expected_audience = str(settings.SUPABASE_JWT_AUDIENCE or "").strip()
    token_aud = claims.get("aud")
    if expected_audience:
        audience_ok = False
        if isinstance(token_aud, str):
            audience_ok = token_aud == expected_audience
        elif isinstance(token_aud, list):
            audience_ok = expected_audience in token_aud
        if not audience_ok:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Supabase token audience mismatch",
            )

    jwks_url = f"{expected_issuer}/.well-known/jwks.json"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0)) as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
            jwks = response.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify Supabase token right now",
        )

    kid = header.get("kid")
    alg = header.get("alg")
    key_data = next((item for item in jwks.get("keys", []) if item.get("kid") == kid), None)
    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase signing key",
        )

    try:
        message, encoded_signature = supabase_token.rsplit(".", 1)
        decoded_signature = base64url_decode(encoded_signature.encode("utf-8"))
        public_key = jwk.construct(key_data, algorithm=alg)
        if not public_key.verify(message.encode("utf-8"), decoded_signature):
            raise ValueError("signature_invalid")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase token signature",
        )

    now = int(time.time())
    exp = claims.get("exp")
    nbf = claims.get("nbf")
    if exp is not None and now >= int(exp):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Supabase session expired",
        )
    if nbf is not None and now < int(nbf):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Supabase session not active yet",
        )

    return claims


async def _verify_clerk_session_token(clerk_token: str) -> dict:
    """Verify Clerk session token signature and required claims."""
    try:
        header = jwt.get_unverified_header(clerk_token)
        claims = jwt.get_unverified_claims(clerk_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Clerk session token",
        )

    issuer = str(claims.get("iss") or "").strip().rstrip("/")
    expected_issuer = str(settings.CLERK_ISSUER or "").strip().rstrip("/")
    if expected_issuer and issuer != expected_issuer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clerk token issuer mismatch",
        )
    if not issuer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clerk token issuer missing",
        )

    jwks_url = f"{issuer}/.well-known/jwks.json"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0)) as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
            jwks = response.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify Clerk session right now",
        )

    kid = header.get("kid")
    alg = header.get("alg")
    key_data = next((item for item in jwks.get("keys", []) if item.get("kid") == kid), None)
    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Clerk signing key",
        )

    try:
        message, encoded_signature = clerk_token.rsplit(".", 1)
        decoded_signature = base64url_decode(encoded_signature.encode("utf-8"))
        public_key = jwk.construct(key_data, algorithm=alg)
        if not public_key.verify(message.encode("utf-8"), decoded_signature):
            raise ValueError("signature_invalid")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Clerk session signature",
        )

    now = int(time.time())
    exp = claims.get("exp")
    nbf = claims.get("nbf")
    if exp is not None and now >= int(exp):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clerk session expired",
        )
    if nbf is not None and now < int(nbf):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clerk session not active yet",
        )

    return claims


async def _ensure_clerk_org_membership(clerk_user_id: str) -> None:
    """Best-effort auto-membership to a default Clerk org for smoother multi-user onboarding."""
    org_id = str(settings.CLERK_DEFAULT_ORG_ID or "").strip()
    secret_key = str(settings.CLERK_SECRET_KEY or "").strip()
    if not org_id or not secret_key:
        return

    endpoint = f"https://api.clerk.com/v1/organizations/{org_id}/memberships"
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "user_id": clerk_user_id,
        "role": "org:member",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0)) as client:
            response = await client.post(endpoint, headers=headers, json=payload)

        if response.status_code in {200, 201, 409}:
            return

        # Clerk can return validation errors when membership already exists.
        if response.status_code == 422 and "already" in response.text.lower():
            return

        logger.warning(
            "clerk_default_org_membership_failed",
            clerk_user_id=clerk_user_id,
            org_id=org_id,
            status_code=response.status_code,
            response_body=response.text[:500],
        )
    except Exception as exc:
        logger.warning(
            "clerk_default_org_membership_exception",
            clerk_user_id=clerk_user_id,
            org_id=org_id,
            error=str(exc),
        )


def _is_smtp_configured() -> bool:
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        return False

    has_any_auth_value = bool(settings.SMTP_USER or settings.SMTP_PASSWORD)
    if has_any_auth_value and not (settings.SMTP_USER and settings.SMTP_PASSWORD):
        return False

    if settings.SMTP_USER in SMTP_USER_PLACEHOLDERS:
        return False
    if settings.SMTP_PASSWORD in SMTP_PASSWORD_PLACEHOLDERS:
        return False

    return True


async def register_user(data: UserRegister, db: AsyncSession) -> TokenResponse:
    """Register a new user and create their organization."""
    email = _normalize_email(data.email)
    username = _normalize_username(data.username)
    full_name = _normalize_optional_text(data.full_name)
    org_name = str(data.org_name).strip()

    # Check if email already exists
    existing = await db.execute(select(User).where(func.lower(User.email) == email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Check if username exists
    existing = await db.execute(select(User).where(func.lower(User.username) == username.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    # Create user
    user = User(
        email=email,
        username=username,
        hashed_password=hash_password(data.password),
        full_name=full_name,
    )
    db.add(user)
    await db.flush()

    # Create organization
    slug = _slugify(org_name)
    # Ensure slug uniqueness
    existing_org = await db.execute(select(Organization).where(Organization.slug == slug))
    if existing_org.scalar_one_or_none():
        slug = f"{slug}-{str(user.id)[:8]}"

    org = Organization(
        name=org_name,
        slug=slug,
    )
    db.add(org)
    await db.flush()

    # Create membership (admin)
    membership = OrgMember(
        user_id=user.id,
        organization_id=org.id,
        role=OrgRole.ADMIN,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(user)
    await db.refresh(org)

    logger.info("user_registered", user_id=str(user.id), org_id=str(org.id))

    # Generate JWT
    token = create_access_token(data={"sub": str(user.id), "org": str(org.id)})

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
        organization=OrgResponse.model_validate(org),
    )


async def _get_user_org(user_id, db: AsyncSession):
    result = await db.execute(
        select(OrgMember, Organization)
        .join(Organization, OrgMember.organization_id == Organization.id)
        .where(OrgMember.user_id == user_id)
        .limit(1)
    )
    return result.first()


async def login_user(data: UserLogin, db: AsyncSession) -> TokenResponse:
    """Authenticate user and return JWT token."""
    email = _normalize_email(data.email)

    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Get user's org
    row = await _get_user_org(user.id, db)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No organization found for user",
        )

    membership, org = row

    logger.info("user_logged_in", user_id=str(user.id))

    token = create_access_token(data={"sub": str(user.id), "org": str(org.id)})

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
        organization=OrgResponse.model_validate(org),
    )


async def google_sign_in(data: GoogleSignInRequest, db: AsyncSession) -> TokenResponse:
    """Authenticate user with Google ID token and issue app JWT."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google sign-in is not configured",
        )

    try:
        google_payload = id_token.verify_oauth2_token(
            data.credential, Request(), settings.GOOGLE_CLIENT_ID
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google credential",
        )

    email = _normalize_email(google_payload.get("email"))
    if not email or not google_payload.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account email is not verified",
        )

    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()

    if not user:
        full_name = google_payload.get("name")
        username_seed = email.split("@")[0]
        username = re.sub(r"[^a-zA-Z0-9._-]", "-", username_seed).strip("-") or "user"
        org_name = f"{full_name or username_seed}'s ORVANTA Workspace"

        existing_username = await db.execute(
            select(User).where(func.lower(User.username) == username.lower())
        )
        if existing_username.scalar_one_or_none():
            username = f"{username}-{uuid.uuid4().hex[:6]}"

        user = User(
            email=email,
            username=username,
            hashed_password=hash_password(uuid.uuid4().hex),
            full_name=full_name,
        )
        db.add(user)
        await db.flush()

        slug = _slugify(org_name)
        existing_org = await db.execute(select(Organization).where(Organization.slug == slug))
        if existing_org.scalar_one_or_none():
            slug = f"{slug}-{str(user.id)[:8]}"

        org = Organization(name=org_name, slug=slug)
        db.add(org)
        await db.flush()

        membership = OrgMember(
            user_id=user.id,
            organization_id=org.id,
            role=OrgRole.ADMIN,
        )
        db.add(membership)
        await db.commit()
        await db.refresh(user)
        await db.refresh(org)
    else:
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled",
            )

        row = await _get_user_org(user.id, db)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No organization found for user",
            )
        _, org = row

    token = create_access_token(data={"sub": str(user.id), "org": str(org.id)})
    logger.info("user_logged_in_google", user_id=str(user.id))

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
        organization=OrgResponse.model_validate(org),
    )


async def clerk_sign_in(data: ClerkSignInRequest, db: AsyncSession) -> TokenResponse:
    """Authenticate user with Clerk session token and issue app JWT."""
    claims = await _verify_clerk_session_token(data.clerk_token)
    clerk_user_id = str(claims.get("sub") or "").strip()
    if not clerk_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Clerk user identity",
        )

    await _ensure_clerk_org_membership(clerk_user_id)

    claim_email = _normalize_email(claims.get("email") or claims.get("email_address") or "")
    request_email = _normalize_email(data.email or "")
    email = request_email or claim_email or f"clerk+{clerk_user_id}@clerk.local"
    full_name = _normalize_optional_text(data.full_name or claims.get("name"))

    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()

    if not user:
        username_seed = email.split("@")[0] if "@" in email else clerk_user_id
        username = re.sub(r"[^a-zA-Z0-9._-]", "-", username_seed).strip("-") or "user"
        existing_username = await db.execute(
            select(User).where(func.lower(User.username) == username.lower())
        )
        if existing_username.scalar_one_or_none():
            username = f"{username}-{uuid.uuid4().hex[:6]}"

        org_name_seed = (full_name or username_seed or "Client").strip()
        org_name = f"{org_name_seed}'s ORVANTA Workspace"

        user = User(
            email=email,
            username=username,
            hashed_password=hash_password(uuid.uuid4().hex),
            full_name=full_name,
        )
        db.add(user)
        await db.flush()

        slug = _slugify(org_name)
        existing_org = await db.execute(select(Organization).where(Organization.slug == slug))
        if existing_org.scalar_one_or_none():
            slug = f"{slug}-{str(user.id)[:8]}"

        org = Organization(name=org_name, slug=slug)
        db.add(org)
        await db.flush()

        membership = OrgMember(
            user_id=user.id,
            organization_id=org.id,
            role=OrgRole.ADMIN,
        )
        db.add(membership)
        await db.commit()
        await db.refresh(user)
        await db.refresh(org)
    else:
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled",
            )

        row = await _get_user_org(user.id, db)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No organization found for user",
            )
        _, org = row

    token = create_access_token(data={"sub": str(user.id), "org": str(org.id)})
    logger.info("user_logged_in_clerk", user_id=str(user.id), clerk_user_id=clerk_user_id)

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
        organization=OrgResponse.model_validate(org),
    )


async def supabase_sign_in(data: SupabaseSignInRequest, db: AsyncSession) -> TokenResponse:
    """Authenticate user with Supabase access token and issue app JWT."""
    claims = await _verify_supabase_access_token(data.access_token)

    supabase_user_id = str(claims.get("sub") or "").strip()
    if not supabase_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase user identity",
        )

    email = _normalize_email(claims.get("email") or "")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supabase account email is required",
        )

    user_metadata = claims.get("user_metadata") if isinstance(claims.get("user_metadata"), dict) else {}
    full_name = _normalize_optional_text(data.full_name or user_metadata.get("full_name") or claims.get("name"))

    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()

    if not user:
        username_seed = _normalize_username(data.username or email.split("@")[0])
        username = re.sub(r"[^a-zA-Z0-9._-]", "-", username_seed).strip("-") or "user"
        existing_username = await db.execute(
            select(User).where(func.lower(User.username) == username.lower())
        )
        if existing_username.scalar_one_or_none():
            username = f"{username}-{uuid.uuid4().hex[:6]}"

        user = User(
            email=email,
            username=username,
            hashed_password=hash_password(uuid.uuid4().hex),
            full_name=full_name,
        )
        try:
            user.id = uuid.UUID(supabase_user_id)
        except ValueError:
            pass

        db.add(user)
        await db.flush()

        org = await _create_default_org_for_user(user, db, data.org_name)
        await db.refresh(user)
    else:
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled",
            )

        if full_name and user.full_name != full_name:
            user.full_name = full_name
            await db.commit()

        row = await _get_user_org(user.id, db)
        if not row:
            org = await _create_default_org_for_user(user, db, data.org_name)
        else:
            _, org = row

    token = create_access_token(data={"sub": str(user.id), "org": str(org.id)})
    logger.info("user_logged_in_supabase", user_id=str(user.id), supabase_user_id=supabase_user_id)

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
        organization=OrgResponse.model_validate(org),
    )


async def _send_password_reset_email(to_email: str, reset_link: str) -> tuple[bool, str | None]:
    """Send password reset email when SMTP is configured."""
    if not _is_smtp_configured():
        logger.warning("smtp_not_configured_password_reset", email=to_email, reset_link=reset_link)
        return False, "Password reset email service is not configured on this server."

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = to_email
    message["Subject"] = "Reset your ORVANTA password"
    message.set_content(
        f"Use this link to reset your password:\n\n{reset_link}\n\n"
        "If you did not request this, you can ignore this email."
    )

    try:
        send_kwargs = {
            "hostname": settings.SMTP_HOST,
            "port": settings.SMTP_PORT,
            "timeout": 10,
        }

        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            send_kwargs["username"] = settings.SMTP_USER
            send_kwargs["password"] = settings.SMTP_PASSWORD

        if settings.SMTP_USE_TLS:
            send_kwargs["use_tls"] = True
        elif settings.SMTP_STARTTLS:
            send_kwargs["start_tls"] = True

        await aiosmtplib.send(message, **send_kwargs)
        return True, None
    except Exception as exc:
        logger.error("password_reset_email_failed", email=to_email, error=str(exc), reset_link=reset_link)
        return False, "Password reset email service is temporarily unavailable. Please try again later."


async def request_password_reset(data: ForgotPasswordRequest, db: AsyncSession) -> MessageResponse:
    """Issue a reset token and send reset instructions if account exists."""
    email = _normalize_email(data.email)
    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalar_one_or_none()
    inbox_url = settings.SMTP_INBOX_URL if settings.APP_ENV == "development" else None

    if not _is_smtp_configured():
        reset_link = None
        if user:
            token = create_access_token(
                data={"sub": str(user.id), "type": "password_reset"},
                expires_delta=timedelta(minutes=30),
            )
            reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
            logger.warning("password_reset_using_dev_link", user_id=str(user.id), reset_link=reset_link)

        message = "Password reset email service is not configured on this server."
        if reset_link and settings.APP_ENV == "development":
            message = "Password reset email is not configured. Use the reset link below."
        return MessageResponse(
            message=message,
            reset_link=reset_link if settings.APP_ENV == "development" else None,
            inbox_url=inbox_url,
        )

    if user:
        token = create_access_token(
            data={"sub": str(user.id), "type": "password_reset"},
            expires_delta=timedelta(minutes=30),
        )
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        sent, error_message = await _send_password_reset_email(user.email, reset_link)
        if not sent:
            if settings.APP_ENV == "development":
                return MessageResponse(
                    message=error_message or "Password reset email service is temporarily unavailable.",
                    reset_link=reset_link,
                    inbox_url=inbox_url,
                )
            return MessageResponse(
                message="If that email exists, password reset instructions have been sent."
            )
        logger.info("password_reset_requested", user_id=str(user.id))

    # Always return generic message to avoid email enumeration
    return MessageResponse(
        message="If that email exists, password reset instructions have been sent.",
        inbox_url=inbox_url,
    )


async def reset_password(data: ResetPasswordRequest, db: AsyncSession) -> MessageResponse:
    """Validate reset token and update user's password."""
    payload = decode_access_token(data.token)
    if payload.get("type") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password reset token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password reset token",
        )

    try:
        parsed_user_id = uuid.UUID(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password reset token",
        )

    result = await db.execute(select(User).where(User.id == parsed_user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.hashed_password = hash_password(data.new_password)
    await db.commit()
    logger.info("password_reset_completed", user_id=str(user.id))

    return MessageResponse(message="Password reset successful. You can now log in.")
