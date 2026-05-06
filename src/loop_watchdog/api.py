from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .alerting import AlertDispatcher
from .config import WatchdogSettings, get_settings
from .loop_detector import LoopDetector, normalize_text
from .models import EventKind, ResumeRequest, SessionCommandRequest, WatchdogEventCreate
from .provider import UpstreamProxy
from .state import WatchdogStore

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
TEMPLATES_DIR = PACKAGE_DIR / "templates"


def _coerce_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("input_text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts)
    if isinstance(value, dict):
        nested = value.get("text") or value.get("content")
        return nested if isinstance(nested, str) else ""
    return ""


def _extract_latest_user_text(payload: dict[str, Any]) -> str:
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "user":
                return _coerce_content(message.get("content"))
    input_value = payload.get("input")
    if isinstance(input_value, str):
        return input_value
    if isinstance(input_value, list):
        parts: list[str] = []
        for item in input_value:
            if isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            text = part.get("text") or part.get("input_text")
                            if isinstance(text, str):
                                parts.append(text)
        return " ".join(parts)
    return ""


def _extract_response_text(payload: Any) -> str:
    if isinstance(payload, dict):
        if "choices" in payload and isinstance(payload["choices"], list):
            choice = payload["choices"][0] if payload["choices"] else {}
            if isinstance(choice, dict):
                message = choice.get("message", {})
                if isinstance(message, dict):
                    return _coerce_content(message.get("content"))
        output = payload.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if isinstance(item, dict):
                    content = item.get("content")
                    if isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict):
                                text = part.get("text") or part.get("output_text")
                                if isinstance(text, str):
                                    parts.append(text)
            return " ".join(parts)
    return ""


def _clamp(value: str, max_chars: int) -> str:
    cleaned = " ".join(value.split())
    return cleaned[:max_chars]


def _extract_session_id(
    payload: dict[str, Any],
    x_loop_session: str | None,
) -> str:
    if x_loop_session:
        return x_loop_session
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        for key in ("session_id", "loop_watchdog_session", "loop_session"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value
    user = payload.get("user")
    if isinstance(user, str) and user.strip():
        return user
    latest_text = _extract_latest_user_text(payload)
    seed = latest_text or json.dumps(payload, sort_keys=True)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"ephemeral:{digest}"


def _request_event(payload: dict[str, Any], session_id: str, max_chars: int) -> WatchdogEventCreate:
    summary = _clamp(_extract_latest_user_text(payload), max_chars)
    return WatchdogEventCreate(
        session_id=session_id,
        kind=EventKind.AGENT_REQUEST,
        summary=summary or "Agent request",
        metadata={"stream": bool(payload.get("stream"))},
    )


def _response_event(
    payload: Any,
    session_id: str,
    max_chars: int,
) -> WatchdogEventCreate:
    summary = _clamp(_extract_response_text(payload), max_chars)
    return WatchdogEventCreate(
        session_id=session_id,
        kind=EventKind.AGENT_RESPONSE,
        summary=summary or "Agent response",
    )


def _error_event(session_id: str, status_code: int, payload: Any) -> WatchdogEventCreate:
    if isinstance(payload, (dict, list)):
        text = json.dumps(payload, sort_keys=True)
    else:
        text = str(payload)
    summary = _clamp(text, 280)
    return WatchdogEventCreate(
        session_id=session_id,
        kind=EventKind.TOOL_ERROR,
        summary=summary or f"Upstream error {status_code}",
        metadata={"status_code": status_code, "error": normalize_text(text)},
    )


def create_app(
    settings: WatchdogSettings | None = None,
    upstream: UpstreamProxy | None = None,
    dispatcher: AlertDispatcher | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    detector = LoopDetector(resolved_settings)
    store = WatchdogStore(resolved_settings, detector)
    proxy = upstream or UpstreamProxy(resolved_settings)
    alert_dispatcher = dispatcher or AlertDispatcher(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield

    app = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.store = store
    app.state.proxy = proxy
    app.state.dispatcher = alert_dispatcher
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    async def landing_home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="landing.html",
            context={
                "app_name": resolved_settings.app_name,
                "refresh_ms": 3000,
            },
        )

    @app.get("/dashboard", include_in_schema=False, response_class=HTMLResponse)
    async def dashboard_home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "app_name": resolved_settings.app_name,
                "refresh_ms": 3000,
            },
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/watchdog/dashboard")
    async def dashboard_snapshot(
        include_archived: bool = Query(default=False),
    ) -> JSONResponse:
        snapshot = store.dashboard_snapshot(include_archived=include_archived)
        return JSONResponse(status_code=200, content=snapshot.model_dump(mode="json"))

    @app.get("/v1/watchdog/sessions")
    async def list_sessions(include_archived: bool = Query(default=False)) -> JSONResponse:
        sessions = store.list_sessions(include_archived=include_archived)
        return JSONResponse(
            status_code=200,
            content={"sessions": [session.model_dump(mode="json") for session in sessions]},
        )

    @app.get("/v1/watchdog/status/{session_id}")
    async def session_status(session_id: str) -> JSONResponse:
        status = store.get_status(session_id)
        return JSONResponse(status_code=200, content=status.model_dump(mode="json"))

    @app.get("/v1/watchdog/sessions/{session_id}/events")
    async def session_events(session_id: str) -> JSONResponse:
        events = store.get_recent_events(session_id)
        return JSONResponse(
            status_code=200,
            content={"session_id": session_id, "events": [event.model_dump(mode="json") for event in events]},
        )

    @app.post("/v1/watchdog/events")
    async def ingest_event(payload: WatchdogEventCreate) -> JSONResponse:
        _, incident = store.record_event(payload)
        if incident is not None:
            await alert_dispatcher.dispatch(incident, store.get_recent_events(payload.session_id))
        status = store.get_status(payload.session_id)
        return JSONResponse(status_code=202, content=status.model_dump(mode="json"))

    @app.post("/v1/watchdog/demo/guided-trial")
    async def guided_trial() -> JSONResponse:
        result = store.create_guided_trial()
        return JSONResponse(status_code=201, content=result.model_dump(mode="json"))

    @app.post("/v1/watchdog/history/clear")
    async def clear_history(_: SessionCommandRequest) -> JSONResponse:
        snapshot = store.clear_history()
        return JSONResponse(status_code=200, content=snapshot.model_dump(mode="json"))

    @app.post("/v1/watchdog/sessions/{session_id}/acknowledge")
    async def acknowledge_session(session_id: str, payload: SessionCommandRequest) -> JSONResponse:
        status = store.acknowledge_session(session_id, payload)
        return JSONResponse(status_code=200, content=status.model_dump(mode="json"))

    @app.post("/v1/watchdog/sessions/{session_id}/resume")
    async def resume_session(session_id: str, payload: ResumeRequest) -> JSONResponse:
        status = store.resume_session(session_id, payload)
        return JSONResponse(status_code=200, content=status.model_dump(mode="json"))

    @app.post("/v1/watchdog/sessions/{session_id}/kill")
    async def kill_session(session_id: str, payload: SessionCommandRequest) -> JSONResponse:
        status = store.kill_session(session_id, payload)
        return JSONResponse(status_code=200, content=status.model_dump(mode="json"))

    @app.post("/v1/watchdog/sessions/{session_id}/archive")
    async def archive_session(session_id: str, payload: SessionCommandRequest) -> JSONResponse:
        status = store.archive_session(session_id, payload)
        return JSONResponse(status_code=200, content=status.model_dump(mode="json"))

    @app.post("/v1/chat/completions")
    async def chat_completions(
        request: Request,
        x_loop_session: str | None = Header(default=None),
    ):
        return await _handle_proxy_request(
            request=request,
            path="/v1/chat/completions",
            x_loop_session=x_loop_session,
            settings=resolved_settings,
            store=store,
            proxy=proxy,
            dispatcher=alert_dispatcher,
        )

    @app.post("/v1/responses")
    async def responses(
        request: Request,
        x_loop_session: str | None = Header(default=None),
    ):
        return await _handle_proxy_request(
            request=request,
            path="/v1/responses",
            x_loop_session=x_loop_session,
            settings=resolved_settings,
            store=store,
            proxy=proxy,
            dispatcher=alert_dispatcher,
        )

    return app


async def _handle_proxy_request(
    request: Request,
    path: str,
    x_loop_session: str | None,
    settings: WatchdogSettings,
    store: WatchdogStore,
    proxy: UpstreamProxy,
    dispatcher: AlertDispatcher,
):
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON request body must be an object.")

    session_id = _extract_session_id(payload, x_loop_session)
    cooldown_until = store.cooldown_until(session_id)
    if cooldown_until is not None and cooldown_until > datetime.now(UTC):
        return JSONResponse(
            status_code=423,
            content={
                "error": {
                    "message": "Loop Watchdog is holding this session in cooldown before another model call is allowed.",
                    "type": "loop_watchdog_cooldown",
                    "cooldown_until": cooldown_until.isoformat(),
                }
            },
        )

    plan_hint = ""
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("loop_watchdog_plan") or metadata.get("changed_plan")
        if isinstance(value, str):
            plan_hint = value
    x_loop_plan = request.headers.get("x-loop-plan")
    if not plan_hint and isinstance(x_loop_plan, str):
        plan_hint = x_loop_plan
    if store.changed_plan_required(session_id) and not store.validate_and_consume_plan(session_id, plan_hint):
        return JSONResponse(
            status_code=428,
            content={
                "error": {
                    "message": "Loop Watchdog requires a changed plan token before this session can resume.",
                    "type": "loop_watchdog_plan_required",
                    "required_plan_preview": store.required_plan_preview(session_id),
                }
            },
        )

    if store.is_paused(session_id):
        incident = store.current_incident(session_id)
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "message": "Loop Watchdog has paused this session before another model call was sent.",
                    "type": "loop_watchdog_paused",
                    "incident": incident.model_dump(mode="json") if incident else None,
                }
            },
        )

    _, incident = store.record_event(_request_event(payload, session_id, settings.max_summary_chars))
    if incident is not None:
        await dispatcher.dispatch(incident, store.get_recent_events(session_id))
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "message": "Loop Watchdog paused the session after detecting a likely fix-break loop.",
                    "type": "loop_watchdog_paused",
                    "incident": incident.model_dump(mode="json"),
                }
            },
        )

    headers = {key.lower(): value for key, value in request.headers.items()}
    is_streaming = bool(payload.get("stream"))

    if is_streaming:
        status_code, response_headers, iterator = await proxy.forward_stream(path, payload, headers)
        return StreamingResponse(iterator, status_code=status_code, headers=response_headers)

    status_code, response_headers, response_payload = await proxy.forward_json(path, payload, headers)
    if status_code >= 400:
        _, incident = store.record_event(_error_event(session_id, status_code, response_payload))
        if incident is not None:
            await dispatcher.dispatch(incident, store.get_recent_events(session_id))
    else:
        _, incident = store.record_event(
            _response_event(response_payload, session_id, settings.max_response_chars)
        )
        if incident is not None:
            await dispatcher.dispatch(incident, store.get_recent_events(session_id))
    return JSONResponse(status_code=status_code, content=response_payload, headers=response_headers)
