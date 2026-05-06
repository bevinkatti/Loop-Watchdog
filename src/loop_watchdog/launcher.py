from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from .models import EventKind

IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".sl",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".next",
    ".turbo",
    ".idea",
    ".vscode",
    ".loop_watchdog",
}

SESSION_HEADER_ENV = "LOOP_WATCHDOG_SESSION"
PROVIDER_ID = "loop_watchdog"
CODEX_EXECUTABLE_ENV = "LOOP_WATCHDOG_CODEX_EXECUTABLE"
AUTO_SERVER_PERSISTENCE_ENV = "LOOP_WATCHDOG_PERSISTENCE_PATH"


def sanitize_session_part(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-")
    return cleaned or fallback


def resolve_workspace(extra_args: list[str], default: Path | None = None) -> Path:
    workspace = default or Path.cwd()
    index = 0
    while index < len(extra_args):
        token = extra_args[index]
        if token == "-C" and index + 1 < len(extra_args):
            return Path(extra_args[index + 1]).expanduser().resolve()
        if token == "--cd" and index + 1 < len(extra_args):
            return Path(extra_args[index + 1]).expanduser().resolve()
        if token.startswith("--cd="):
            return Path(token.split("=", 1)[1]).expanduser().resolve()
        index += 1
    return workspace.expanduser().resolve()


def detect_git_branch(workspace: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(workspace),
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None
    branch = result.stdout.strip()
    if not branch or branch == "HEAD":
        return None
    return branch


def build_session_id(workspace: Path, user: str | None = None, branch: str | None = None) -> str:
    repo = sanitize_session_part(workspace.name or "workspace", "workspace")
    actor = sanitize_session_part(user or getpass.getuser() or "operator", "operator")
    branch_name = sanitize_session_part(
        branch or detect_git_branch(workspace) or "workspace",
        "workspace",
    )
    return f"{repo}:{actor}:{branch_name}"


@dataclass(frozen=True)
class ProxyEndpoints:
    proxy_url: str
    health_url: str
    events_url: str


@dataclass(frozen=True)
class ServerLaunchContext:
    host: str
    port: int
    command: list[str]
    environment: dict[str, str]


def build_proxy_endpoints(proxy_url: str) -> ProxyEndpoints:
    cleaned = proxy_url.rstrip("/")
    parts = urlsplit(cleaned)
    path = parts.path or ""
    if path.endswith("/v1"):
        root_path = path[: -len("/v1")] or ""
        api_path = path
    else:
        root_path = path
        api_path = f"{path}/v1" if path else "/v1"
    base_root = urlunsplit((parts.scheme, parts.netloc, root_path, "", ""))
    base_api = urlunsplit((parts.scheme, parts.netloc, api_path, "", ""))
    return ProxyEndpoints(
        proxy_url=base_api,
        health_url=f"{base_root}/healthz",
        events_url=f"{base_api}/watchdog/events",
    )


def resolve_codex_executable(explicit_path: str | None = None) -> str:
    candidates: list[str | Path | None] = [
        explicit_path,
        os.environ.get(CODEX_EXECUTABLE_ENV),
        shutil.which("codex"),
        shutil.which("codex.exe"),
    ]

    home = Path.home()
    vscode_extensions = home / ".vscode" / "extensions"
    if vscode_extensions.exists():
        for extension_dir in sorted(
            vscode_extensions.glob("openai.chatgpt-*"),
            reverse=True,
        ):
            candidates.append(extension_dir / "bin" / "windows-x86_64" / "codex.exe")

    for candidate in candidates:
        if not candidate:
            continue
        resolved = Path(candidate).expanduser()
        if resolved.is_file():
            return str(resolved)

    raise FileNotFoundError(
        "Could not locate codex.exe. Install Codex, ensure it is on PATH, or set "
        f"{CODEX_EXECUTABLE_ENV} to the full executable path."
    )


def build_codex_command(
    codex_executable: str,
    proxy_url: str,
    extra_args: list[str],
) -> list[str]:
    config_overrides = [
        "-c",
        f'model_provider="{PROVIDER_ID}"',
        "-c",
        f'model_providers.{PROVIDER_ID}.name="Loop Watchdog"',
        "-c",
        f'model_providers.{PROVIDER_ID}.base_url="{proxy_url}"',
        "-c",
        f"model_providers.{PROVIDER_ID}.requires_openai_auth=true",
        "-c",
        (
            "model_providers."
            f'{PROVIDER_ID}.env_http_headers={{"X-Loop-Session" = "{SESSION_HEADER_ENV}"}}'
        ),
    ]
    return [codex_executable, *extra_args, *config_overrides]


def ensure_proxy_available(health_url: str) -> tuple[bool, str]:
    try:
        response = httpx.get(health_url, timeout=2.0)
    except httpx.HTTPError as exc:
        return False, f"Could not reach Loop Watchdog at {health_url}: {exc}"
    if response.status_code != 200:
        return False, (
            f"Loop Watchdog responded from {health_url} with {response.status_code}. "
            "Start the local server before launching Codex through the wrapper."
        )
    return True, ""


def default_auto_server_persistence_path() -> Path:
    return Path.home() / ".loop_watchdog" / "state.json"


def build_server_launch_context(proxy_url: str) -> ServerLaunchContext:
    endpoints = build_proxy_endpoints(proxy_url)
    parts = urlsplit(endpoints.proxy_url)
    host = parts.hostname or "127.0.0.1"
    port = parts.port or (443 if parts.scheme == "https" else 80)

    environment = os.environ.copy()
    if AUTO_SERVER_PERSISTENCE_ENV not in environment:
        environment[AUTO_SERVER_PERSISTENCE_ENV] = str(default_auto_server_persistence_path())

    command = [
        sys.executable,
        "-m",
        "loop_watchdog",
        "serve",
        "--host",
        host,
        "--port",
        str(port),
    ]
    return ServerLaunchContext(
        host=host,
        port=port,
        command=command,
        environment=environment,
    )


def ensure_local_server_running(
    proxy_url: str,
    startup_timeout_seconds: float = 12.0,
) -> tuple[bool, ServerLaunchContext]:
    server_context = build_server_launch_context(proxy_url)
    is_available, _ = ensure_proxy_available(build_proxy_endpoints(proxy_url).health_url)
    if is_available:
        return False, server_context

    popen_kwargs: dict[str, Any] = {
        "args": server_context.command,
        "env": server_context.environment,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )

    process = subprocess.Popen(**popen_kwargs)
    deadline = time.time() + startup_timeout_seconds
    health_url = build_proxy_endpoints(proxy_url).health_url

    while time.time() < deadline:
        is_available, _ = ensure_proxy_available(health_url)
        if is_available:
            return True, server_context
        if process.poll() is not None:
            raise RuntimeError(
                "Loop Watchdog server exited during startup. "
                "Run `loop-watchdog serve` manually to inspect the server output."
            )
        time.sleep(0.25)

    if process.poll() is None:
        process.terminate()
    raise RuntimeError(
        "Loop Watchdog server did not become healthy in time. "
        "Run `loop-watchdog serve` manually if you want to inspect startup output."
    )


class LocalEventClient:
    def __init__(self, events_url: str, session_id: str) -> None:
        self.events_url = events_url
        self.session_id = session_id
        self._muted = False

    def post(
        self,
        kind: EventKind,
        summary: str,
        files: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._muted:
            return
        payload = {
            "session_id": self.session_id,
            "kind": kind.value,
            "summary": summary,
            "files": files or [],
            "metadata": metadata or {},
        }
        try:
            response = httpx.post(self.events_url, json=payload, timeout=2.0)
            response.raise_for_status()
        except httpx.HTTPError:
            # Avoid spamming the terminal if the local server goes away mid-session.
            self._muted = True


class FileChangeWatcher:
    def __init__(
        self,
        workspace: Path,
        client: LocalEventClient,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self.workspace = workspace
        self.client = client
        self.poll_interval_seconds = poll_interval_seconds
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="loop-watchdog-file-watcher",
            daemon=True,
        )
        self._snapshot: dict[str, int] = {}

    def start(self) -> None:
        self._snapshot = self._scan()
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop_event.wait(self.poll_interval_seconds):
            current = self._scan()
            changed_files = [
                path
                for path, modified_at in current.items()
                if self._snapshot.get(path) != modified_at
            ]
            self._snapshot = current
            if changed_files:
                files = sorted(changed_files)[:12]
                summary = "Detected local file edits while Codex session was active."
                metadata = {
                    "source": "loop-watchdog codex",
                    "changed_file_count": len(changed_files),
                    "workspace": str(self.workspace),
                }
                self.client.post(
                    EventKind.FILE_EDIT,
                    summary=summary,
                    files=files,
                    metadata=metadata,
                )

    def _scan(self) -> dict[str, int]:
        snapshot: dict[str, int] = {}
        for root, dir_names, file_names in os.walk(self.workspace):
            dir_names[:] = [name for name in dir_names if not self._should_skip_dir(name)]
            for file_name in file_names:
                absolute_path = Path(root) / file_name
                try:
                    relative_path = absolute_path.relative_to(self.workspace).as_posix()
                    snapshot[relative_path] = absolute_path.stat().st_mtime_ns
                except (OSError, ValueError):
                    continue
        return snapshot

    @staticmethod
    def _should_skip_dir(name: str) -> bool:
        return name in IGNORED_DIRECTORY_NAMES


@dataclass(frozen=True)
class CodexLaunchContext:
    session_id: str
    workspace: Path
    endpoints: ProxyEndpoints
    codex_executable: str
    command: list[str]


def build_launch_context(
    proxy_url: str,
    extra_args: list[str],
    session_id: str | None = None,
    codex_executable: str | None = None,
) -> CodexLaunchContext:
    workspace = resolve_workspace(extra_args)
    resolved_session_id = session_id or build_session_id(workspace)
    endpoints = build_proxy_endpoints(proxy_url)
    resolved_codex_executable = resolve_codex_executable(codex_executable)
    command = build_codex_command(
        resolved_codex_executable,
        endpoints.proxy_url,
        extra_args,
    )
    return CodexLaunchContext(
        session_id=resolved_session_id,
        workspace=workspace,
        endpoints=endpoints,
        codex_executable=resolved_codex_executable,
        command=command,
    )


def launch_codex(
    proxy_url: str,
    extra_args: list[str],
    session_id: str | None = None,
    watch_files: bool = True,
    codex_executable: str | None = None,
) -> int:
    context = build_launch_context(
        proxy_url=proxy_url,
        extra_args=extra_args,
        session_id=session_id,
        codex_executable=codex_executable,
    )
    is_available, error_message = ensure_proxy_available(context.endpoints.health_url)
    if not is_available:
        raise RuntimeError(error_message)

    env = os.environ.copy()
    env[SESSION_HEADER_ENV] = context.session_id

    watcher: FileChangeWatcher | None = None
    if watch_files:
        client = LocalEventClient(context.endpoints.events_url, context.session_id)
        watcher = FileChangeWatcher(context.workspace, client)
        watcher.start()

    try:
        completed = subprocess.run(context.command, env=env, check=False)
        return completed.returncode
    finally:
        if watcher is not None:
            watcher.stop()
