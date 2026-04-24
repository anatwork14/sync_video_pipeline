import asyncio
import json
import logging
from collections import defaultdict
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections grouped by session_id.
    Supports broadcasting events to all clients watching a session.
    """

    def __init__(self):
        # session_id → list of active WebSocket connections
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[session_id].append(websocket)
        logger.info(f"[WS] Client connected to session {session_id} (total: {len(self._connections[session_id])})")

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            try:
                self._connections[session_id].remove(websocket)
            except ValueError:
                pass  # Already removed
            if not self._connections.get(session_id):
                self._connections.pop(session_id, None)
        logger.info(f"[WS] Client disconnected from session {session_id}")

    async def broadcast(self, session_id: str, event: dict) -> None:
        """Send a JSON event to all clients subscribed to a session."""
        payload = json.dumps(event)
        dead: list[WebSocket] = []

        for ws in list(self._connections.get(session_id, [])):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        # Cleanup dead connections
        for ws in dead:
            await self.disconnect(session_id, ws)

    async def broadcast_all(self, event: dict) -> None:
        """Broadcast to ALL connected sessions (e.g. system announcements)."""
        for session_id in list(self._connections.keys()):
            await self.broadcast(session_id, event)


# Singleton instance used across the app
manager = ConnectionManager()
