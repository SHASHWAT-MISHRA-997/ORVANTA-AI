"""
ORVANTA Cloud - Chat API Routes
"""

from typing import Any, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_org
from app.db.database import get_db
from app.services.chat_service import generate_chat_response

router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatHistoryItem] = Field(default_factory=list)
    client_now_iso: Optional[str] = None
    client_tz_offset_minutes: Optional[int] = None


class ChatResponse(BaseModel):
    response: str
    provider: str
    model: str
    sources: list[dict[str, Any]] = Field(default_factory=list)


@router.post("", response_model=ChatResponse)
async def ask_assistant(
    payload: ChatRequest,
    org_context: tuple = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Generate an assistant response using organization-aware context."""
    _, org, _ = org_context

    try:
        result = await generate_chat_response(
            message=payload.message,
            history=[item.model_dump() for item in payload.history],
            client_now_iso=payload.client_now_iso,
            client_tz_offset_minutes=payload.client_tz_offset_minutes,
            organization_id=org.id,
            db=db,
        )
        return ChatResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Assistant unavailable: {exc}")
