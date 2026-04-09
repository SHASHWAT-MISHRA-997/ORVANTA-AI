"""
ORVANTA Cloud — WebSocket Connection Manager
Manages WebSocket connections per organization for real-time alerts.
"""

import json
from typing import Dict, List, Set
from fastapi import WebSocket
from app.core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections grouped by organization."""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, org_id: str):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        if org_id not in self.active_connections:
            self.active_connections[org_id] = set()
        self.active_connections[org_id].add(websocket)
        logger.info("ws_connected", org_id=org_id, total=len(self.active_connections[org_id]))

    def disconnect(self, websocket: WebSocket, org_id: str):
        """Remove a WebSocket connection."""
        if org_id in self.active_connections:
            self.active_connections[org_id].discard(websocket)
            if not self.active_connections[org_id]:
                del self.active_connections[org_id]
        logger.info("ws_disconnected", org_id=org_id)

    async def broadcast_to_org(self, org_id: str, message: dict):
        """Broadcast a message to all connections in an organization."""
        if org_id not in self.active_connections:
            return

        dead_connections = set()
        payload = json.dumps(message)

        for ws in self.active_connections[org_id]:
            try:
                await ws.send_text(payload)
            except Exception:
                dead_connections.add(ws)

        for ws in dead_connections:
            self.active_connections[org_id].discard(ws)

    async def broadcast_all(self, message: dict):
        """Broadcast to all connected clients across all orgs."""
        for org_id in list(self.active_connections.keys()):
            await self.broadcast_to_org(org_id, message)

    def get_connection_count(self, org_id: str = None) -> int:
        """Get number of active connections."""
        if org_id:
            return len(self.active_connections.get(org_id, set()))
        return sum(len(conns) for conns in self.active_connections.values())


# Global singleton
ws_manager = ConnectionManager()
