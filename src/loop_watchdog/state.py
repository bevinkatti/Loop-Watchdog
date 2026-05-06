from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
from threading import RLock

from .config import WatchdogSettings
from .loop_detector import normalize_text
from .loop_detector import LoopDetector
from .models import (
    DashboardSnapshot,
    DetectorDecision,
    EventKind,
    GuidedTrialResponse,
    LoopIncident,
    PersistedSessionState,
    PersistedStore,
    ResumeRequest,
    SessionCommandRequest,
    SessionMetrics,
    SessionSnapshot,
    SessionStatus,
    WatchdogEvent,
    WatchdogEventCreate,
)


@dataclass
class SessionState:
    session_id: str
    created_at: datetime
    updated_at: datetime
    events: deque[WatchdogEvent] = field(default_factory=deque)
    incident: LoopIncident | None = None
    acknowledged_at: datetime | None = None
    acknowledged_note: str = ""
    archived: bool = False
    cooldown_until: datetime | None = None
    required_plan_digest: str = ""
    required_plan_preview: str = ""


class WatchdogStore:
    def __init__(self, settings: WatchdogSettings, detector: LoopDetector) -> None:
        self.settings = settings
        self.detector = detector
        self._sessions: dict[str, SessionState] = {}
        self._lock = RLock()
        self._persistence_path = Path(settings.persistence_path)
        if self.settings.persistence_enabled:
            self._load_state()

    def record_event(self, payload: WatchdogEventCreate) -> tuple[WatchdogEvent, LoopIncident | None]:
        with self._lock:
            self._cleanup_expired_locked()
            now = datetime.now(UTC)
            session = self._sessions.setdefault(
                payload.session_id,
                SessionState(session_id=payload.session_id, created_at=now, updated_at=now),
            )
            event = WatchdogEvent(
                **payload.model_dump(),
                fingerprint=self.detector.fingerprint(payload.kind, payload.summary, payload.files),
            )
            if payload.kind in {EventKind.TOOL_ERROR, EventKind.TEST_FAILURE}:
                event.error_signature = self.detector.error_signature(event)

            self._append_event_locked(session, event)

            if session.incident is not None:
                self._persist_locked()
                return event, None

            decision = self.detector.evaluate(list(session.events))
            if not decision.paused:
                self._persist_locked()
                return event, None

            incident = self._build_incident_locked(payload.session_id, session, decision)
            session.incident = incident
            self._persist_locked()
            return event, incident

    def get_status(self, session_id: str) -> SessionStatus:
        with self._lock:
            self._cleanup_expired_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return SessionStatus(session_id=session_id, paused=False, event_count=0)
            snapshot = self._snapshot_locked(session)
            return SessionStatus(
                session_id=session_id,
                paused=snapshot.paused,
                event_count=snapshot.event_count,
                last_event_at=snapshot.last_event_at,
                incident=session.incident,
                acknowledged_at=snapshot.acknowledged_at,
                acknowledged_note=snapshot.acknowledged_note,
                archived=snapshot.archived,
                cooldown_until=snapshot.cooldown_until,
                requires_changed_plan=snapshot.requires_changed_plan,
                required_plan_preview=snapshot.required_plan_preview,
            )

    def get_recent_events(self, session_id: str) -> list[WatchdogEvent]:
        with self._lock:
            self._cleanup_expired_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return []
            return list(session.events)[-self.settings.recent_window :]

    def list_sessions(self, include_archived: bool = False) -> list[SessionSnapshot]:
        with self._lock:
            self._cleanup_expired_locked()
            sessions = [
                self._snapshot_locked(session)
                for session in self._sessions.values()
                if include_archived or not session.archived
            ]
            sessions.sort(
                key=lambda snapshot: (
                    snapshot.paused,
                    snapshot.archived is False,
                    snapshot.last_event_at or snapshot.updated_at,
                ),
                reverse=True,
            )
            return sessions

    def dashboard_snapshot(self, include_archived: bool = False) -> DashboardSnapshot:
        with self._lock:
            self._cleanup_expired_locked()
            sessions = [
                self._snapshot_locked(session)
                for session in self._sessions.values()
                if include_archived or not session.archived
            ]
            sessions.sort(
                key=lambda snapshot: (
                    snapshot.paused,
                    snapshot.archived is False,
                    snapshot.last_event_at or snapshot.updated_at,
                ),
                reverse=True,
            )
            return DashboardSnapshot(
                total_sessions=len(sessions),
                paused_sessions=sum(1 for session in sessions if session.paused),
                active_incidents=sum(1 for session in sessions if session.incident is not None),
                total_events=sum(session.event_count for session in sessions),
                acknowledged_sessions=sum(1 for session in sessions if session.acknowledged_at is not None),
                archived_sessions=sum(1 for session in sessions if session.archived),
                sessions=sessions,
            )

    def resume_session(self, session_id: str, payload: ResumeRequest) -> SessionStatus:
        with self._lock:
            self._cleanup_expired_locked()
            now = datetime.now(UTC)
            session = self._sessions.setdefault(
                session_id,
                SessionState(session_id=session_id, created_at=now, updated_at=now),
            )
            if payload.clear_recent_events:
                session.events.clear()
            session.incident = None
            session.archived = False
            session.acknowledged_at = None
            session.acknowledged_note = ""
            session.cooldown_until = (
                now + timedelta(seconds=payload.cooldown_seconds)
                if payload.cooldown_seconds > 0
                else None
            )
            if payload.changed_plan.strip():
                session.required_plan_digest = self._plan_digest(payload.changed_plan)
                session.required_plan_preview = payload.changed_plan.strip()[:180]
            else:
                session.required_plan_digest = ""
                session.required_plan_preview = ""
            event = WatchdogEvent(
                session_id=session_id,
                kind=EventKind.MANUAL_RESUME,
                summary=payload.note or "Session resumed manually.",
                metadata={
                    "clear_recent_events": payload.clear_recent_events,
                    "cooldown_seconds": payload.cooldown_seconds,
                    "requires_changed_plan": bool(payload.changed_plan.strip()),
                },
                fingerprint=self.detector.fingerprint(EventKind.MANUAL_RESUME, payload.note, []),
            )
            self._append_event_locked(session, event)
            self._persist_locked()
            return self.get_status(session_id)

    def acknowledge_session(self, session_id: str, payload: SessionCommandRequest) -> SessionStatus:
        with self._lock:
            self._cleanup_expired_locked()
            now = datetime.now(UTC)
            session = self._sessions.setdefault(
                session_id,
                SessionState(session_id=session_id, created_at=now, updated_at=now),
            )
            session.acknowledged_at = now
            session.acknowledged_note = payload.note or "Incident acknowledged by an operator."
            event = WatchdogEvent(
                session_id=session_id,
                kind=EventKind.MANUAL_ACKNOWLEDGE,
                summary=session.acknowledged_note,
                fingerprint=self.detector.fingerprint(
                    EventKind.MANUAL_ACKNOWLEDGE,
                    session.acknowledged_note,
                    [],
                ),
            )
            self._append_event_locked(session, event)
            self._persist_locked()
            return self.get_status(session_id)

    def archive_session(self, session_id: str, payload: SessionCommandRequest) -> SessionStatus:
        with self._lock:
            self._cleanup_expired_locked()
            now = datetime.now(UTC)
            session = self._sessions.setdefault(
                session_id,
                SessionState(session_id=session_id, created_at=now, updated_at=now),
            )
            session.archived = True
            event = WatchdogEvent(
                session_id=session_id,
                kind=EventKind.MANUAL_ARCHIVE,
                summary=payload.note or "Session archived by an operator.",
                fingerprint=self.detector.fingerprint(
                    EventKind.MANUAL_ARCHIVE,
                    payload.note,
                    [],
                ),
            )
            self._append_event_locked(session, event)
            self._persist_locked()
            return self.get_status(session_id)

    def kill_session(self, session_id: str, payload: SessionCommandRequest) -> SessionStatus:
        with self._lock:
            self._cleanup_expired_locked()
            now = datetime.now(UTC)
            session = self._sessions.setdefault(
                session_id,
                SessionState(session_id=session_id, created_at=now, updated_at=now),
            )
            if session.incident is None:
                session.incident = LoopIncident(
                    session_id=session_id,
                    score=999.0,
                    reasons=[payload.note or "Session was terminated manually."],
                    request_count=sum(
                        1 for event in session.events if event.kind == EventKind.AGENT_REQUEST
                    ),
                    recommendation="Do not resume until a human rewrites the plan.",
                )
            event = WatchdogEvent(
                session_id=session_id,
                kind=EventKind.MANUAL_KILL,
                summary=payload.note or "Session terminated manually.",
                fingerprint=self.detector.fingerprint(EventKind.MANUAL_KILL, payload.note, []),
            )
            self._append_event_locked(session, event)
            self._persist_locked()
            return self.get_status(session_id)

    def is_paused(self, session_id: str) -> bool:
        return self.get_status(session_id).paused

    def current_incident(self, session_id: str) -> LoopIncident | None:
        return self.get_status(session_id).incident

    def cooldown_until(self, session_id: str) -> datetime | None:
        with self._lock:
            session = self._sessions.get(session_id)
            return session.cooldown_until if session else None

    def changed_plan_required(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            return bool(session and session.required_plan_digest)

    def required_plan_preview(self, session_id: str) -> str:
        with self._lock:
            session = self._sessions.get(session_id)
            return session.required_plan_preview if session else ""

    def validate_and_consume_plan(self, session_id: str, plan_value: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or not session.required_plan_digest:
                return True
            if not plan_value.strip():
                return False
            provided = self._plan_digest(plan_value)
            if provided != session.required_plan_digest:
                return False
            session.required_plan_digest = ""
            session.required_plan_preview = ""
            self._persist_locked()
            return True

    def create_guided_trial(self) -> GuidedTrialResponse:
        with self._lock:
            now = datetime.now(UTC)
            session_id = f"trial:{now.strftime('%Y%m%d%H%M%S')}"
            session = SessionState(
                session_id=session_id,
                created_at=now - timedelta(minutes=8),
                updated_at=now - timedelta(minutes=1),
            )
            trial_events = [
                (
                    EventKind.AGENT_REQUEST,
                    "Fix the receipt rounding bug in checkout totals.",
                    7,
                    [],
                    {},
                ),
                (
                    EventKind.FILE_EDIT,
                    "Adjusted receipt rounding at the formatter layer.",
                    6,
                    ["src/payments/receipts.py", "tests/test_receipts.py"],
                    {},
                ),
                (
                    EventKind.TEST_FAILURE,
                    "test_receipt_total still fails with rounding mismatch.",
                    5,
                    ["src/payments/receipts.py", "tests/test_receipts.py"],
                    {"error": "AssertionError: expected 124.20 got 124.19"},
                ),
                (
                    EventKind.FILE_EDIT,
                    "Retried the receipt patch with another rounding guard.",
                    4,
                    ["src/payments/receipts.py", "tests/test_receipts.py"],
                    {},
                ),
                (
                    EventKind.TEST_FAILURE,
                    "test_receipt_total still fails with rounding mismatch.",
                    3,
                    ["src/payments/receipts.py", "tests/test_receipts.py"],
                    {"error": "AssertionError: expected 124.20 got 124.19"},
                ),
            ]
            for kind, summary, minutes_ago, files, metadata in trial_events:
                event = WatchdogEvent(
                    session_id=session_id,
                    kind=kind,
                    summary=summary,
                    files=files,
                    metadata=metadata,
                    created_at=now - timedelta(minutes=minutes_ago),
                    fingerprint=self.detector.fingerprint(kind, summary, files),
                )
                if kind in {EventKind.TOOL_ERROR, EventKind.TEST_FAILURE}:
                    event.error_signature = self.detector.error_signature(event)
                self._append_event_locked(session, event)

            decision = self.detector.evaluate(list(session.events))
            if decision.paused:
                session.incident = self._build_incident_locked(session_id, session, decision)
                session.acknowledged_note = "Guided trial seeded for first-run evaluation."
            self._sessions[session_id] = session
            self._persist_locked()
            status = self.get_status(session_id)
            return GuidedTrialResponse(
                session_id=session_id,
                status=status,
                message="Guided trial session created. Open the dashboard to inspect the incident and operator controls.",
            )

    def clear_history(self) -> DashboardSnapshot:
        with self._lock:
            self._sessions = {}
            self._persist_locked()
            return DashboardSnapshot()

    def _build_incident_locked(
        self,
        session_id: str,
        session: SessionState,
        decision: DetectorDecision,
    ) -> LoopIncident:
        request_count = sum(1 for event in session.events if event.kind == EventKind.AGENT_REQUEST)
        return LoopIncident(
            session_id=session_id,
            score=decision.score,
            reasons=decision.reasons,
            repeated_files=decision.repeated_files,
            repeated_errors=decision.repeated_errors,
            triggering_event_ids=decision.triggering_event_ids,
            request_count=request_count,
            recommendation=decision.recommendation,
        )

    def _snapshot_locked(self, session: SessionState) -> SessionSnapshot:
        events = list(session.events)
        recent_events = events[-self.settings.recent_window :]
        counts = Counter(event.kind for event in events)
        last_event = events[-1] if events else None
        current_stage = last_event.kind.value.replace("_", " ") if last_event else "idle"
        last_summary = ""
        for event in reversed(events):
            if event.summary:
                last_summary = event.summary
                break
        return SessionSnapshot(
            session_id=session.session_id,
            paused=session.incident is not None,
            created_at=session.created_at,
            updated_at=session.updated_at,
            event_count=len(events),
            last_event_at=last_event.created_at if last_event else None,
            last_summary=last_summary,
            current_stage=current_stage,
            metrics=SessionMetrics(
                request_count=counts[EventKind.AGENT_REQUEST],
                response_count=counts[EventKind.AGENT_RESPONSE],
                error_count=counts[EventKind.TOOL_ERROR],
                edit_count=counts[EventKind.FILE_EDIT] + counts[EventKind.PATCH_APPLY],
                test_failure_count=counts[EventKind.TEST_FAILURE],
                test_pass_count=counts[EventKind.TEST_PASS],
            ),
            incident=session.incident,
            recent_events=recent_events,
            acknowledged_at=session.acknowledged_at,
            acknowledged_note=session.acknowledged_note,
            archived=session.archived,
            cooldown_until=session.cooldown_until,
            requires_changed_plan=bool(session.required_plan_digest),
            required_plan_preview=session.required_plan_preview,
        )

    def _append_event_locked(self, session: SessionState, event: WatchdogEvent) -> None:
        session.events.append(event)
        session.updated_at = event.created_at
        while len(session.events) > self.settings.max_events_per_session:
            session.events.popleft()

    def _plan_digest(self, value: str) -> str:
        normalized = normalize_text(value)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _load_state(self) -> None:
        with self._lock:
            self._load_state_locked()

    def _load_state_locked(self) -> None:
        if not self._persistence_path.exists():
            return
        try:
            payload = PersistedStore.model_validate_json(self._persistence_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self._sessions = {}
        for item in payload.sessions:
            state = SessionState(
                session_id=item.session_id,
                created_at=item.created_at,
                updated_at=item.updated_at,
                events=deque(item.events),
                incident=item.incident,
                acknowledged_at=item.acknowledged_at,
                acknowledged_note=item.acknowledged_note,
                archived=item.archived,
                cooldown_until=item.cooldown_until,
                required_plan_digest=item.required_plan_digest,
                required_plan_preview=item.required_plan_preview,
            )
            self._sessions[state.session_id] = state
        if self._prune_seed_demo_sessions_locked():
            self._persist_locked()

    def _persist_locked(self) -> None:
        if not self.settings.persistence_enabled:
            return
        store = PersistedStore(
            sessions=[
                PersistedSessionState(
                    session_id=session.session_id,
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                    events=list(session.events),
                    incident=session.incident,
                    acknowledged_at=session.acknowledged_at,
                    acknowledged_note=session.acknowledged_note,
                    archived=session.archived,
                    cooldown_until=session.cooldown_until,
                    required_plan_digest=session.required_plan_digest,
                    required_plan_preview=session.required_plan_preview,
                )
                for session in self._sessions.values()
            ]
        )
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
        target = self._persistence_path
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(store.model_dump_json(indent=2), encoding="utf-8")
        temp.replace(target)

    def _prune_seed_demo_sessions_locked(self) -> bool:
        seed_demo_session_ids = [
            session_id for session_id in self._sessions if session_id.startswith("demo:")
        ]
        if not seed_demo_session_ids:
            return False
        for session_id in seed_demo_session_ids:
            del self._sessions[session_id]
        return True

    def _cleanup_expired_locked(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(seconds=self.settings.session_ttl_seconds)
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if session.updated_at < cutoff
        ]
        for session_id in expired:
            del self._sessions[session_id]
        if expired:
            self._persist_locked()
