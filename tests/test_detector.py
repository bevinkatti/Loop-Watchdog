from loop_watchdog.config import WatchdogSettings
from loop_watchdog.loop_detector import LoopDetector
from loop_watchdog.models import EventKind, WatchdogEvent


def test_detector_pauses_repeated_fix_break_pattern() -> None:
    settings = WatchdogSettings(
        pause_score_threshold=4.0,
        file_repeat_threshold=2,
        recent_window=8,
    )
    detector = LoopDetector(settings)
    events = [
        WatchdogEvent(session_id="demo", kind=EventKind.AGENT_REQUEST, summary="Fix parser test failure"),
        WatchdogEvent(
            session_id="demo",
            kind=EventKind.FILE_EDIT,
            summary="Retry parser patch",
            files=["src/parser.py", "tests/test_parser.py"],
        ),
        WatchdogEvent(
            session_id="demo",
            kind=EventKind.TEST_FAILURE,
            summary="test_parse_user still fails with NoneType",
            files=["src/parser.py", "tests/test_parser.py"],
            metadata={"error": "AssertionError: expected name, got NoneType"},
            error_signature="assertionerror expected name got nonetype",
        ),
        WatchdogEvent(session_id="demo", kind=EventKind.AGENT_REQUEST, summary="Fix parser test failure"),
        WatchdogEvent(
            session_id="demo",
            kind=EventKind.FILE_EDIT,
            summary="Retry parser patch again",
            files=["src/parser.py", "tests/test_parser.py"],
        ),
        WatchdogEvent(
            session_id="demo",
            kind=EventKind.TEST_FAILURE,
            summary="test_parse_user still fails with NoneType",
            files=["src/parser.py", "tests/test_parser.py"],
            metadata={"error": "AssertionError: expected name, got NoneType"},
            error_signature="assertionerror expected name got nonetype",
        ),
        WatchdogEvent(session_id="demo", kind=EventKind.AGENT_REQUEST, summary="Fix parser test failure"),
    ]

    decision = detector.evaluate(events)

    assert decision.paused is True
    assert decision.score >= settings.pause_score_threshold
    assert "src/parser.py" in decision.repeated_files
    assert decision.repeated_errors


def test_detector_allows_progress_when_success_arrives() -> None:
    settings = WatchdogSettings(
        pause_score_threshold=5.5,
        file_repeat_threshold=2,
        recent_window=8,
    )
    detector = LoopDetector(settings)
    events = [
        WatchdogEvent(session_id="demo", kind=EventKind.AGENT_REQUEST, summary="Fix auth bug"),
        WatchdogEvent(
            session_id="demo",
            kind=EventKind.FILE_EDIT,
            summary="Adjust token refresh logic",
            files=["src/auth.py"],
        ),
        WatchdogEvent(
            session_id="demo",
            kind=EventKind.TEST_FAILURE,
            summary="refresh token test still fails",
            files=["src/auth.py"],
            metadata={"error": "refresh token expired"},
            error_signature="refresh token expired",
        ),
        WatchdogEvent(session_id="demo", kind=EventKind.AGENT_REQUEST, summary="Fix auth bug"),
        WatchdogEvent(
            session_id="demo",
            kind=EventKind.FILE_EDIT,
            summary="Add missing issued-at comparison",
            files=["src/auth.py"],
        ),
        WatchdogEvent(
            session_id="demo",
            kind=EventKind.TEST_PASS,
            summary="auth refresh tests passed",
            files=["src/auth.py"],
        ),
    ]

    decision = detector.evaluate(events)

    assert decision.paused is False

