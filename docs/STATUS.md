# Loop Watchdog — Current Status

## Current Task

**TASK-16 — Test/Command Telemetry**

## Phase

**Phase 3 — Automatic Telemetry**

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

### Phase 2 — Detection Engine V2
* TASK-05 — Error Normalization ✅
  * Added regex stack for UUIDs, ISO timestamps, temp directories, user/home paths, absolute paths, ports, hashes, and line numbers.
  * Updated NON_WORD_RE to preserve `<` and `>` placeholders for strong token signals.
  * Equivalent failures across different machines/environments now produce identical signatures.

* TASK-06 — Test Failure Identity ✅
  * Introduced TestFailureIdentity model (framework, suite, test_id, command, exit_code, failure_type, stacktrace_signature).
  * Added extract_test_failure() method to LoopDetector.
  * Detector now strongly weights identical repeated test failures.

* TASK-07 — Git Diff Fingerprinting ✅
  * Introduced GitDiffFingerprint model (diff_hash, normalized_diff_hash, reversed_hash, files, symbols, lines_added, lines_removed).
  * Normalizes diffs by stripping index hashes, hunk line numbers, and file paths while preserving +/- markers.
  * Detects repeated patches, near-identical patches, and reverted patches.

* TASK-08 — File Cluster Similarity ✅
  * Replaced strict file-set equality with Jaccard similarity-based greedy clustering.
  * [A, B] and [A, B, C] are now recognized as related clusters.
  * Extracts core intersection files for explainable reporting.

* TASK-09 — Strategy Similarity ✅
  * Added build_strategy_fingerprint() combining request, files, errors, and diff hashes.
  * Added strategy_similarity() using Jaccard and sequence similarity.
  * Detects when agent repeats highly similar strategies consecutively.

* TASK-10 — Strategy Diversity ✅
  * Added unique_strategies count to DetectorDecision.
  * Introduced negative strategy_diversity_weight to reward healthy exploration.
  * Agent trying 3+ distinct strategies receives a score reduction (protects from false positives).

* TASK-11 — A→B→A Oscillation Detection ✅
  * Builds state_sequence from diffs, errors, and file sets.
  * Detects A→B→A patterns where agent applies, reverts/fails, and reapplies the same change.
  * Replaces basic edit→failure oscillation with precise state-based detection.

* TASK-12 — Progress Engine ✅
  * Introduced independent progress_score separate from loop risk score.
  * Tracks success events (TEST_PASS, BUILD_SUCCESS, LINT_PASS, TASK_COMPLETED).
  * Detects error signature changes as progress signal.

* TASK-13 — Risk + Confidence Engine ✅
  * Introduced HealthState enum (HEALTHY, WATCH, WARNING, HIGH_RISK, CRITICAL).
  * Added confidence score (0.0–1.0) based on number of distinct signals firing.
  * Configurable thresholds for each health state transition.

* TASK-14 — Early Warning + Soft Pause ✅
  * Added soft_pause flag for WARNING and HIGH_RISK states.
  * Graduated intervention: agent receives early warning before hard pause.
  * Exposed current_state in SessionStatus and SessionSnapshot for dashboard visibility.

* TASK-15 — Detector Explainability ✅
  * Introduced DetectorSignal model (signal_type, weight, detail).
  * Every score contribution now produces a structured, machine-readable signal.
  * Enables debugging, dashboard visualization, and integration evidence.

## Phase 2 Summary

* Detection engine evolved from binary pause/resume to graduated, explainable risk scoring.
* 11 new detection signals covering errors, diffs, files, strategies, oscillation, and progress.
* Full backwards compatibility preserved — no breaking changes to existing API or persistence.
* All signals are deterministic, local-first, and agent-agnostic.

## Next

**Implement TASK-16: Automatically observe common test/build commands (pytest, npm test, cargo test, go test, mvn test, gradle test) and capture command, working_directory, exit_code, duration, and normalized_output as structured events.**