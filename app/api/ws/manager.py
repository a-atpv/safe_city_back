import json
import asyncio
import logging
from typing import Dict, List, Any, Optional
from fastapi import WebSocket
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages active WebSocket connections for real-time updates.
    Uses Redis Pub/Sub to synchronize messages across multiple worker processes.
    """

    def __init__(self):
        # Maps user_id / guard_id -> list of active websockets (local to this process)
        self.user_connections: Dict[int, List[WebSocket]] = {}
        self.guard_connections: Dict[int, List[WebSocket]] = {}
        self.redis_channel = "ws_notifications"
        self._listener_task: Optional[asyncio.Task] = None

    async def start_listening(self):
        """Starts a background task to listen for notification events from Redis."""
        self._listener_task = asyncio.create_task(self._listen_to_redis())
        logger.info("WebSocket Manager: Started listening to Redis Pub/Sub")

    async def stop_listening(self):
        """Stops the Redis background task."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            logger.info("WebSocket Manager: Stopped listening to Redis Pub/Sub")

    async def _listen_to_redis(self):
        """Background loop to forward Redis messages to local connections."""
        while True:
            try:
                redis = get_redis()
                # Wait until redis is initialized if called early
                while redis is None:
                    await asyncio.sleep(1)
                    redis = get_redis()

                pubsub = redis.pubsub()
                await pubsub.subscribe(self.redis_channel)
                
                logger.info(f"WebSocket Manager: Subscribed to Redis channel '{self.redis_channel}'")

                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            target_type = data.get("target_type")
                            target_id = data.get("target_id")
                            payload = data.get("payload")

                            if target_type == "user":
                                await self._send_local_user(target_id, payload)
                            elif target_type == "guard":
                                await self._send_local_guard(target_id, payload)
                            elif target_type == "broadcast_guards":
                                await self._broadcast_local_guards(payload)
                            elif target_type == "broadcast_all":
                                await self._broadcast_local_all(payload)
                        except json.JSONDecodeError:
                            logger.error(f"WebSocket Manager: Failed to decode Redis message: {message['data']}")
                        except Exception as e:
                            logger.error(f"WebSocket Manager: Error processing message: {e}")
            except Exception as e:
                logger.error(f"WebSocket Manager: Error in Redis listener loop: {e}")
                # Wait before retrying to avoid tight loop on persistent errors
                await asyncio.sleep(5)

    # ---------------------------------------------------------
    # Local Send Methods (Direct to connected clients in THIS process)
    # ---------------------------------------------------------
    async def _send_local_user(self, user_id: int, message: Dict[str, Any]):
        if user_id in self.user_connections:
            for connection in self.user_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

    async def _send_local_guard(self, guard_id: int, message: Dict[str, Any]):
        if guard_id in self.guard_connections:
            for connection in self.guard_connections[guard_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

    async def _broadcast_local_guards(self, message: Dict[str, Any]):
        for guard_id in list(self.guard_connections.keys()):
            await self._send_local_guard(guard_id, message)

    async def _broadcast_local_all(self, message: Dict[str, Any]):
        for user_id in list(self.user_connections.keys()):
            await self._send_local_user(user_id, message)
        for guard_id in list(self.guard_connections.keys()):
            await self._send_local_guard(guard_id, message)

    # ---------------------------------------------------------
    # Global Send Methods (Publish to Redis for all workers)
    # ---------------------------------------------------------
    async def send_to_user(self, user_id: int, message: Dict[str, Any]):
        """Publish a message to be sent to a specific user across all workers."""
        redis = get_redis()
        if redis:
            try:
                await redis.publish(self.redis_channel, json.dumps({
                    "target_type": "user",
                    "target_id": user_id,
                    "payload": message
                }))
                return
            except Exception as e:
                logger.warning(f"WebSocket Manager: Redis publish failed ({e}), falling back to local delivery")
        # Fallback to local if redis is not available or failed
        await self._send_local_user(user_id, message)

    async def send_to_guard(self, guard_id: int, message: Dict[str, Any]):
        """Publish a message to be sent to a specific guard across all workers."""
        redis = get_redis()
        if redis:
            try:
                await redis.publish(self.redis_channel, json.dumps({
                    "target_type": "guard",
                    "target_id": guard_id,
                    "payload": message
                }))
                return
            except Exception as e:
                logger.warning(f"WebSocket Manager: Redis publish failed ({e}), falling back to local delivery")
        await self._send_local_guard(guard_id, message)

    async def broadcast_to_guards(self, message: Dict[str, Any]):
        """Publish a message to be broadcast to all guards across all workers."""
        redis = get_redis()
        if redis:
            try:
                await redis.publish(self.redis_channel, json.dumps({
                    "target_type": "broadcast_guards",
                    "payload": message
                }))
                return
            except Exception as e:
                logger.warning(f"WebSocket Manager: Redis publish failed ({e}), falling back to local delivery")
        await self._broadcast_local_guards(message)

    # ---------------------------------------------------------
    # Connection Management
    # ---------------------------------------------------------
    async def connect_user(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.user_connections:
            self.user_connections[user_id] = []
        self.user_connections[user_id].append(websocket)

    def disconnect_user(self, user_id: int, websocket: WebSocket):
        if user_id in self.user_connections:
            if websocket in self.user_connections[user_id]:
                self.user_connections[user_id].remove(websocket)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

    async def connect_guard(self, guard_id: int, websocket: WebSocket):
        await websocket.accept()
        if guard_id not in self.guard_connections:
            self.guard_connections[guard_id] = []
        self.guard_connections[guard_id].append(websocket)

    def disconnect_guard(self, guard_id: int, websocket: WebSocket):
        if guard_id in self.guard_connections:
            if websocket in self.guard_connections[guard_id]:
                self.guard_connections[guard_id].remove(websocket)
            if not self.guard_connections[guard_id]:
                del self.guard_connections[guard_id]


# Global instance
manager = ConnectionManager()
