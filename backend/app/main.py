"""
ORVANTA Cloud — FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.db.database import init_db, AsyncSessionLocal
from app.websocket.manager import ws_manager
from app.core.security import decode_access_token
from app.services.official_mode import reclassify_events_official_only

# Import all models so they register with SQLAlchemy
import app.models  # noqa: F401

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    setup_logging()
    logger.info("warops_starting", env=settings.APP_ENV)

    # Initialize database tables
    await init_db()
    logger.info("database_initialized")

    if settings.OFFICIAL_ONLY_MODE:
        async with AsyncSessionLocal() as db:
            updated = await reclassify_events_official_only(db)
        logger.info("official_only_mode_applied", updated=updated)

    yield

    logger.info("warops_shutdown")


app = FastAPI(
    title="ORVANTA",
    description="Operations SaaS for verified event intelligence, analytics, risk scoring, alerts, and live management workflows",
    version="1.0.0",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    lifespan=lifespan,
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routers ──
from app.api.auth import router as auth_router
from app.api.events import router as events_router
from app.api.risk import router as risk_router
from app.api.alerts import router as alerts_router
from app.api.dashboard import router as dashboard_router
from app.api.organizations import router as organizations_router
from app.api.developer import router as developer_router
from app.api.watchlists import router as watchlists_router
from app.api.chat import router as chat_router

app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(events_router, prefix=settings.API_V1_PREFIX)
app.include_router(risk_router, prefix=settings.API_V1_PREFIX)
app.include_router(alerts_router, prefix=settings.API_V1_PREFIX)
app.include_router(dashboard_router, prefix=settings.API_V1_PREFIX)
app.include_router(organizations_router, prefix=settings.API_V1_PREFIX)
app.include_router(developer_router, prefix=settings.API_V1_PREFIX)
app.include_router(watchlists_router, prefix=settings.API_V1_PREFIX)
app.include_router(chat_router, prefix=settings.API_V1_PREFIX)


# ── Health Check ──
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": settings.APP_NAME, "version": "1.0.0"}


@app.get(f"{settings.API_V1_PREFIX}/health")
async def api_health():
    """API health check."""
    return {"status": "ok", "api_version": "v1"}


# ── WebSocket Endpoint ──
@app.websocket(f"{settings.API_V1_PREFIX}/ws/{{org_id}}")
async def websocket_endpoint(websocket: WebSocket, org_id: str):
    """
    WebSocket endpoint for real-time alerts.
    Clients connect with their org_id and receive broadcasts.
    """
    # Optional: validate token from query params
    token = websocket.query_params.get("token")
    if token:
        try:
            decode_access_token(token)
        except Exception:
            await websocket.close(code=4001)
            return

    await ws_manager.connect(websocket, org_id)
    try:
        while True:
            # Keep connection alive, listen for client messages
            data = await websocket.receive_text()
            # Echo back as acknowledgement
            await websocket.send_text(f'{{"type":"ack","message":"received"}}')
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, org_id)


# ── Global Exception Handler ──
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("unhandled_exception", error=str(exc), path=str(request.url))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
