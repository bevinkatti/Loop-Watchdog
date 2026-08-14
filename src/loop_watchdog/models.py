from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)

class EventKind(StrEnum):
    # V1 Events
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

    # V2 Roadmap Events
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    FILE_CREATE = "file_create"
    FILE_DELETE = "file_delete"
    COMMAND_START = "command_start"
    COMMAND_END = "command_end"
    TEST_START = "test_start"
    BUILD_START = "build_start"
    BUILD_SUCCESS = "build_success"
    BUILD_FAILURE = "build_failure"
    LINT_PASS = "lint_pass"
    LINT_FAILURE = "lint_failure"
    GIT_DIFF = "git_diff"
    GIT_COMMIT = "git_commit"
    USER_INTERVENTION = "user_intervention"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    
    @property
    def is_v1(self) -> bool:
        return self in {
            self.AGENT_REQUEST,
            self.AGENT_RESPONSE,
            self.FILE_EDIT,
            self.PATCH_APPLY,
            self.TOOL_ERROR,
            self.TEST_FAILURE,
            self.TEST_PASS,
            self.MANUAL_RESUME,
            self.MANUAL_KILL,
            self.MANUAL_ACKNOWLEDGE,
            self.MANUAL_ARCHIVE,
            self.SESSION_NOTE,
        }

    @property
    def is_progress(self) -> bool:
        return self in {self.TEST_PASS, self.BUILD_SUCCESS, self.LINT_PASS, self.TASK_COMPLETED}

    @property
    def is_failure(self) -> bool:
        return self in {self.TOOL_ERROR, self.TEST_FAILURE, self.BUILD_FAILURE, self.LINT_FAILURE}

    @property
    def is_file_modification(self) -> bool:
        return self in {self.FILE_EDIT, self.PATCH_APPLY, self.FILE_CREATE, self.FILE_DELETE}

    
class HealthState(StrEnum):
    HEALTHY = "healthy"
    WATCH = "watch"
    WARNING = "warning"
    HIGH_RISK = "high_risk"
    CRITICAL = "critical"

    @property
    def is_v1(self) -> bool:
        return self in {
            self.AGENT_REQUEST,
            self.AGENT_RESPONSE,
            self.FILE_EDIT,
            self.PATCH_APPLY,
            self.TOOL_ERROR,
            self.TEST_FAILURE,
            self.TEST_PASS,
            self.MANUAL_RESUME,
            self.MANUAL_KILL,
            self.MANUAL_ACKNOWLEDGE,
            self.MANUAL_ARCHIVE,
            self.SESSION_NOTE,
        }

    @property
    def is_progress(self) -> bool:
        return self in {self.TEST_PASS, self.BUILD_SUCCESS, self.LINT_PASS, self.TASK_COMPLETED}

    @property
    def is_failure(self) -> bool:
        return self in {self.TOOL_ERROR, self.TEST_FAILURE, self.BUILD_FAILURE, self.LINT_FAILURE}

    @property
    def is_file_modification(self) -> bool:
        return self in {self.FILE_EDIT, self.PATCH_APPLY, self.FILE_CREATE, self.FILE_DELETE}
    
class TestFailureIdentity(BaseModel):
    framework: str = ""
    suite: str = ""
    test_id: str = ""
    command: str = ""
    exit_code: int | None = None
    failure_type: str = ""
    stacktrace_signature: str = ""

    def identity(self) -> str:
        parts = [self.suite, self.test_id, self.failure_type, self.stacktrace_signature]
        return "|".join(p for p in parts if p)
    
class GitDiffFingerprint(BaseModel):
    diff_hash: str = ""
    normalized_diff_hash: str = ""
    reversed_hash: str = ""
    files: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0

    def identity(self) -> str:
        return self.normalized_diff_hash or self.diff_hash
    
class SessionIdentity(BaseModel):
    watchdog_session_id: str = Field(min_length=1)
    repository: str = ""
    workspace: str = ""
    branch: str = ""
    agent: str = ""
    agent_session_id: str = ""
    task_id: str = ""


class WatchdogEventCreate(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    session_id: str | None = Field(
        default=None, description="Legacy session ID. Use identity instead."
    )
    identity: SessionIdentity | None = None
    kind: EventKind
    summary: str = ""
    files: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _resolve_identity(self) -> WatchdogEventCreate:
        if self.identity is None:
            if not self.session_id:
                raise ValueError("Either session_id or identity must be provided.")
            self.identity = SessionIdentity(
                watchdog_session_id=self.session_id,
                agent_session_id=self.session_id,
                agent="legacy",
            )
        # Ensure session_id always reflects the canonical watchdog ID for backwards compat
        self.session_id = self.identity.watchdog_session_id
        return self
    
    
class WatchdogEvent(WatchdogEventCreate):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)
    fingerprint: str = ""
    error_signature: str = ""
    git_diff_fingerprint: GitDiffFingerprint | None = None
    test_failure: TestFailureIdentity | None = None
    git_diff: GitDiffFingerprint | None = None

class DetectorSignal(BaseModel):
    signal_type: str
    weight: float
    detail: str = ""
    
class DetectorDecision(BaseModel):
    paused: bool = False
    score: float = 0.0
    soft_pause: bool = False
    reasons: list[str] = Field(default_factory=list)
    signals: list[DetectorSignal] = Field(default_factory=list)
    unique_strategies: int = 0
    progress_score: float = 0.0
    confidence: float = 0.0
    state: HealthState = HealthState.HEALTHY
    progress_signals: list[str] = Field(default_factory=list)
    repeated_files: list[str] = Field(default_factory=list)
    repeated_errors: list[str] = Field(default_factory=list)
    triggering_event_ids: list[str] = Field(default_factory=list)
    recommendation: str = ""


class LoopIncident(BaseModel):
    incident_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    identity: SessionIdentity | None = None
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
    identity: SessionIdentity | None = None
    paused: bool
    current_state: HealthState = HealthState.HEALTHY
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
    identity: SessionIdentity | None = None
    paused: bool
    current_state: HealthState = HealthState.HEALTHY
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
    identity: SessionIdentity | None = None
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
