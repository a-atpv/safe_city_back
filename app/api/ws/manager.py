from typing import Dict, List, Any
from fastapi import WebSocket


class ConnectionManager:
    """
    Manages active WebSocket connections for real-time updates.
    Connections are indexed by user_id or guard_id.
    """

    def __init__(self):
        # Maps user_id / guard_id -> list of active websockets
        self.user_connections: Dict[int, List[WebSocket]] = {}
        self.guard_connections: Dict[int, List[WebSocket]] = {}

    # ---------------------------------------------------------
    # User Connections
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

    async def send_to_user(self, user_id: int, message: Dict[str, Any]):
        """Send a message to all active connections of a specific user."""
        if user_id in self.user_connections:
            for connection in self.user_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    # Connection might be stale, we cleanup on disconnect handler
                    pass

    # ---------------------------------------------------------
    # Guard Connections
    # ---------------------------------------------------------
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

    async def send_to_guard(self, guard_id: int, message: Dict[str, Any]):
        """Send a message to all active connections of a specific guard."""
        if guard_id in self.guard_connections:
            for connection in self.guard_connections[guard_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

    async def broadcast_to_guards(self, message: Dict[str, Any]):
        """Broadcast a message to all connected guards."""
        for guard_id in self.guard_connections:
            await self.send_to_guard(guard_id, message)


# Global instance
manager = ConnectionManager()
