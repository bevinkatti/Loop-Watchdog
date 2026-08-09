import pytest
from pydantic import ValidationError

from loop_watchdog.models import EventKind, WatchdogEvent, WatchdogEventCreate


def test_event_kind_v1_values() -> None:
    assert EventKind("agent_request") == EventKind.AGENT_REQUEST
    assert EventKind("file_edit") == EventKind.FILE_EDIT
    assert EventKind("test_failure") == EventKind.TEST_FAILURE


def test_event_kind_v2_values() -> None:
    assert EventKind("tool_call") == EventKind.TOOL_CALL
    assert EventKind("build_success") == EventKind.BUILD_SUCCESS
    assert EventKind("git_commit") == EventKind.GIT_COMMIT


def test_event_kind_categories() -> None:
    assert EventKind.TEST_PASS.is_progress is True
    assert EventKind.BUILD_SUCCESS.is_progress is True
    assert EventKind.AGENT_REQUEST.is_progress is False
    assert EventKind.TEST_FAILURE.is_failure is True
    assert EventKind.BUILD_FAILURE.is_failure is True
    assert EventKind.LINT_FAILURE.is_failure is True
    assert EventKind.AGENT_RESPONSE.is_failure is False
    assert EventKind.FILE_EDIT.is_file_modification is True
    assert EventKind.FILE_DELETE.is_file_modification is True
    assert EventKind.GIT_COMMIT.is_file_modification is False


def test_event_kind_is_v1() -> None:
    assert EventKind.AGENT_REQUEST.is_v1 is True
    assert EventKind.FILE_EDIT.is_v1 is True
    assert EventKind.TOOL_CALL.is_v1 is False


def test_valid_event_creation() -> None:
    event = WatchdogEventCreate(
        session_id="repo:user:main",
        kind=EventKind.FILE_EDIT,
        summary="Changed parser logic",
        files=["src/parser.py"],
    )
    assert event.schema_version == 1
    assert event.session_id == "repo:user:main"
    assert event.kind == EventKind.FILE_EDIT


def test_event_versioning() -> None:
    event = WatchdogEventCreate(
        schema_version=2,
        session_id="test:session",
        kind=EventKind.TOOL_CALL,
    )
    assert event.schema_version == 2


def test_invalid_event_missing_session_id() -> None:
    with pytest.raises(ValidationError):
        WatchdogEventCreate(kind=EventKind.FILE_EDIT, summary="No session id provided")


def test_invalid_event_empty_session_id() -> None:
    with pytest.raises(ValidationError):
        WatchdogEventCreate(session_id="", kind=EventKind.FILE_EDIT)


def test_invalid_event_invalid_kind() -> None:
    with pytest.raises(ValidationError):
        WatchdogEventCreate(session_id="test:session", kind="nonexistent_event_kind")


def test_invalid_event_invalid_schema_version() -> None:
    with pytest.raises(ValidationError):
        WatchdogEventCreate(schema_version=0, session_id="test:session", kind=EventKind.FILE_EDIT)


def test_backwards_compatibility_without_version() -> None:
    payload = {
        "session_id": "legacy:session",
        "kind": "file_edit",
        "summary": "Retro event without schema_version",
        "files": ["old.py"],
        "metadata": {},
    }
    event = WatchdogEventCreate(**payload)
    assert event.schema_version == 1
    assert event.kind == EventKind.FILE_EDIT


def test_serialization_and_deserialization() -> None:
    event = WatchdogEvent(
        session_id="test:session",
        kind=EventKind.BUILD_FAILURE,
        summary="Build failed",
        files=["src/main.py"],
        metadata={"error": "syntax error"},
    )
    json_data = event.model_dump_json()
    parsed_event = WatchdogEvent.model_validate_json(json_data)
    assert parsed_event.schema_version == 1
    assert parsed_event.session_id == "test:session"
    assert parsed_event.kind == EventKind.BUILD_FAILURE
    assert parsed_event.metadata == {"error": "syntax error"}


def test_watchdog_event_inherits_defaults() -> None:
    event = WatchdogEvent(session_id="defaults:session", kind=EventKind.AGENT_REQUEST)
    assert event.event_id is not None
    assert len(event.event_id) == 36
    assert event.created_at is not None
    assert event.fingerprint == ""
    assert event.error_signature == ""
