
# Loop Watchdog — Current Status

## Current Task

**TASK-05 — Error Normalization**

## Phase

**Phase 2 — Detection Engine V2**

## Status

**READY**

## Completed

### Phase 0 — Engineering Baseline
* TASK-00 — Create Engineering Contract ✅

### Phase 1 — Core Architecture
* TASK-01 — Formalize Event Model ✅
  * Expanded EventKind to 30 categories with semantic properties (is_progress, is_failure, is_file_modification, is_v1).
  * Added schema_version field for forward compatibility.
  * 13 new tests covering validation, serialization, backwards compatibility.

* TASK-02 — Redesign Session Identity ✅
  * Introduced SessionIdentity model with watchdog_session_id as canonical isolation key.
  * Supports repository, workspace, branch, agent, agent_session_id, task_id.
  * Backwards-compatible: legacy string session_id auto-mapped via Pydantic validator.
  * 5 new tests covering isolation, legacy compat, serialization.

* TASK-03 — Event Protocol V1 (LWEP) ✅
  * Created LoopWatchdogEnvelope with versioned protocol structure.
  * parse_event_payload accepts both LWEP envelope and legacy flat format.
  * Wired into /v1/watchdog/events endpoint (backwards compatible).
  * Documented in docs/EVENT_PROTOCOL.md.
  * 12 new tests covering parsing, round-trip, integration.

* TASK-04 — Persistence Abstraction ✅
  * Introduced SessionStore interface with load()/save() methods.
  * JsonSessionStore preserves existing atomic JSON file persistence.
  * Dependency injection support for future SQLite backend.
  * 7 new tests covering unit, integration, legacy JSON loading.

* Lint cleanup — All 44 ruff errors resolved across codebase.
* Fixed flaky time-bomb test (test_legacy_seed_demo_sessions_are_pruned_on_reload).

## Phase 1 Summary

* 54 tests passing
* Lint: All checks passed
* Architecture: Event Model → Session Identity → Event Protocol → Persistence
* Zero regression: loop_detector.py never modified during Phase 1
* Full backwards compatibility preserved

## Next

**Implement TASK-05: Improve error signatures by normalizing paths, line numbers, timestamps, UUIDs, ports, hashes, temporary directories, and machine-specific paths so equivalent failures produce equivalent signatures.**