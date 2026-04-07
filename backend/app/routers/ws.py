import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ws.manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(session_id: str, websocket: WebSocket):
    """
    WebSocket endpoint for real-time session status updates.

    Clients connect with: ws://host/ws/{session_id}

    Events pushed from server:
      { "type": "chunk_uploaded",   "session_id": "...", "chunk_index": N, "cam_id": "camA" }
      { "type": "processing_started", "session_id": "...", "chunk_index": N }
      { "type": "chunk_done",       "session_id": "...", "chunk_index": N, "url": "/static/synced/..." }
      { "type": "error",            "session_id": "...", "message": "..." }
    """
    await manager.connect(session_id, websocket)
    try:
        # Keep connection alive — receive pings/client messages
        while True:
            data = await websocket.receive_text()
            # Optionally handle client-side commands (e.g. {"action": "ping"})
            if data == '{"action":"ping"}':
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        await manager.disconnect(session_id, websocket)
        logger.info(f"WebSocket disconnected: session={session_id}")
