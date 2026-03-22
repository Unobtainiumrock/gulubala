"""WebSocket connection manager and route definitions."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from contracts.events import DashboardEvent

logger = logging.getLogger("call_center.dashboard")

router = APIRouter(tags=["dashboard"])

_MANAGER: ConnectionManager | None = None


def get_manager() -> ConnectionManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = ConnectionManager()
    return _MANAGER


class ConnectionManager:
    """Async-safe WebSocket pub/sub manager.

    Maintains two connection pools:
    - _session_connections: per-session subscribers
    - _global_connections: subscribers receiving all events
    """

    def __init__(self) -> None:
        self._session_connections: dict[str, list[WebSocket]] = {}
        self._global_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect_session(self, websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        async with self._lock:
            if session_id not in self._session_connections:
                self._session_connections[session_id] = []
            self._session_connections[session_id].append(websocket)

    async def connect_global(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._global_connections.append(websocket)

    async def disconnect_session(self, websocket: WebSocket, session_id: str) -> None:
        async with self._lock:
            conns = self._session_connections.get(session_id, [])
            if websocket in conns:
                conns.remove(websocket)
            if not conns:
                self._session_connections.pop(session_id, None)

    async def disconnect_global(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._global_connections:
                self._global_connections.remove(websocket)

    async def publish(self, event: DashboardEvent) -> None:
        """Broadcast an event to session-specific and global subscribers."""
        payload = event.model_dump_json()
        session_id = event.session_id

        async with self._lock:
            targets = list(self._session_connections.get(session_id, []))
            targets.extend(self._global_connections)

        stale: list[tuple[WebSocket, str | None]] = []
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                if ws in self._global_connections:
                    stale.append((ws, None))
                else:
                    stale.append((ws, session_id))

        for ws, sid in stale:
            if sid is None:
                await self.disconnect_global(ws)
            else:
                await self.disconnect_session(ws, sid)

    def publish_sync(self, event: DashboardEvent) -> None:
        """Fire-and-forget publish from synchronous code.

        Schedules the async publish onto the running event loop.
        Silently drops if no loop is running (CLI mode, tests).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        asyncio.run_coroutine_threadsafe(self.publish(event), loop)


@router.websocket("/ws/{session_id}")
async def ws_session(websocket: WebSocket, session_id: str) -> None:
    """Per-session WebSocket — receives only events for session_id."""
    manager = get_manager()
    await manager.connect_session(websocket, session_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect_session(websocket, session_id)


@router.websocket("/ws")
async def ws_global(websocket: WebSocket) -> None:
    """Global WebSocket — receives events for ALL sessions."""
    manager = get_manager()
    await manager.connect_global(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect_global(websocket)
