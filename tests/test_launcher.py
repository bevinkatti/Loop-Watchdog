from pathlib import Path

from loop_watchdog.launcher import (
    AUTO_SERVER_PERSISTENCE_ENV,
    CODEX_EXECUTABLE_ENV,
    PROVIDER_ID,
    SESSION_HEADER_ENV,
    build_codex_command,
    build_launch_context,
    build_proxy_endpoints,
    build_server_launch_context,
    build_session_id,
    resolve_codex_executable,
    resolve_workspace,
)


def test_resolve_workspace_prefers_codex_cd_flag(tmp_path) -> None:
    workspace = tmp_path / "demo-repo"
    workspace.mkdir()

    resolved = resolve_workspace(["-C", str(workspace)])

    assert resolved == workspace.resolve()


def test_build_session_id_sanitizes_parts(tmp_path) -> None:
    workspace = tmp_path / "Loop Watchdog Repo"
    workspace.mkdir()

    session_id = build_session_id(workspace, user="Abhishek", branch="feature/live-test")

    assert session_id == "loop-watchdog-repo:abhishek:feature-live-test"


def test_build_proxy_endpoints_normalizes_v1_url() -> None:
    endpoints = build_proxy_endpoints("http://127.0.0.1:8787/v1/")

    assert endpoints.proxy_url == "http://127.0.0.1:8787/v1"
    assert endpoints.health_url == "http://127.0.0.1:8787/healthz"
    assert endpoints.events_url == "http://127.0.0.1:8787/v1/watchdog/events"


def test_build_codex_command_injects_loop_watchdog_provider() -> None:
    command = build_codex_command(
        "C:/tools/codex.exe",
        "http://127.0.0.1:8787/v1",
        ["exec", "-m", "gpt-5.4"],
    )

    rendered = " ".join(command)
    assert command[:4] == ["C:/tools/codex.exe", "exec", "-m", "gpt-5.4"]
    assert f'model_provider="{PROVIDER_ID}"' in rendered
    assert 'model_providers.loop_watchdog.base_url="http://127.0.0.1:8787/v1"' in rendered
    assert "model_providers.loop_watchdog.requires_openai_auth=true" in rendered
    assert SESSION_HEADER_ENV in rendered


def test_resolve_codex_executable_prefers_env_override(tmp_path, monkeypatch) -> None:
    codex_executable = tmp_path / "codex.exe"
    codex_executable.write_text("", encoding="utf-8")
    monkeypatch.setenv(CODEX_EXECUTABLE_ENV, str(codex_executable))

    resolved = resolve_codex_executable()

    assert resolved == str(codex_executable)


def test_build_server_launch_context_sets_default_persistence_path(monkeypatch) -> None:
    monkeypatch.delenv(AUTO_SERVER_PERSISTENCE_ENV, raising=False)

    context = build_server_launch_context("http://127.0.0.1:8787/v1")
    persistence_path = Path(context.environment[AUTO_SERVER_PERSISTENCE_ENV])

    assert context.host == "127.0.0.1"
    assert context.port == 8787
    assert context.command[1:4] == ["-m", "loop_watchdog", "serve"]
    assert persistence_path.name == "state.json"
    assert persistence_path.parent.name == ".loop_watchdog"


def test_build_launch_context_uses_explicit_session_id(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    codex_executable = tmp_path / "codex.exe"
    codex_executable.write_text("", encoding="utf-8")

    context = build_launch_context(
        proxy_url="http://127.0.0.1:8787",
        extra_args=[],
        session_id="manual:session:id",
        codex_executable=str(codex_executable),
    )

    assert context.session_id == "manual:session:id"
    assert context.workspace == Path.cwd()
    assert context.endpoints.proxy_url == "http://127.0.0.1:8787/v1"
    assert context.codex_executable == str(codex_executable)
