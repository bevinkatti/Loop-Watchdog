from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class EventKind(str, Enum):
    AGENT_REQUEST = "agent_request"
    AGENT_RESPONSE = "agent_response"
    FILE_EDIT = "file_edit"
    PATCH_APPLY = "patch_apply"
    TOOL_ERROR = "tool_error"
    TEST_FAILURE = "test_failure"
    TEST_PASS = "test_pass"
    MANUAL_RESUME = "manual_resume"
    MANUAL_KILL = "manual_kill"
    MANUAL_ACKNOWLEDGE = "manual_acknowledge"
    MANUAL_ARCHIVE = "manual_archive"
    SESSION_NOTE = "session_note"


class WatchdogEventCreate(BaseModel):
    session_id: str = Field(min_length=1)
    kind: EventKind
    summary: str = ""
    files: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WatchdogEvent(WatchdogEventCreate):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)
    fingerprint: str = ""
    error_signature: str = ""


class DetectorDecision(BaseModel):
    paused: bool = False
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    repeated_files: list[str] = Field(default_factory=list)
    repeated_errors: list[str] = Field(default_factory=list)
    triggering_event_ids: list[str] = Field(default_factory=list)
    recommendation: str = ""


class LoopIncident(BaseModel):
    incident_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    created_at: datetime = Field(default_factory=utc_now)
    score: float
    reasons: list[str]
    repeated_files: list[str] = Field(default_factory=list)
    repeated_errors: list[str] = Field(default_factory=list)
    triggering_event_ids: list[str] = Field(default_factory=list)
    request_count: int = 0
    recommendation: str


class SessionStatus(BaseModel):
    session_id: str
    paused: bool
    event_count: int
    last_event_at: datetime | None = None
    incident: LoopIncident | None = None
    acknowledged_at: datetime | None = None
    acknowledged_note: str = ""
    archived: bool = False
    cooldown_until: datetime | None = None
    requires_changed_plan: bool = False
    required_plan_preview: str = ""


class ResumeRequest(BaseModel):
    note: str = ""
    clear_recent_events: bool = False
    cooldown_seconds: int = Field(default=0, ge=0, le=86400)
    changed_plan: str = ""


class SessionCommandRequest(BaseModel):
    note: str = ""


class SessionMetrics(BaseModel):
    request_count: int = 0
    response_count: int = 0
    error_count: int = 0
    edit_count: int = 0
    test_failure_count: int = 0
    test_pass_count: int = 0


class SessionSnapshot(BaseModel):
    session_id: str
    paused: bool
    created_at: datetime
    updated_at: datetime
    event_count: int
    last_event_at: datetime | None = None
    last_summary: str = ""
    current_stage: str = ""
    metrics: SessionMetrics = Field(default_factory=SessionMetrics)
    incident: LoopIncident | None = None
    recent_events: list[WatchdogEvent] = Field(default_factory=list)
    acknowledged_at: datetime | None = None
    acknowledged_note: str = ""
    archived: bool = False
    cooldown_until: datetime | None = None
    requires_changed_plan: bool = False
    required_plan_preview: str = ""


class DashboardSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    total_sessions: int = 0
    paused_sessions: int = 0
    total_events: int = 0
    active_incidents: int = 0
    acknowledged_sessions: int = 0
    archived_sessions: int = 0
    sessions: list[SessionSnapshot] = Field(default_factory=list)


class IncidentEnvelope(BaseModel):
    incident: LoopIncident
    recent_events: list[WatchdogEvent]


class PersistedSessionState(BaseModel):
    session_id: str
    created_at: datetime
    updated_at: datetime
    events: list[WatchdogEvent] = Field(default_factory=list)
    incident: LoopIncident | None = None
    acknowledged_at: datetime | None = None
    acknowledged_note: str = ""
    archived: bool = False
    cooldown_until: datetime | None = None
    required_plan_digest: str = ""
    required_plan_preview: str = ""


class PersistedStore(BaseModel):
    version: int = 1
    sessions: list[PersistedSessionState] = Field(default_factory=list)


class GuidedTrialResponse(BaseModel):
    session_id: str
    status: SessionStatus
    message: str
