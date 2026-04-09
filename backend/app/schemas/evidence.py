"""
Evidence link schemas shared across event and chat responses.
"""

from typing import Optional

from pydantic import BaseModel


class EvidenceLink(BaseModel):
    title: str
    url: str
    source: str
    host: Optional[str] = None
    kind: str = "reference"
    category: str = "unverified"
    verified: bool = False
    reason: Optional[str] = None
    published_at: Optional[str] = None
