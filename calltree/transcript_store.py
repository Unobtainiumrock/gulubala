"""In-memory IVR navigator transcripts for dashboard / SMS links."""

from __future__ import annotations

import threading
from typing import Literal

TranscriptRole = Literal["ivr", "agent"]

_lock = threading.Lock()
_store: dict[str, list[dict[str, str]]] = {}


def record_transcript_turn(session_id: str, role: TranscriptRole, content: str) -> None:
    """Append one line to the session transcript (thread-safe)."""
    line = {"role": role, "content": content}
    with _lock:
        _store.setdefault(session_id, []).append(line)


def get_transcript(session_id: str) -> list[dict[str, str]] | None:
    """Return a copy of the transcript or None if unknown / empty."""
    with _lock:
        rows = _store.get(session_id)
        if not rows:
            return None
        return [dict(r) for r in rows]


def clear_transcript(session_id: str) -> None:
    with _lock:
        _store.pop(session_id, None)
