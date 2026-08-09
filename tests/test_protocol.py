import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from loop_watchdog.api import create_app
from loop_watchdog.config import WatchdogSettings
from loop_watchdog.models import EventKind, WatchdogEventCreate
from loop_watchdog.protocol import (
    PROTOCOL_VERSION,
    LoopWatchdogEnvelope,
    ProtocolEventPayload,
    envelope_to_event,
    event_to_envelope,
    parse_event_payload,
)
from loop_watchdog.provider import UpstreamProxy


def _envelope_dict(**overrides) -> dict:
    base = {
        "version": "1",
        "session": {
            "watchdog_session_id": "repo:user:main",
            "agent": "claude-code",
            "repository": "acme/api",
            "branch": "main",
        },
        "event": {
            "type": "test_failure",
            "summary": "test_totals failed",
            "files": ["src/totals.py"],
            "metadata": {"error": "AssertionError"},
        },
    }
    base.update(overrides)
    return base


def _transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    return httpx.MockTransport(handler)


def _client() -> TestClient:
    settings = WatchdogSettings(
        upstream_base_url="https://upstream.example.com",
        persistence_enabled=False,
    )
    proxy = UpstreamProxy(settings, transport=_transport())
    return TestClient(create_app(settings=settings, upstream=proxy))


# --- Unit tests: parsing -------------------------------------------------


def test_parse_lwep_envelope() -> None:
    event = parse_event_payload(_envelope_dict())
    assert isinstance(event, WatchdogEventCreate)
    assert event.kind == EventKind.TEST_FAILURE
    assert event.identity.watchdog_session_id == "repo:user:main"
    assert event.identity.agent == "claude-code"
    assert event.session_id == "repo:user:main"
    assert event.metadata["_lwep_event_id"]


def test_parse_legacy_flat_format() -> None:
    legacy = {
        "session_id": "legacy:session",
        "kind": "file_edit",
        "summary": "edited parser",
        "files": ["src/parser.py"],
    }
    event = parse_event_payload(legacy)
    assert event.kind == EventKind.FILE_EDIT
    assert event.identity.watchdog_session_id == "legacy:session"
    assert event.identity.agent == "legacy"


def test_reject_unsupported_version() -> None:
    with pytest.raises((ValueError, ValidationError)):
        parse_event_payload(_envelope_dict(version="99"))


def test_reject_invalid_event_type() -> None:
    payload = _envelope_dict()
    payload["event"]["type"] = "not_a_real_event"
    with pytest.raises((ValueError, ValidationError)):
        parse_event_payload(payload)


def test_reject_missing_session() -> None:
    payload = _envelope_dict()
    del payload["session"]
    with pytest.raises((ValueError, ValidationError)):
        parse_event_payload(payload)


def test_reject_non_object_payload() -> None:
    with pytest.raises(ValueError):
        parse_event_payload(["not", "an", "object"])


# --- Unit tests: round trip + serialization ------------------------------


def test_envelope_round_trip() -> None:
    envelope = LoopWatchdogEnvelope.model_validate(_envelope_dict())
    event = envelope_to_event(envelope)
    rebuilt = event_to_envelope(event)
    assert rebuilt.version == PROTOCOL_VERSION
    assert rebuilt.session.watchdog_session_id == envelope.session.watchdog_session_id
    assert rebuilt.event.type == envelope.event.type
    assert rebuilt.event.files == envelope.event.files
    assert rebuilt.event.id == envelope.event.id


def test_envelope_serialization() -> None:
    envelope = LoopWatchdogEnvelope.model_validate(_envelope_dict())
    rebuilt = LoopWatchdogEnvelope.model_validate_json(envelope.model_dump_json())
    assert rebuilt == envelope


def test_default_event_id_generated() -> None:
    payload = ProtocolEventPayload(type="test_pass")
    assert payload.id
    assert len(payload.id) == 36


# --- Integration tests: HTTP endpoint ------------------------------------


def test_api_accepts_lwep_envelope() -> None:
    client = _client()
    response = client.post("/v1/watchdog/events", json=_envelope_dict())
    assert response.status_code == 202
    body = response.json()
    assert body["session_id"] == "repo:user:main"
    assert body["identity"]["agent"] == "claude-code"


def test_api_accepts_legacy_format() -> None:
    client = _client()
    legacy = {"session_id": "legacy:x", "kind": "file_edit", "summary": "s"}
    response = client.post("/v1/watchdog/events", json=legacy)
    assert response.status_code == 202
    assert response.json()["session_id"] == "legacy:x"


def test_api_rejects_invalid_envelope() -> None:
    client = _client()
    bad = _envelope_dict()
    bad["event"]["type"] = "not_a_real_event"
    response = client.post("/v1/watchdog/events", json=bad)
    assert response.status_code == 422
