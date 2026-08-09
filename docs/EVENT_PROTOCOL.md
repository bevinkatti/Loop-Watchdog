# Loop Watchdog Event Protocol (LWEP) v1

The Loop Watchdog Event Protocol (LWEP) is the stable, versioned wire format
that external agent adapters use to emit telemetry into Loop Watchdog.

Adapters should target this protocol rather than the internal event model so
the internal representation can evolve without breaking integrations.

## Envelope

Every LWEP v1 message is a JSON object with three top-level fields:

| Field     | Type            | Required | Description                        |
| --------- | --------------- | -------- | ---------------------------------- |
| `version` | string          | yes      | Protocol version. Must be `"1"`.   |
| `session` | SessionIdentity | yes      | Structured session identity.       |
| `event`   | EventPayload    | yes      | The event body.                    |

### Example

```json
{
  "version": "1",
  "session": {
    "watchdog_session_id": "acme-api:claude:main:9f2c",
    "agent": "claude-code",
    "agent_session_id": "sess_abc123",
    "repository": "acme/api",
    "workspace": "backend",
    "branch": "main",
    "task_id": "fix-rounding"
  },
  "event": {
    "id": "7c1f9a2e",
    "type": "test_failure",
    "timestamp": "2026-08-09T12:34:56Z",
    "summary": "test_totals failed with rounding mismatch",
    "files": ["src/totals.py", "tests/test_totals.py"],
    "metadata": { "error": "AssertionError: expected 124.20 got 124.19" }
  }
}