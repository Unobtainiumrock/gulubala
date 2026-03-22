"""Async coordination layer for presenter info-gathering calls.

When the navigator needs a missing field, it calls the presenter and
awaits the result here.  The Twilio ``<Gather>`` webhook resolves the
corresponding future so the navigator can resume.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GatherRequest:
    """Tracks a pending info-gather call to the presenter."""

    session_id: str
    field_name: str
    future: asyncio.Future[str] = field(compare=False, repr=False)


_lock = threading.Lock()
_pending: dict[str, GatherRequest] = {}


def _key(session_id: str, field_name: str) -> str:
    return f"{session_id}:{field_name}"


def create_gather_future(
    session_id: str,
    field_name: str,
    loop: asyncio.AbstractEventLoop,
) -> asyncio.Future[str]:
    """Register a future the navigator can ``await`` until the webhook fires."""
    fut: asyncio.Future[str] = loop.create_future()
    req = GatherRequest(session_id=session_id, field_name=field_name, future=fut)
    with _lock:
        _pending[_key(session_id, field_name)] = req
    return fut


def resolve_gather(session_id: str, field_name: str, value: str) -> bool:
    """Called by the Twilio webhook to deliver the gathered value.

    Returns ``True`` if a matching future was found and resolved.
    """
    with _lock:
        req = _pending.pop(_key(session_id, field_name), None)
    if req is None:
        logger.warning("No pending gather for session=%s field=%s", session_id, field_name)
        return False

    if req.future.done():
        logger.warning(
            "Ignoring late gather result session=%s field=%s (future already done)",
            session_id,
            field_name,
        )
        return False

    loop = req.future.get_loop()

    def _safe_set_result(fut: asyncio.Future[str], val: str) -> None:
        if not fut.done():
            fut.set_result(val)

    loop.call_soon_threadsafe(_safe_set_result, req.future, value)
    logger.info(
        "Resolved gather session=%s field=%s value=%s",
        session_id, field_name, value[:40],
    )
    return True


def cancel_gather(session_id: str, field_name: str) -> None:
    """Cancel a pending gather (e.g. presenter didn't answer)."""
    with _lock:
        req = _pending.pop(_key(session_id, field_name), None)
    if req is not None and not req.future.done():
        loop = req.future.get_loop()
        loop.call_soon_threadsafe(req.future.cancel)
