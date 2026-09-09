from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Connection Manager ───────────────────────────────────────────────────────

class ConnectionManager:
    """
    Manages all active WebSocket connections.
    When broadcast() is called (e.g., when a new alert is created),
    the message is sent to ALL connected clients — Web Portal AND Security Software.
    """

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.loop = None

    def set_loop(self, loop):
        self.loop = loop
        logger.info(f"[WS] Main event loop registered: {loop}")

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WS] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"[WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        data = json.dumps(message, default=str)
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def broadcast_sync(self, message: dict):
        """Thread-safe synchronous broadcast dispatch callable from worker threads."""
        import asyncio
        if self.loop is not None and self.loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)
                return
            except Exception as e:
                logger.debug(f"[WS] broadcast_sync run_coroutine_threadsafe failed: {e}")

        try:
            loop = asyncio.get_running_loop()
            asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
                else:
                    loop.run_until_complete(self.broadcast(message))
            except Exception as e:
                logger.debug(f"[WS] broadcast_sync fallback error: {e}")

    async def send_to(self, websocket: WebSocket, message: dict):
        """Send message to a specific client."""
        await websocket.send_text(json.dumps(message, default=str))



# ─── Singleton ────────────────────────────────────────────────────────────────

manager = ConnectionManager()


# ─── WebSocket Endpoint ───────────────────────────────────────────────────────

@router.websocket("/ws/alerts")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    # Send connection confirmation
    await manager.send_to(websocket, {
        "type": "SYSTEM",
        "data": {"message": "Connected to IBVAP WebSocket", "status": "ok"},
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
    })

    try:
        while True:
            data = await websocket.receive_text()
            # Handle ping/pong keepalive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
