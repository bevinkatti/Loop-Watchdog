import pytest
from pydantic import ValidationError

from loop_watchdog.models import EventKind, SessionIdentity, WatchdogEventCreate
from loop_watchdog.state import WatchdogStore
from loop_watchdog.config import WatchdogSettings
from loop_watchdog.loop_detector import LoopDetector

def test_session_identity_creation() -> None:
    identity = SessionIdentity(
        watchdog_session_id="unique-123",
        repository="my-repo",
        branch="main",
        agent="codex"
    )
    assert identity.watchdog_session_id == "unique-123"
    assert identity.repository == "my-repo"

def test_legacy_session_id_mapping() -> None:
    # Simulate an old payload that only sends the raw string
    event = WatchdogEventCreate(
        session_id="legacy:session:1",
        kind=EventKind.FILE_EDIT
    )
    assert event.identity is not None
    assert event.identity.watchdog_session_id == "legacy:session:1"
    assert event.identity.agent == "legacy"
    assert event.session_id == "legacy:session:1" # Ensures backwards compat

def test_independent_sessions_isolation() -> None:
    settings = WatchdogSettings(upstream_base_url="https://dummy")
    detector = LoopDetector(settings)
    store = WatchdogStore(settings, detector)
    
    # Same repo/branch, but different watchdog_session_id
    event1 = WatchdogEventCreate(
        identity=SessionIdentity(watchdog_session_id="session-A", repository="repo", branch="main"),
        kind=EventKind.FILE_EDIT
    )
    event2 = WatchdogEventCreate(
        identity=SessionIdentity(watchdog_session_id="session-B", repository="repo", branch="main"),
        kind=EventKind.FILE_EDIT
    )
    
    store.record_event(event1)
    store.record_event(event2)
    
    assert "session-A" in store._sessions
    assert "session-B" in store._sessions
    assert store._sessions["session-A"] is not store._sessions["session-B"]
    assert store._sessions["session-A"].identity.repository == "repo"

def test_event_serialization_with_identity() -> None:
    event = WatchdogEventCreate(
        identity=SessionIdentity(watchdog_session_id="ser-test", agent="gemini"),
        kind=EventKind.TEST_FAILURE
    )
    json_data = event.model_dump_json()
    parsed = WatchdogEventCreate.model_validate_json(json_data)
    assert parsed.identity.watchdog_session_id == "ser-test"
    assert parsed.identity.agent == "gemini"

def test_invalid_event_missing_both_ids() -> None:
    with pytest.raises(ValidationError):
        WatchdogEventCreate(kind=EventKind.FILE_EDIT)