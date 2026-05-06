import httpx
from fastapi.testclient import TestClient

from loop_watchdog.api import create_app
from loop_watchdog.config import WatchdogSettings
from loop_watchdog.provider import UpstreamProxy


def _transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Applied a safer fix."}}]},
        )

    return httpx.MockTransport(handler)


def _settings(**overrides) -> WatchdogSettings:
    return WatchdogSettings(
        upstream_base_url="https://upstream.example.com",
        persistence_enabled=False,
        **overrides,
    )


def test_proxy_pauses_session_after_repeat_pattern() -> None:
    settings = _settings(
        pause_score_threshold=4.0,
        file_repeat_threshold=2,
        recent_window=8,
    )
    proxy = UpstreamProxy(settings, transport=_transport())
    client = TestClient(create_app(settings=settings, upstream=proxy))

    session_headers = {"X-Loop-Session": "repo:user:main"}
    event_payloads = [
        {
            "session_id": "repo:user:main",
            "kind": "file_edit",
            "summary": "Retry parser patch",
            "files": ["src/parser.py", "tests/test_parser.py"],
        },
        {
            "session_id": "repo:user:main",
            "kind": "test_failure",
            "summary": "test_parse_user still fails with NoneType",
            "files": ["src/parser.py", "tests/test_parser.py"],
            "metadata": {"error": "AssertionError: expected name, got NoneType"},
        },
        {
            "session_id": "repo:user:main",
            "kind": "file_edit",
            "summary": "Retry parser patch again",
            "files": ["src/parser.py", "tests/test_parser.py"],
        },
        {
            "session_id": "repo:user:main",
            "kind": "test_failure",
            "summary": "test_parse_user still fails with NoneType",
            "files": ["src/parser.py", "tests/test_parser.py"],
            "metadata": {"error": "AssertionError: expected name, got NoneType"},
        },
    ]
    for payload in event_payloads:
        response = client.post("/v1/watchdog/events", json=payload)
        assert response.status_code == 202

    response = client.post(
        "/v1/chat/completions",
        headers=session_headers,
        json={"messages": [{"role": "user", "content": "Fix parser test failure"}]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["type"] == "loop_watchdog_paused"


def test_proxy_forwards_when_session_is_healthy() -> None:
    settings = _settings()
    proxy = UpstreamProxy(settings, transport=_transport())
    client = TestClient(create_app(settings=settings, upstream=proxy))

    response = client.post(
        "/v1/chat/completions",
        headers={"X-Loop-Session": "healthy:session"},
        json={"messages": [{"role": "user", "content": "Refactor this module safely"}]},
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Applied a safer fix."


def test_dashboard_routes_render_and_report_sessions() -> None:
    settings = _settings()
    proxy = UpstreamProxy(settings, transport=_transport())
    client = TestClient(create_app(settings=settings, upstream=proxy))

    html_response = client.get("/")
    assert html_response.status_code == 200
    assert "Detect repeat-fix loops" in html_response.text

    dashboard_response = client.get("/dashboard")
    assert dashboard_response.status_code == 200
    assert "Session intelligence and operator actions" in dashboard_response.text

    client.post(
        "/v1/watchdog/events",
        json={
            "session_id": "dashboard:demo",
            "kind": "file_edit",
            "summary": "Touched parser module",
            "files": ["src/parser.py"],
        },
    )
    snapshot_response = client.get("/v1/watchdog/dashboard")
    assert snapshot_response.status_code == 200
    payload = snapshot_response.json()
    assert payload["total_sessions"] == 1
    assert payload["sessions"][0]["session_id"] == "dashboard:demo"


def test_resume_with_reset_clears_recent_window() -> None:
    settings = _settings(
        pause_score_threshold=4.0,
        file_repeat_threshold=2,
        recent_window=8,
    )
    proxy = UpstreamProxy(settings, transport=_transport())
    client = TestClient(create_app(settings=settings, upstream=proxy))

    for payload in [
        {
            "session_id": "resume:demo",
            "kind": "file_edit",
            "summary": "Retry parser patch",
            "files": ["src/parser.py", "tests/test_parser.py"],
        },
        {
            "session_id": "resume:demo",
            "kind": "test_failure",
            "summary": "test_parse_user still fails",
            "files": ["src/parser.py", "tests/test_parser.py"],
            "metadata": {"error": "AssertionError: expected name, got NoneType"},
        },
        {
            "session_id": "resume:demo",
            "kind": "file_edit",
            "summary": "Retry parser patch again",
            "files": ["src/parser.py", "tests/test_parser.py"],
        },
        {
            "session_id": "resume:demo",
            "kind": "test_failure",
            "summary": "test_parse_user still fails",
            "files": ["src/parser.py", "tests/test_parser.py"],
            "metadata": {"error": "AssertionError: expected name, got NoneType"},
        },
    ]:
        client.post("/v1/watchdog/events", json=payload)

    blocked = client.post(
        "/v1/chat/completions",
        headers={"X-Loop-Session": "resume:demo"},
        json={"messages": [{"role": "user", "content": "Fix parser test failure"}]},
    )
    assert blocked.status_code == 409

    resumed = client.post(
        "/v1/watchdog/sessions/resume:demo/resume",
        json={
            "note": "Human rewrote the plan.",
            "clear_recent_events": True,
        },
    )
    assert resumed.status_code == 200
    assert resumed.json()["paused"] is False

    status = client.get("/v1/watchdog/status/resume:demo")
    assert status.status_code == 200
    assert status.json()["paused"] is False

    forwarded = client.post(
        "/v1/chat/completions",
        headers={"X-Loop-Session": "resume:demo"},
        json={"messages": [{"role": "user", "content": "Try a new approach now"}]},
    )
    assert forwarded.status_code == 200


def test_resume_with_changed_plan_requires_token() -> None:
    settings = _settings(
        pause_score_threshold=4.0,
        file_repeat_threshold=2,
        recent_window=8,
    )
    proxy = UpstreamProxy(settings, transport=_transport())
    client = TestClient(create_app(settings=settings, upstream=proxy))

    for payload in [
        {
            "session_id": "plan:demo",
            "kind": "file_edit",
            "summary": "Retry parser patch",
            "files": ["src/parser.py", "tests/test_parser.py"],
        },
        {
            "session_id": "plan:demo",
            "kind": "test_failure",
            "summary": "test_parse_user still fails",
            "files": ["src/parser.py", "tests/test_parser.py"],
            "metadata": {"error": "AssertionError: expected name, got NoneType"},
        },
        {
            "session_id": "plan:demo",
            "kind": "file_edit",
            "summary": "Retry parser patch again",
            "files": ["src/parser.py", "tests/test_parser.py"],
        },
        {
            "session_id": "plan:demo",
            "kind": "test_failure",
            "summary": "test_parse_user still fails",
            "files": ["src/parser.py", "tests/test_parser.py"],
            "metadata": {"error": "AssertionError: expected name, got NoneType"},
        },
    ]:
        client.post("/v1/watchdog/events", json=payload)

    client.post(
        "/v1/watchdog/sessions/plan:demo/resume",
        json={
            "note": "Human rewrote the plan.",
            "clear_recent_events": True,
            "cooldown_seconds": 0,
            "changed_plan": "Reproduce with tax-inclusive totals and rewrite rounding at the aggregator boundary.",
        },
    )

    blocked = client.post(
        "/v1/chat/completions",
        headers={"X-Loop-Session": "plan:demo"},
        json={"messages": [{"role": "user", "content": "Try a new approach now"}]},
    )
    assert blocked.status_code == 428
    assert blocked.json()["error"]["type"] == "loop_watchdog_plan_required"

    allowed = client.post(
        "/v1/chat/completions",
        headers={
            "X-Loop-Session": "plan:demo",
            "X-Loop-Plan": "Reproduce with tax-inclusive totals and rewrite rounding at the aggregator boundary.",
        },
        json={"messages": [{"role": "user", "content": "Try a new approach now"}]},
    )
    assert allowed.status_code == 200


def test_legacy_seed_demo_sessions_are_pruned_on_reload(tmp_path) -> None:
    persistence_path = tmp_path / "state.json"
    settings = WatchdogSettings(
        upstream_base_url="https://upstream.example.com",
        persistence_enabled=True,
        persistence_path=persistence_path,
    )
    proxy = UpstreamProxy(settings, transport=_transport())

    with persistence_path.open("w", encoding="utf-8") as handle:
        handle.write(
            """
{
  "version": 1,
  "sessions": [
    {
      "session_id": "demo:payments:main",
      "created_at": "2026-04-29T18:00:00Z",
      "updated_at": "2026-04-29T18:10:00Z",
      "events": [],
      "incident": null,
      "acknowledged_at": null,
      "acknowledged_note": "",
      "archived": false,
      "cooldown_until": null,
      "required_plan_digest": "",
      "required_plan_preview": ""
    },
    {
      "session_id": "real:user:main",
      "created_at": "2026-04-29T19:00:00Z",
      "updated_at": "2026-04-29T19:05:00Z",
      "events": [],
      "incident": null,
      "acknowledged_at": null,
      "acknowledged_note": "",
      "archived": false,
      "cooldown_until": null,
      "required_plan_digest": "",
      "required_plan_preview": ""
    }
  ]
}
            """.strip()
        )

    reloaded_client = TestClient(create_app(settings=settings, upstream=proxy))
    snapshot = reloaded_client.get("/v1/watchdog/dashboard?include_archived=true")
    assert snapshot.status_code == 200
    payload = snapshot.json()
    session_ids = {session["session_id"] for session in payload["sessions"]}
    assert "demo:payments:main" not in session_ids
    assert "real:user:main" in session_ids


def test_guided_trial_creates_paused_session() -> None:
    settings = _settings(
        pause_score_threshold=4.0,
        file_repeat_threshold=2,
        recent_window=8,
    )
    proxy = UpstreamProxy(settings, transport=_transport())
    client = TestClient(create_app(settings=settings, upstream=proxy))

    response = client.post("/v1/watchdog/demo/guided-trial")
    assert response.status_code == 201
    payload = response.json()
    assert payload["session_id"].startswith("trial:")
    assert payload["status"]["paused"] is True


def test_clear_history_removes_sessions_and_persistence(tmp_path) -> None:
    persistence_path = tmp_path / "state.json"
    settings = WatchdogSettings(
        upstream_base_url="https://upstream.example.com",
        persistence_enabled=True,
        persistence_path=persistence_path,
    )
    proxy = UpstreamProxy(settings, transport=_transport())
    client = TestClient(create_app(settings=settings, upstream=proxy))

    event_response = client.post(
        "/v1/watchdog/events",
        json={
            "session_id": "real:user:main",
            "kind": "file_edit",
            "summary": "Touched parser module",
            "files": ["src/parser.py"],
        },
    )
    assert event_response.status_code == 202
    assert persistence_path.exists()

    cleared = client.post("/v1/watchdog/history/clear", json={"note": "Reset local state."})
    assert cleared.status_code == 200
    cleared_payload = cleared.json()
    assert cleared_payload["total_sessions"] == 0
    assert cleared_payload["sessions"] == []

    snapshot = client.get("/v1/watchdog/dashboard")
    assert snapshot.status_code == 200
    payload = snapshot.json()
    assert payload["total_sessions"] == 0
    assert payload["paused_sessions"] == 0

    reloaded_client = TestClient(create_app(settings=settings, upstream=proxy))
    reloaded_snapshot = reloaded_client.get("/v1/watchdog/dashboard")
    assert reloaded_snapshot.status_code == 200
    reloaded_payload = reloaded_snapshot.json()
    assert reloaded_payload["total_sessions"] == 0
