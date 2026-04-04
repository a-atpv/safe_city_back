from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import get_db
from app.api.deps import get_ws_current_user, get_ws_current_guard
from app.api.ws.manager import manager
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["WebSockets"])


@router.websocket("/user")
async def websocket_user_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    WebSocket endpoint for users to receive real-time updates about their emergency calls.
    Usage: ws://host:port/api/v1/ws/user?token=YOUR_JWT_TOKEN
    """
    # Create a local session for authentication
    from app.core.database import async_session
    async with async_session() as db:
        user = await get_ws_current_user(db, token)
        if not user:
            await websocket.close(code=1008)  # Policy Violation
            return

        await manager.connect_user(user.id, websocket)
        logger.info(f"User {user.id} connected to WebSocket")
        
        try:
            while True:
                # Keep connection alive and wait for client messages (if any)
                data = await websocket.receive_text()
                # Users shouldn't need to send anything for now, but we keep the loop
                await websocket.send_json({"status": "received", "echo": data})
        except WebSocketDisconnect:
            manager.disconnect_user(user.id, websocket)
            logger.info(f"User {user.id} disconnected from WebSocket")
        except Exception as e:
            manager.disconnect_user(user.id, websocket)
            logger.error(f"WebSocket error for user {user.id}: {e}")


@router.websocket("/guard")
async def websocket_guard_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    WebSocket endpoint for guards to receive new call offers and status updates.
    Usage: ws://host:port/api/v1/ws/guard?token=YOUR_JWT_TOKEN
    """
    from app.core.database import async_session
    async with async_session() as db:
        guard = await get_ws_current_guard(db, token)
        if not guard:
            await websocket.close(code=1008)
            return

        await manager.connect_guard(guard.id, websocket)
        logger.info(f"Guard {guard.id} connected to WebSocket")

        try:
            while True:
                data = await websocket.receive_text()
                # Maybe handle guard location updates via WS in the future
                await websocket.send_json({"status": "received", "echo": data})
        except WebSocketDisconnect:
            manager.disconnect_guard(guard.id, websocket)
            logger.info(f"Guard {guard.id} disconnected from WebSocket")
        except Exception as e:
            manager.disconnect_guard(guard.id, websocket)
            logger.error(f"WebSocket error for guard {guard.id}: {e}")
