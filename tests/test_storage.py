import json
from datetime import timedelta

from loop_watchdog.config import WatchdogSettings
from loop_watchdog.loop_detector import LoopDetector
from loop_watchdog.models import (
    EventKind,
    PersistedSessionState,
    PersistedStore,
    WatchdogEventCreate,
    utc_now,
)
from loop_watchdog.state import WatchdogStore
from loop_watchdog.storage import JsonSessionStore

# --- JsonSessionStore unit tests -----------------------------------------


def test_json_store_load_missing_file_returns_empty(tmp_path) -> None:
    store = JsonSessionStore(tmp_path / "state.json")
    result = store.load()
    assert isinstance(result, PersistedStore)
    assert result.sessions == []


def test_json_store_save_and_load_round_trip(tmp_path) -> None:
    path = tmp_path / "state.json"
    store = JsonSessionStore(path)
    now = utc_now()
    session = PersistedSessionState(
        session_id="test:session",
        created_at=now,
        updated_at=now,
    )
    store.save(PersistedStore(sessions=[session]))
    loaded = store.load()
    assert len(loaded.sessions) == 1
    assert loaded.sessions[0].session_id == "test:session"


def test_json_store_load_corrupt_file_returns_empty(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text("not valid json {{{", encoding="utf-8")
    store = JsonSessionStore(path)
    result = store.load()
    assert result.sessions == []


def test_json_store_creates_parent_directories(tmp_path) -> None:
    path = tmp_path / "nested" / "dir" / "state.json"
    store = JsonSessionStore(path)
    store.save(PersistedStore())
    assert path.exists()


# --- WatchdogStore integration tests -------------------------------------


def test_watchdog_store_persists_and_reloads(tmp_path) -> None:
    path = tmp_path / "state.json"
    settings = WatchdogSettings(
        upstream_base_url="https://upstream.example.com",
        persistence_enabled=True,
        persistence_path=path,
    )
    store1 = WatchdogStore(settings, LoopDetector(settings))
    store1.record_event(
        WatchdogEventCreate(session_id="persist:test", kind=EventKind.FILE_EDIT, summary="edit")
    )

    store2 = WatchdogStore(settings, LoopDetector(settings))
    status = store2.get_status("persist:test")
    assert status.event_count == 1
    assert status.identity.watchdog_session_id == "persist:test"


def test_watchdog_store_accepts_injected_backend(tmp_path) -> None:
    injected_path = tmp_path / "injected.json"
    backend = JsonSessionStore(injected_path)
    settings = WatchdogSettings(
        upstream_base_url="https://upstream.example.com",
        persistence_enabled=True,
        persistence_path=tmp_path / "should_not_be_used.json",
    )
    store = WatchdogStore(settings, LoopDetector(settings), store=backend)
    store.record_event(
        WatchdogEventCreate(session_id="inject:test", kind=EventKind.FILE_EDIT, summary="edit")
    )
    assert injected_path.exists()
    assert not (tmp_path / "should_not_be_used.json").exists()


def test_watchdog_store_loads_legacy_json_without_identity(tmp_path) -> None:
    path = tmp_path / "state.json"
    now = utc_now()
    legacy = {
        "version": 1,
        "sessions": [
            {
                "session_id": "legacy:session",
                "created_at": (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
                "updated_at": (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                "events": [],
                "incident": None,
                "acknowledged_at": None,
                "acknowledged_note": "",
                "archived": False,
                "cooldown_until": None,
                "required_plan_digest": "",
                "required_plan_preview": "",
            }
        ],
    }
    path.write_text(json.dumps(legacy), encoding="utf-8")
    settings = WatchdogSettings(
        upstream_base_url="https://upstream.example.com",
        persistence_enabled=True,
        persistence_path=path,
    )
    store = WatchdogStore(settings, LoopDetector(settings))
    status = store.get_status("legacy:session")
    assert status.identity.watchdog_session_id == "legacy:session"
