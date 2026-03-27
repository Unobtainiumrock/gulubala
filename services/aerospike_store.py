"""Aerospike-backed session persistence."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from config.models import (
    AEROSPIKE_HOSTS,
    AEROSPIKE_NAMESPACE,
    AEROSPIKE_SET,
    SESSION_TTL_SECONDS,
)
from contracts.models import SessionState


class AerospikeSessionStore:
    """Session store backed by Aerospike with server-side TTL expiry."""

    def __init__(
        self,
        *,
        hosts: str = AEROSPIKE_HOSTS,
        namespace: str = AEROSPIKE_NAMESPACE,
        set_name: str = AEROSPIKE_SET,
        ttl_seconds: int = SESSION_TTL_SECONDS,
        client: Any | None = None,
        aerospike_module: Any | None = None,
    ):
        self.hosts = hosts
        self.namespace = namespace
        self.set_name = set_name
        self._ttl = ttl_seconds
        self._aerospike = aerospike_module
        self._client = client if client is not None else self._connect_client()

    def create_session(
        self,
        channel: str = "text",
        session_id: str | None = None,
    ) -> SessionState:
        session = SessionState(channel=channel, session_id=session_id or uuid4().hex)
        return self.save_session(session)

    def get_session(self, session_id: str) -> SessionState | None:
        key = self._record_key(session_id)
        try:
            _key, _meta, bins = self._client.get(key)
        except Exception as exc:  # pragma: no cover - error type depends on installed client
            if self._is_record_not_found(exc):
                return None
            raise

        state_json = bins.get("state_json")
        if not isinstance(state_json, str):
            return None
        return SessionState.model_validate_json(state_json)

    def save_session(self, session: SessionState) -> SessionState:
        key = self._record_key(session.session_id)
        self._client.put(
            key,
            {"state_json": session.model_dump_json()},
            meta={"ttl": self._ttl},
        )
        return session

    def cleanup_expired(self) -> int:
        """Aerospike expires records natively using TTL."""

        return 0

    def close(self) -> None:
        """Close the underlying Aerospike client when supported."""

        close = getattr(self._client, "close", None)
        if callable(close):
            close()

    def _connect_client(self):
        aerospike = self._aerospike or self._import_aerospike()
        self._aerospike = aerospike
        config = {"hosts": _parse_hosts(self.hosts)}
        return aerospike.client(config).connect()

    def _record_key(self, session_id: str) -> tuple[str, str, str]:
        return (self.namespace, self.set_name, session_id)

    def _is_record_not_found(self, exc: Exception) -> bool:
        aerospike = self._aerospike
        exception_module = (
            getattr(aerospike, "exception", None) if aerospike is not None else None
        )
        record_not_found = getattr(exception_module, "RecordNotFound", None)
        if record_not_found is not None and isinstance(exc, record_not_found):
            return True
        return exc.__class__.__name__ == "RecordNotFound"

    @staticmethod
    def _import_aerospike():
        try:
            import aerospike
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on local install
            raise ModuleNotFoundError(
                "Aerospike support requires the 'aerospike' package. "
                "Install requirements.txt or pass an injected client when testing."
            ) from exc
        return aerospike


def _parse_hosts(hosts: str) -> list[tuple[str, int]]:
    parsed: list[tuple[str, int]] = []
    for item in hosts.split(","):
        host = item.strip()
        if not host:
            continue
        if ":" in host:
            hostname, port = host.rsplit(":", 1)
            parsed.append((hostname.strip(), int(port.strip())))
        else:
            parsed.append((host, 3000))
    return parsed or [("127.0.0.1", 3000)]
