from __future__ import annotations

import shlex

import typer
import uvicorn

from .api import create_app
from .config import WatchdogSettings, get_settings
from .launcher import (
    build_launch_context,
    build_server_launch_context,
    ensure_local_server_running,
    launch_codex,
)

app = typer.Typer(no_args_is_help=True, add_completion=False)
start_app = typer.Typer(no_args_is_help=True, add_completion=False)
app.add_typer(start_app, name="start")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address."),
    port: int = typer.Option(8787, help="Bind port."),
    reload: bool = typer.Option(False, help="Enable autoreload for local development."),
) -> None:
    settings = get_settings()
    uvicorn.run(
        create_app(settings),
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@app.command()
def print_config() -> None:
    settings: WatchdogSettings = get_settings()
    typer.echo(settings.model_dump_json(indent=2))


def _run_codex_command(
    ctx: typer.Context,
    session_id: str | None,
    proxy_url: str,
    codex_executable: str | None,
    watch_files: bool,
    dry_run: bool,
    auto_start_server: bool,
) -> None:
    extra_args = list(ctx.args)
    launch_context = build_launch_context(
        proxy_url=proxy_url,
        extra_args=extra_args,
        session_id=session_id,
        codex_executable=codex_executable,
    )

    typer.echo(f"Session: {launch_context.session_id}")
    typer.echo(f"Workspace: {launch_context.workspace}")
    typer.echo(f"Proxy: {launch_context.endpoints.proxy_url}")
    typer.echo(f"Codex: {launch_context.codex_executable}")

    if dry_run:
        if auto_start_server:
            server_context = build_server_launch_context(proxy_url)
            typer.echo(f"Server: would start on http://{server_context.host}:{server_context.port}/")
        typer.echo(shlex.join(launch_context.command))
        return

    try:
        if auto_start_server:
            server_started, server_context = ensure_local_server_running(proxy_url)
            state_label = "started" if server_started else "running"
            typer.echo(f"Server: {state_label} on http://{server_context.host}:{server_context.port}/")
        raise typer.Exit(
            code=launch_codex(
                proxy_url=proxy_url,
                extra_args=extra_args,
                session_id=session_id,
                watch_files=watch_files,
                codex_executable=codex_executable,
            )
        )
    except (RuntimeError, FileNotFoundError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def codex(
    ctx: typer.Context,
    session_id: str | None = typer.Option(
        None,
        "--session-id",
        help="Override the stable loop-watchdog session id.",
    ),
    proxy_url: str = typer.Option(
        "http://127.0.0.1:8787/v1",
        "--proxy-url",
        help="Loop Watchdog proxy base URL.",
    ),
    codex_executable: str | None = typer.Option(
        None,
        "--codex-executable",
        help="Full path to codex.exe when PATH lookup is unreliable.",
    ),
    watch_files: bool = typer.Option(
        True,
        "--watch-files/--no-watch-files",
        help="Emit lightweight file_edit events while Codex is running.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the resolved Codex command without launching it.",
    ),
) -> None:
    _run_codex_command(
        ctx=ctx,
        session_id=session_id,
        proxy_url=proxy_url,
        codex_executable=codex_executable,
        watch_files=watch_files,
        dry_run=dry_run,
        auto_start_server=False,
    )


@start_app.command(
    "codex",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def start_codex(
    ctx: typer.Context,
    session_id: str | None = typer.Option(
        None,
        "--session-id",
        help="Override the stable loop-watchdog session id.",
    ),
    proxy_url: str = typer.Option(
        "http://127.0.0.1:8787/v1",
        "--proxy-url",
        help="Loop Watchdog proxy base URL.",
    ),
    codex_executable: str | None = typer.Option(
        None,
        "--codex-executable",
        help="Full path to codex.exe when PATH lookup is unreliable.",
    ),
    watch_files: bool = typer.Option(
        True,
        "--watch-files/--no-watch-files",
        help="Emit lightweight file_edit events while Codex is running.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the resolved Codex command without launching it.",
    ),
) -> None:
    _run_codex_command(
        ctx=ctx,
        session_id=session_id,
        proxy_url=proxy_url,
        codex_executable=codex_executable,
        watch_files=watch_files,
        dry_run=dry_run,
        auto_start_server=True,
    )
