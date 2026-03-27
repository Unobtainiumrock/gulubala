"""Coverage for the Aerospike session store."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from contracts.models import SessionState
from services.aerospike_store import AerospikeSessionStore, _parse_hosts


class FakeRecordNotFound(Exception):
    pass


class FakeAerospikeClient:
    def __init__(self):
        self.records: dict[tuple[str, str, str], dict[str, object]] = {}
        self.closed = False

    def get(self, key):
        if key not in self.records:
            raise FakeRecordNotFound("missing record")
        record = self.records[key]
        return key, record["meta"], record["bins"]

    def put(self, key, bins, meta=None):
        self.records[key] = {"bins": bins, "meta": meta or {}}

    def close(self):
        self.closed = True


class FakeAerospikeFactory:
    def __init__(self):
        self.config = None
        self.client_instance = FakeAerospikeClient()
        self.exception = SimpleNamespace(RecordNotFound=FakeRecordNotFound)

    def client(self, config):
        self.config = config
        return self

    def connect(self):
        return self.client_instance


class TestParseHosts:
    def test_parses_comma_separated_hosts_and_ports(self):
        assert _parse_hosts("10.0.0.1:3000, 10.0.0.2:3001") == [
            ("10.0.0.1", 3000),
            ("10.0.0.2", 3001),
        ]

    def test_uses_default_port_when_missing(self):
        assert _parse_hosts("127.0.0.1") == [("127.0.0.1", 3000)]


class TestAerospikeSessionStore:
    def test_create_and_get_session_round_trip(self):
        client = FakeAerospikeClient()
        store = AerospikeSessionStore(client=client, ttl_seconds=90)

        created = store.create_session(channel="voice", session_id="session-1")
        loaded = store.get_session("session-1")

        assert loaded is not None
        assert loaded.session_id == "session-1"
        assert loaded.channel == "voice"
        assert created.session_id == loaded.session_id
        assert client.records[("test", "sessions", "session-1")]["meta"] == {"ttl": 90}

    def test_save_session_writes_state_json(self):
        client = FakeAerospikeClient()
        store = AerospikeSessionStore(
            client=client,
            namespace="hackathon",
            set_name="call_sessions",
            ttl_seconds=120,
        )
        session = SessionState(session_id="session-2", channel="api")
        session.intent = "password_reset"

        store.save_session(session)

        record = client.records[("hackathon", "call_sessions", "session-2")]
        assert record["meta"] == {"ttl": 120}
        assert "\"intent\":\"password_reset\"" in record["bins"]["state_json"]

    def test_get_session_returns_none_for_missing_record(self):
        aerospike_module = SimpleNamespace(
            exception=SimpleNamespace(RecordNotFound=FakeRecordNotFound)
        )
        store = AerospikeSessionStore(
            client=FakeAerospikeClient(),
            aerospike_module=aerospike_module,
        )

        assert store.get_session("missing-session") is None

    def test_cleanup_expired_is_noop_with_native_ttl(self):
        store = AerospikeSessionStore(client=FakeAerospikeClient())

        assert store.cleanup_expired() == 0

    def test_close_closes_underlying_client(self):
        client = FakeAerospikeClient()
        store = AerospikeSessionStore(client=client)

        store.close()

        assert client.closed is True

    def test_builds_client_from_aerospike_module(self):
        aerospike_factory = FakeAerospikeFactory()

        store = AerospikeSessionStore(
            hosts="10.0.0.1:3000,10.0.0.2:3001",
            namespace="hackathon",
            set_name="call_sessions",
            aerospike_module=aerospike_factory,
        )

        assert aerospike_factory.config == {
            "hosts": [("10.0.0.1", 3000), ("10.0.0.2", 3001)],
        }
        assert store.namespace == "hackathon"
        assert store.set_name == "call_sessions"

    def test_raises_helpful_error_when_dependency_missing(self):
        with pytest.raises(ModuleNotFoundError) as excinfo:
            AerospikeSessionStore(
                aerospike_module=None,
                client=None,
                hosts="127.0.0.1:3000",
            )

        assert "aerospike" in str(excinfo.value).lower()
