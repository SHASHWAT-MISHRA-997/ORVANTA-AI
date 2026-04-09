"""
ORVANTA Cloud — Automation Engine
Trigger-based automation system that fires actions based on risk thresholds.
"""

import httpx
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.event import Event
from app.models.organization import Organization
from app.models.risk_score import RiskScore
from app.models.alert import Alert
from app.core.source_trust import classify_source
from app.services.alert_service import create_risk_alert
from app.websocket.manager import ws_manager
from app.core.logging import get_logger

logger = get_logger(__name__)


async def process_risk_automations(
    risk_score: RiskScore,
    event_title: str,
    organization_id: UUID,
    db: AsyncSession,
) -> dict:
    """
    Process automation rules for a computed risk score.
    Triggers: alerts, webhooks, WebSocket notifications.
    Returns summary of actions taken.
    """
    actions = {"alert_created": False, "webhook_sent": False, "websocket_sent": False}

    # Get org thresholds
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    org = result.scalar_one_or_none()
    if not org:
        return actions

    event_result = await db.execute(
        select(Event).where(Event.id == risk_score.event_id)
    )
    event = event_result.scalar_one_or_none()
    if not event:
        return actions

    trust = classify_source(event.source, event.source_url, event.raw_data)
    if trust.get("source_status") != "official":
        logger.info(
            "automation_skipped_non_official",
            event_id=str(event.id),
            source_status=trust.get("source_status"),
        )
        return actions

    threshold = float(org.risk_threshold_medium)

    # ── Rule 1: Create alert if score exceeds threshold ──
    if risk_score.overall_score >= threshold:
        alert = await create_risk_alert(
            organization_id=organization_id,
            event_title=event.title,
            risk_score=risk_score.overall_score,
            risk_level=risk_score.risk_level,
            event_id=risk_score.event_id,
            db=db,
            recommendations=risk_score.recommendations,
        )
        if alert:
            actions["alert_created"] = True

            # ── Rule 2: Broadcast via WebSocket ──
            try:
                await ws_manager.broadcast_to_org(
                    str(organization_id),
                    {
                        "type": "alert",
                        "data": {
                            "id": str(alert.id),
                            "title": alert.title,
                            "message": alert.message,
                            "priority": alert.priority.value,
                            "risk_score": risk_score.overall_score,
                            "created_at": alert.created_at.isoformat(),
                        },
                    },
                )
                alert.websocket_sent = True
                actions["websocket_sent"] = True
            except Exception as e:
                logger.error("websocket_broadcast_failed", error=str(e))

            # ── Rule 3: Fire webhook if configured ──
            if org.webhook_enabled and org.webhook_url:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.post(
                            org.webhook_url,
                            json={
                                "event": "risk_alert",
                                "alert_id": str(alert.id),
                                "title": alert.title,
                                "message": alert.message,
                                "priority": alert.priority.value,
                                "risk_score": risk_score.overall_score,
                                "risk_level": risk_score.risk_level,
                                "organization_id": str(organization_id),
                            },
                            headers={"Content-Type": "application/json"},
                        )
                        if response.status_code < 300:
                            alert.webhook_sent = True
                            actions["webhook_sent"] = True
                            logger.info("webhook_sent", url=org.webhook_url)
                        else:
                            logger.warning(
                                "webhook_failed",
                                status=response.status_code,
                                url=org.webhook_url,
                            )
                except Exception as e:
                    logger.error("webhook_error", error=str(e), url=org.webhook_url)

            await db.commit()

    return actions
