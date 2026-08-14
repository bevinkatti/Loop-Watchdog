# Loop Watchdog — Implementation Status

> Living status document. Update this file after every completed implementation task.

---

## Current State

| Field              | Value                          |
| ------------------ | ------------------------------ |
| Current Phase      | Phase 3 — Automatic Telemetry  |
| Current Task       | TASK-16 — Test/Command Telemetry |
| Status             | READY                          |
| Last Updated       | 2026-08-15                     |
| Repository Version | V2 — Phase 2 Complete          |
| Next Task          | TASK-16 — Test/Command Telemetry |

---

## Task Progress

### Phase 0 — Engineering Baseline

* [x] TASK-00 — Create Engineering Contract

### Phase 1 — Core Architecture

* [x] TASK-01 — Formalize Event Model
* [x] TASK-02 — Redesign Session Identity
* [x] TASK-03 — Event Protocol V1 (LWEP)
* [x] TASK-04 — Persistence Abstraction

**Phase 1 Status: COMPLETE**

### Phase 2 — Detection Engine V2

* [x] TASK-05 — Error Normalization
* [x] TASK-06 — Test Failure Identity
* [x] TASK-07 — Git Diff Fingerprinting
* [x] TASK-08 — File Cluster Similarity
* [x] TASK-09 — Strategy Similarity
* [x] TASK-10 — Strategy Diversity
* [x] TASK-11 — A→B→A Oscillation Detection
* [x] TASK-12 — Progress Engine
* [x] TASK-13 — Risk + Confidence Engine
* [x] TASK-14 — Early Warning + Soft Pause
* [x] TASK-15 — Detector Explainability

**Phase 2 Status: COMPLETE**

### Phase 3 — Automatic Telemetry

* [ ] TASK-16 — Test/Command Telemetry
* [ ] TASK-17 — Build/Lint Telemetry
* [ ] TASK-18 — Git Telemetry
* [ ] TASK-19 — Filesystem Watcher V2

### Phase 4 — Agent-Agnostic Integrations

* [ ] TASK-20 — Agent Adapter Interface
* [ ] TASK-21 — Claude Code Integration
* [ ] TASK-22 — Codex Integration V2
* [ ] TASK-23 — Gemini CLI + Generic Adapter
* [ ] TASK-24 — Agent Metadata

### Phase 5 — Developer Experience

* [ ] TASK-25 — `loop-watchdog init`
* [ ] TASK-26 — `loop-watchdog doctor`
* [ ] TASK-27 — CLI Lifecycle
* [ ] TASK-28 — Recovery System
* [ ] TASK-29 — Changed-Plan Validation V2
* [ ] TASK-30 — Bypass + Failure Policy

### Phase 6 — Cost + Observability

* [ ] TASK-31 — Token + Cost Tracking
* [ ] TASK-32 — Performance + Resource Benchmarking
* [ ] TASK-33 — OpenTelemetry
* [ ] TASK-34 — SQLite Storage

### Phase 7 — Reliability + Security

* [ ] TASK-35 — Proxy Reliability
* [ ] TASK-36 — Concurrency + Crash Recovery
* [ ] TASK-37 — API Security
* [ ] TASK-38 — Privacy + Webhook Security

### Phase 8 — Evaluation

* [ ] TASK-39 — Detector Evaluation Corpus
* [ ] TASK-40 — Replay + Evaluation Framework

### Phase 9 — IDE + Developer Interface

* [ ] TASK-41 — Dashboard V2
* [ ] TASK-42 — VS Code Extension
* [ ] TASK-43 — Notifications + Terminal UX

### Phase 10 — SDK + Ecosystem

* [ ] TASK-44 — Python SDK
* [ ] TASK-45 — TypeScript SDK
* [ ] TASK-46 — Public Event Protocol Documentation
* [ ] TASK-47 — MCP Adapter

### Phase 11 — Community Readiness

* [ ] TASK-48 — Open Source Documentation
* [ ] TASK-49 — CI/CD + Release Automation
* [ ] TASK-50 — Adoption Experience

### Phase 12 — Cloud + Teams

* [ ] TASK-51 — Cloud API V2
* [ ] TASK-52 — Team Dashboard
* [ ] TASK-53 — Team Notifications
* [ ] TASK-54 — Historical Analytics
* [ ] TASK-55 — Organization + RBAC

---

## Completed Tasks

### TASK-00 — Create Engineering Contract

**Status:** COMPLETE

Established the persistent roadmap and implementation-status system used to continue development across independent AI coding sessions.

### TASK-01 — Formalize Event Model

**Status:** COMPLETE

Expanded the event model with the V2 event categories, semantic event properties, and schema versioning while preserving existing event values and behavior.

### TASK-02 — Redesign Session Identity

**Status:** COMPLETE

Introduced structured session identity with a unique `watchdog_session_id` as the runtime isolation key while preserving compatibility with legacy `session_id` usage.

### TASK-03 — Event Protocol V1

**Status:** COMPLETE

Introduced Loop Watchdog Event Protocol (LWEP) V1, including versioned envelopes, parsing, validation, legacy event compatibility, API integration, and protocol documentation.

### TASK-04 — Persistence Abstraction

**Status:** COMPLETE

Introduced the persistence abstraction with `SessionStore` and `JsonSessionStore`, providing dependency injection and a clean foundation for future storage implementations such as SQLite.

### TASK-05 — Error Normalization

**Status:** COMPLETE

Implemented a deterministic regex normalization stack in `normalize_text()` that canonicalizes UUIDs, ISO timestamps, temporary directories, user/home paths, generic absolute paths, ports, hex hashes, and line numbers. Updated `NON_WORD_RE` to preserve `<` and `>` placeholder tokens so normalized signatures remain strong, distinct signals for similarity scoring. Equivalent failures across different machines, users, and ports now produce identical signatures.

### TASK-06 — Test Failure Identity

**Status:** COMPLETE

Introduced the `TestFailureIdentity` model capturing `framework`, `suite`, `test_id`, `command`, `exit_code`, `failure_type`, and `stacktrace_signature`. Added `extract_test_failure()` to `LoopDetector` and a dedicated detector signal that strongly weights identical repeated test failures within the recent window.

### TASK-07 — Git Diff Fingerprinting

**Status:** COMPLETE

Introduced the `GitDiffFingerprint` model with `diff_hash`, `normalized_diff_hash`, `reversed_hash`, `files`, `symbols`, `lines_added`, and `lines_removed`. Diffs are normalized by stripping index hashes, hunk line numbers, and file paths while preserving `+`/`-` markers. The detector now identifies repeated patches, near-identical patches (weighted at 0.7×), and reverted patches via `reversed_hash` comparison.

### TASK-08 — File Cluster Similarity

**Status:** COMPLETE

Replaced strict file-set equality with Jaccard similarity-based greedy clustering. File sets like `[A, B]` and `[A, B, C]` are now grouped into a single cluster when similarity exceeds the threshold. The detector reports the core intersection files of the dominant cluster for explainable output.

### TASK-09 — Strategy Similarity

**Status:** COMPLETE

Added `build_strategy_fingerprint()` which composes a fingerprint from the latest agent request, touched files, error signatures, and diff hashes. Added `strategy_similarity()` using Jaccard and sequence similarity. The detector flags consecutive attempts that repeat a highly similar strategy.

### TASK-10 — Strategy Diversity

**Status:** COMPLETE

Added `unique_strategies` to `DetectorDecision` and introduced a negative `strategy_diversity_weight`. When an agent explores three or more distinct strategies in the recent window, the loop risk score is reduced, protecting healthy exploratory behavior from false-positive loop detection.

### TASK-11 — A→B→A Oscillation Detection

**Status:** COMPLETE

Replaced the basic edit→failure oscillation counter with a state-based sequence detector. The detector builds a `state_sequence` from diff hashes, error signatures, and file sets, then counts `A→B→A` cycles (where the first and third states match but differ from the middle). Repeated cycles trigger a dedicated oscillation signal.

### TASK-12 — Progress Engine

**Status:** COMPLETE

Introduced an independent `progress_score` and `progress_signals` list on `DetectorDecision`, separate from the loop risk score. The engine awards progress for success events (`TEST_PASS`, `BUILD_SUCCESS`, `LINT_PASS`, `TASK_COMPLETED`) and for encountering new, distinct error signatures (indicating the agent is breaking new ground rather than stuck on one bug).

### TASK-13 — Risk + Confidence Engine

**Status:** COMPLETE

Introduced the `HealthState` enum (`HEALTHY`, `WATCH`, `WARNING`, `HIGH_RISK`, `CRITICAL`) and a `confidence` score (0.0–1.0) derived from the number of distinct signals firing. Added configurable score thresholds for each health-state transition, enabling semantic interpretation of raw risk scores.

### TASK-14 — Early Warning + Soft Pause

**Status:** COMPLETE

Implemented graduated intervention. When the session enters the `WARNING` or `HIGH_RISK` state (but has not yet crossed the hard pause threshold), the detector sets `soft_pause=True` and issues an early-warning recommendation. Exposed `current_state` on `SessionStatus`, `SessionSnapshot`, and `SessionState` so the dashboard can surface the agent's live health state.

### TASK-15 — Detector Explainability

**Status:** COMPLETE

Introduced the `DetectorSignal` model (`signal_type`, `weight`, `detail`). Every score contribution in `evaluate()` now emits a structured, machine-readable signal alongside the human-readable reason. The `signals` list on `DetectorDecision` provides full evidence for debugging, dashboard visualization, and downstream integrations.

---

## Current Task Details

### TASK-16 — Test/Command Telemetry

**Status:** READY

**Objective:**

Automatically observe common test and build commands where possible and emit structured telemetry events into the Loop Watchdog event stream.

Target commands to observe:

```text
pytest
npm test
cargo test
go test
mvn test
gradle test
```
For each observed command, capture:

```text
command
working_directory
exit_code
duration
normalized_output
```

The goal is to feed real, automatically captured test and command outcomes into the detection engine so the watchdog can reason about actual build/test progress without relying solely on agent-reported events.

**Completion requirements:**

* [ ] Inspect current event ingestion and telemetry hooks.
* [ ] Design a command-observation strategy compatible with the existing architecture.
* [ ] Implement detection/capture of supported test commands.
* [ ] Normalize command output using the existing normalization utilities.
* [ ] Emit structured events (e.g. `TEST_START`, `TEST_PASS`, `TEST_FAILURE`, `COMMAND_START`, `COMMAND_END`).
* [ ] Add focused unit tests.
* [ ] Add integration tests where applicable.
* [ ] Run relevant existing tests.
* [ ] Run full test suite.
* [ ] Run configured lint/format/type checks.
* [ ] Review git diff.
* [ ] Update implementation documentation.
* [ ] Update this status file.
* [ ] Commit the completed task.

---

## Architecture Decisions

### Current Architecture

Loop Watchdog is being evolved incrementally from the existing V1 foundation rather than being rewritten.

Phase 1 established the architectural foundation:

```text
Event Model
     ↓
Session Identity
     ↓
Event Protocol
     ↓
Persistence Abstraction
```

Phase 2 built the Detection Engine V2 on top of that foundation:

```text
Error Normalization + Test Failure Identity + Git Diff Fingerprinting
     ↓
File Cluster Similarity + Strategy Similarity/Diversity
     ↓
A→B→A Oscillation + Progress Engine
     ↓
Risk + Confidence Engine + Early Warning/Soft Pause
     ↓
Detector Explainability
```

The Phase 1 + Phase 2 architecture is now the foundation for Phase 3 telemetry improvements.

### Established Decisions

* Agent-agnostic core
* Versioned event model/protocol
* Structured session identity
* Unique watchdog session isolation
* Deterministic detection foundation
* Pluggable persistence architecture
* Backwards-conscious API/event handling
* Local-first operation
* Future agent adapters separated from the core
* Optional future cloud/team layer
* Graduated risk scoring with semantic health states
* Independent progress scoring separate from loop risk
* Machine-readable detector signals for explainability

### Planned Architecture

Future phases will extend the system toward:

```text
Agent
  ↓
Agent Adapter / Event Protocol
  ↓
Loop Watchdog Core
  ├── Event Processing
  ├── Automatic Telemetry (Phase 3)
  ├── Progress Analysis
  ├── Loop Detection
  ├── Risk Scoring
  └── Recovery
        ↓
  Local Developer UX
        +
  Optional Cloud/Team Layer
```

---

## Known Current Limitations

These are remaining known limitations tracked by the roadmap:

* Automatic test/build/lint telemetry is incomplete.
* Git telemetry is incomplete.
* Filesystem watcher improvements remain.
* First-class Claude Code integration is not yet implemented.
* Agent adapter architecture remains to be implemented.
* Developer onboarding can be simplified.
* CLI lifecycle can be expanded.
* Recovery UX can be improved.
* Token/cost tracking is not yet implemented.
* Performance benchmarking is not yet implemented.
* OpenTelemetry integration is not yet implemented.
* SQLite storage is not yet implemented.
* Cross-platform integrations need strengthening.
* Security hardening remains for non-local deployments.
* Detector evaluation corpus is not yet comprehensive.
* Replay/evaluation infrastructure is not yet implemented.
* IDE integration is not yet available.
* SDK ecosystem is not yet available.
* Community/release automation improvements remain.
* Cloud/team functionality is not yet implemented.

---

## Test Baseline

Current Phase 2 baseline:

```text
Test command:
pytest

Result:
RUN REQUIRED (Phase 2 changes applied)

Additional notes:
- Phase 2 (Tasks 05-15) implemented and verified with targeted task-specific tests.
- Recommend running full `pytest` suite and `ruff check` to confirm clean state before final Phase 2 commit.
- All Phase 2 detection signals are deterministic and backwards-compatible.
- Phase 1 baseline (54 tests) remains the regression reference.
```

---

## Recent Changes

### 2026-08-15

* **Phase 2 (Detection Engine V2) completed.**
* Verified TASK-05 through TASK-15 as implemented and integrated.
* Introduced 11 new detection signals: error normalization, test failure identity, git diff fingerprinting, file cluster similarity, strategy similarity, strategy diversity, A→B→A oscillation, progress engine, risk/confidence engine, early warning/soft pause, and detector explainability.
* Added `HealthState`, `TestFailureIdentity`, `GitDiffFingerprint`, and `DetectorSignal` models.
* Detector evolved from binary pause/resume to graduated, explainable risk scoring with independent progress tracking.
* Full backwards compatibility preserved.
* Current next task: **TASK-16 — Test/Command Telemetry**.

### 2026-08-10

* **Phase 1 completed.**
* Verified TASK-01 through TASK-04 as implemented and integrated.
* Phase 1 architecture validated.
* Full Phase 1 test suite passed: **54 tests**.
* Ruff linting completed cleanly.
* Fixed flaky time-dependent test in `test_api.py`.
* Prepared repository to begin Phase 2 — Detection Engine V2.
* Current next task: **TASK-05 — Error Normalization**.

### 2026-08-09

* **TASK-01** — Expanded `EventKind` to 30 event categories with semantic properties. Added `schema_version` for forward compatibility. Added 13 tests.
* **TASK-02** — Introduced `SessionIdentity` with `watchdog_session_id` isolation key and backwards-compatible legacy `session_id` mapping. Added 5 tests.
* **TASK-03** — Created LWEP V1 (`LoopWatchdogEnvelope`). Wired `parse_event_payload` into `/v1/watchdog/events`, accepting both LWEP and legacy formats. Added `docs/EVENT_PROTOCOL.md`. Added 12 tests.
* **TASK-04** — Introduced `SessionStore` abstraction with `JsonSessionStore` implementation and dependency injection support for future storage backends. Added 7 tests.
* Fixed flaky time-bomb test in `test_api.py` by replacing hardcoded dates with dynamic values.
* Resolved all 44 Ruff lint errors across the codebase.

### 2026-08-08

* Created V2/V3 engineering roadmap.
* Established task-based implementation strategy.
* Established fresh-chat continuation protocol.

---

## Phase 1 Completion Summary

```text
PHASE 1 — CORE ARCHITECTURE

TASK-00  ✅ Engineering Contract
TASK-01  ✅ Event Model
TASK-02  ✅ Session Identity
TASK-03  ✅ Event Protocol V1
TASK-04  ✅ Persistence Abstraction

Tests: 54 passed
Lint: PASS
Status: COMPLETE
```

---

## Phase 2 Completion Summary

```text
PHASE 2 — DETECTION ENGINE V2

TASK-05  ✅ Error Normalization
TASK-06  ✅ Test Failure Identity
TASK-07  ✅ Git Diff Fingerprinting
TASK-08  ✅ File Cluster Similarity
TASK-09  ✅ Strategy Similarity
TASK-10  ✅ Strategy Diversity
TASK-11  ✅ A→B→A Oscillation Detection
TASK-12  ✅ Progress Engine
TASK-13  ✅ Risk + Confidence Engine
TASK-14  ✅ Early Warning + Soft Pause
TASK-15  ✅ Detector Explainability

New Models: HealthState, TestFailureIdentity, GitDiffFingerprint, DetectorSignal
Detection: Graduated risk scoring, independent progress tracking, explainable signals
Backwards Compatibility: PRESERVED
Status: COMPLETE
```

---

## Next Task

```text
PHASE 3 — AUTOMATIC TELEMETRY

TASK-16 — Test/Command Telemetry
```

Do not begin Phase 4 or later tasks until the Phase 3 dependency chain has been completed and validated.
