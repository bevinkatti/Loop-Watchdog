"""Loop Watchdog Event Protocol (LWEP) v1.

This module defines the stable, versioned wire format that external agent
adapters use to emit telemetry into Loop Watchdog. Adapters should target
this protocol rather than the internal ``WatchdogEventCreate`` model so the
internal representation can evolve independently.

Two payload shapes are accepted by the ingestion endpoint:

1. The LWEP v1 envelope (recommended for new adapters).
2. The legacy flat ``WatchdogEventCreate`` shape (backwards compatibility).

See ``docs/EVENT_PROTOCOL.md`` for the full specification.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from .models import EventKind, SessionIdentity, WatchdogEventCreate

PROTOCOL_VERSION = "1"
SUPPORTED_PROTOCOL_VERSIONS = {"1"}

# Reserved metadata keys used to preserve protocol-level fields.
_LWEP_EVENT_ID_KEY = "_lwep_event_id"
_LWEP_TIMESTAMP_KEY = "_lwep_timestamp"


class ProtocolEventPayload(BaseModel):
    """The event body within an LWEP envelope."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str
    timestamp: str | None = None
    summary: str = ""
    files: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LoopWatchdogEnvelope(BaseModel):
    """LWEP v1 envelope: protocol version + session identity + event payload."""

    version: str = PROTOCOL_VERSION
    session: SessionIdentity
    event: ProtocolEventPayload

    @model_validator(mode="after")
    def _validate_version(self) -> "LoopWatchdogEnvelope":
        if self.version not in SUPPORTED_PROTOCOL_VERSIONS:
            raise ValueError(
                f"Unsupported LWEP version '{self.version}'. "
                f"Supported versions: {sorted(SUPPORTED_PROTOCOL_VERSIONS)}"
            )
        return self


def envelope_to_event(envelope: LoopWatchdogEnvelope) -> WatchdogEventCreate:
    """Convert an LWEP envelope into the internal event model."""
    metadata = dict(envelope.event.metadata)
    metadata[_LWEP_EVENT_ID_KEY] = envelope.event.id
    if envelope.event.timestamp:
        metadata[_LWEP_TIMESTAMP_KEY] = envelope.event.timestamp
    return WatchdogEventCreate(
        schema_version=1,
        identity=envelope.session,
        kind=EventKind(envelope.event.type),
        summary=envelope.event.summary,
        files=list(envelope.event.files),
        metadata=metadata,
    )


def event_to_envelope(event: WatchdogEventCreate) -> LoopWatchdogEnvelope:
    """Convert an internal event back into an LWEP envelope (for replay/export)."""
    metadata = dict(event.metadata)
    lwep_event_id = metadata.pop(_LWEP_EVENT_ID_KEY, None)
    lwep_timestamp = metadata.pop(_LWEP_TIMESTAMP_KEY, None)
    session = event.identity or SessionIdentity(watchdog_session_id=event.session_id or "")
    return LoopWatchdogEnvelope(
        version=PROTOCOL_VERSION,
        session=session,
        event=ProtocolEventPayload(
            id=lwep_event_id or str(uuid4()),
            type=event.kind.value,
            timestamp=lwep_timestamp,
            summary=event.summary,
            files=list(event.files),
            metadata=metadata,
        ),
    )


def parse_event_payload(raw: Any) -> WatchdogEventCreate:
    """Parse an incoming event payload in either LWEP envelope or legacy format.

    Backwards compatibility: legacy adapters that POST the flat
    ``WatchdogEventCreate`` shape continue to work. New adapters should POST
    the LWEP envelope.
    """
    if not isinstance(raw, dict):
        raise ValueError("Event payload must be a JSON object.")

    # LWEP envelope: has both "session" and "event" keys.
    if "session" in raw and "event" in raw:
        envelope = LoopWatchdogEnvelope.model_validate(raw)
        return envelope_to_event(envelope)

    # Legacy flat format.
    return WatchdogEventCreate.model_validate(raw)