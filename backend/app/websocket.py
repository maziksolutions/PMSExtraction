from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections per vessel.
    Tracks presence (which users are active on each vessel).
    """

    def __init__(self) -> None:
        # vessel_id -> {user_id -> WebSocket}
        self._connections: dict[str, dict[str, WebSocket]] = defaultdict(dict)
        # vessel_id -> {user_id -> user_info}
        self._presence: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    async def connect(
        self,
        websocket: WebSocket,
        vessel_id: str,
        user_id: str,
        user_info: dict[str, Any] | None = None,
    ) -> None:
        await websocket.accept()
        self._connections[vessel_id][user_id] = websocket
        self._presence[vessel_id][user_id] = user_info or {"user_id": user_id}
        await self.broadcast_to_vessel(
            vessel_id,
            {
                "type": "presence_update",
                "users": list(self._presence[vessel_id].values()),
            },
        )

    async def disconnect(self, vessel_id: str, user_id: str) -> None:
        self._connections[vessel_id].pop(user_id, None)
        self._presence[vessel_id].pop(user_id, None)
        if not self._connections[vessel_id]:
            del self._connections[vessel_id]
        await self.broadcast_to_vessel(
            vessel_id,
            {
                "type": "presence_update",
                "users": list(self._presence.get(vessel_id, {}).values()),
            },
        )

    async def broadcast_to_vessel(self, vessel_id: str, message: dict[str, Any]) -> None:
        """Send a message to all connected users on a vessel."""
        connections = self._connections.get(vessel_id, {})
        dead = []
        for uid, ws in connections.items():
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(uid)
        for uid in dead:
            await self.disconnect(vessel_id, uid)

    async def send_personal(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as exc:
            logger.warning("Failed to send personal message: %s", exc)

    def get_presence(self, vessel_id: str) -> list[dict[str, Any]]:
        return list(self._presence.get(vessel_id, {}).values())


manager = ConnectionManager()
