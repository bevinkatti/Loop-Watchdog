# Loop Watchdog — V2/V3 Engineering Roadmap

> Master implementation roadmap for evolving Loop Watchdog from a Codex-focused watchdog into an agent-agnostic safety, observability, and recovery layer for AI coding agents.

---

## 1. Vision

Loop Watchdog should become a lightweight, local-first safety layer that protects developers from AI coding agents becoming trapped in repetitive fix-break loops.

The long-term architecture is:

```text
AI Coding Agent
      │
      ▼
Agent Adapter / Event Protocol
      │
      ▼
┌─────────────────────────────┐
│     Loop Watchdog Core      │
│                             │
│  Event Processing            │
│  Progress Analysis           │
│  Loop Detection              │
│  Risk Scoring                │
│  Recovery                    │
└──────────────┬──────────────┘
               │
       ┌───────┴────────┐
       ▼                ▼
   Local UX          Optional Cloud
   CLI/IDE           Team/Analytics
```

The core engine must remain:

* deterministic by default
* local-first
* privacy-conscious
* agent-agnostic
* low-latency
* explainable
* resilient
* easy to integrate

LLM-based analysis may eventually be added as an optional explanation/recommendation layer, but it must not become the authoritative enforcement mechanism.

---

# 2. Engineering Principles

Every implementation task must follow these principles:

1. Preserve existing functionality unless a task explicitly requires a breaking change.
2. Prefer incremental changes over rewrites.
3. Keep the core detector deterministic.
4. Keep agent-specific logic outside the core engine.
5. Keep local usage possible without cloud services.
6. Maintain backwards compatibility for persisted state and public APIs where practical.
7. Every feature must have tests.
8. Every completed task must update documentation/status.
9. Avoid premature infrastructure complexity.
10. Do not implement future-phase features early unless they are required dependencies.
11. Optimize for developer experience and adoption, not feature count.
12. The watchdog itself must never become an unnecessary source of developer friction.

---

# 3. Task Completion Definition

A task is complete only when all applicable items are satisfied:

* [ ] Implementation complete
* [ ] Existing functionality preserved
* [ ] Unit tests added/updated
* [ ] Integration tests added where applicable
* [ ] Relevant documentation updated
* [ ] Backwards compatibility checked
* [ ] Performance/security implications considered
* [ ] `IMPLEMENTATION_STATUS.md` updated
* [ ] `STATUS.md` updated
* [ ] Tests pass
* [ ] No known unresolved regression introduced

Do not mark a task complete merely because the code compiles.

---

# 4. Phase 0 — Engineering Baseline

## TASK-00 — Create Engineering Contract

Create the project's persistent engineering documentation:

```text
docs/ROADMAP.md
docs/IMPLEMENTATION_STATUS.md
docs/ARCHITECTURE.md
docs/EVENT_PROTOCOL.md
docs/DETECTOR.md
docs/DEVELOPMENT.md
STATUS.md
```

For the initial implementation, only `ROADMAP.md` and `IMPLEMENTATION_STATUS.md` are required. The remaining documents should be introduced when their corresponding systems are implemented.

### Acceptance Criteria

* Repository contains the master roadmap.
* Repository contains current implementation status.
* A new developer can determine the next task without reading previous conversations.
* Future AI coding sessions can continue from repository state alone.

---

# 5. Phase 1 — Core Architecture

## TASK-01 — Formalize Event Model

Expand and standardize the event model.

Potential event categories:

```text
AGENT_REQUEST
AGENT_RESPONSE

TOOL_CALL
TOOL_RESULT

FILE_CREATE
FILE_EDIT
FILE_DELETE

COMMAND_START
COMMAND_END

TEST_START
TEST_PASS
TEST_FAILURE

BUILD_START
BUILD_SUCCESS
BUILD_FAILURE

LINT_PASS
LINT_FAILURE

GIT_DIFF
GIT_COMMIT

USER_INTERVENTION

TASK_STARTED
TASK_PROGRESS
TASK_COMPLETED
```

Do not implement every producer yet. First establish a stable schema.

### Acceptance Criteria

* Versioned event model.
* Validation.
* Backwards-compatible parsing where practical.
* Tests.
* Documentation.

---

## TASK-02 — Redesign Session Identity

Ensure simultaneous agent sessions cannot share detector state accidentally.

Support concepts such as:

```text
organization
repository
workspace
branch
agent
agent_session
watchdog_session
task_id
```

Actual sessions should have unique generated identifiers.

### Acceptance Criteria

Two simultaneous sessions on the same repository and branch maintain completely independent state.

---

## TASK-03 — Event Protocol V1

Create the Loop Watchdog Event Protocol (LWEP).

Example:

```json
{
  "version": "1",
  "session": {
    "id": "...",
    "agent": "claude-code",
    "repository": "...",
    "branch": "..."
  },
  "event": {
    "id": "...",
    "type": "test_failure",
    "timestamp": "...",
    "files": [],
    "metadata": {}
  }
}
```

Document how third-party integrations can produce events.

---

## TASK-04 — Persistence Abstraction

Introduce storage interfaces such as:

```text
EventStore
SessionStore
```

Keep the existing JSON persistence implementation behind the abstraction.

Do not migrate to SQLite yet.

---

# 6. Phase 2 — Detection Engine V2

## TASK-05 — Error Normalization

Improve error signatures by normalizing:

* paths
* line numbers
* timestamps
* UUIDs
* ports
* hashes
* temporary directories
* machine-specific paths

Equivalent failures should produce equivalent signatures.

---

## TASK-06 — Test Failure Identity

Represent test failures structurally.

Capture, where available:

```text
framework
test_id
suite
command
exit_code
stacktrace_signature
failure_type
```

Repeated identical test failures should be strongly weighted by the detector.

---

## TASK-07 — Git Diff Fingerprinting

Create fingerprints for changes:

```text
diff_hash
normalized_diff_hash
files
symbols
lines_added
lines_removed
```

Detect:

* repeated patches
* near-identical patches
* reverted patches
* repeated edits to the same logical change

---

## TASK-08 — File Cluster Similarity

Replace strict file-set equality with similarity-based clustering.

For example:

```text
[A, B]
```

and:

```text
[A, B, C]
```

should be recognized as related.

---

## TASK-09 — Strategy Similarity

Create a strategy fingerprint using signals such as:

```text
request
files
commands
errors
diffs
tools
tests
```

Calculate strategy similarity between attempts.

---

## TASK-10 — Strategy Diversity

Introduce a strategy diversity signal.

Healthy:

```text
Strategy A
Strategy B
Strategy C
```

Potential loop:

```text
Strategy A
Strategy A
Strategy A
```

---

## TASK-11 — A→B→A Oscillation Detection

Detect oscillating states using:

* diffs
* file state
* errors
* strategy fingerprints

Example:

```text
State A
  ↓
State B
  ↓
State A
```

---

## TASK-12 — Progress Engine

Introduce a first-class progress score independent from loop risk.

Potential progress signals:

* test pass
* build pass
* lint pass
* error changed
* meaningful diff
* new files
* reduced failure severity
* strategy change
* task completion

---

## TASK-13 — Risk + Confidence Engine

Separate:

```text
risk_score
progress_score
confidence
```

Define states such as:

```text
HEALTHY
WATCH
WARNING
HIGH_RISK
CRITICAL
```

---

## TASK-14 — Early Warning + Soft Pause

Introduce graduated intervention:

```text
HEALTHY
    ↓
WATCH
    ↓
WARNING
    ↓
PAUSE
```

Allow configurable final attempts where appropriate.

---

## TASK-15 — Detector Explainability

Every detector decision should provide machine-readable evidence.

Example:

```json
{
  "reason": "Repeated failure with minimal strategy change",
  "signals": [
    {
      "type": "repeated_test_failure",
      "weight": 0.8
    }
  ]
}
```

Provide:

```bash
loop-watchdog explain
```

---

# 7. Phase 3 — Automatic Telemetry

## TASK-16 — Test/Command Telemetry

Automatically observe common commands where possible:

```text
pytest
npm test
cargo test
go test
mvn test
gradle test
```

Capture:

```text
command
working_directory
exit_code
duration
normalized_output
```

---

## TASK-17 — Build/Lint Telemetry

Support:

```text
build
lint
typecheck
```

and integrate their outcomes into the event stream.

---

## TASK-18 — Git Telemetry

Observe relevant Git activity such as:

```text
git diff
git status
git commit
git checkout
git reset
```

where safely possible.

---

## TASK-19 — Filesystem Watcher V2

Move toward event-driven filesystem monitoring.

Support:

* Windows
* Linux
* macOS

Add awareness of:

```text
.gitignore
.watchdogignore
```

Avoid expensive full-tree scanning for large repositories.

---

# 8. Phase 4 — Agent-Agnostic Integrations

## TASK-20 — Agent Adapter Interface

Create a common adapter interface for agents.

Conceptually:

```text
detect()
start()
stop()
configure()
emit_events()
```

The core engine must not contain agent-specific behavior.

---

## TASK-21 — Claude Code Integration

Implement first-class Claude Code support.

Target:

```bash
loop-watchdog start claude
```

and automatic setup through:

```bash
loop-watchdog init
```

where supported.

---

## TASK-22 — Codex Integration V2

Move existing Codex support onto the common adapter architecture.

Avoid duplicated detector logic.

---

## TASK-23 — Gemini CLI + Generic Adapter

Add:

* Gemini CLI
* generic OpenAI-compatible clients

The generic adapter should provide a fallback integration path.

---

## TASK-24 — Agent Metadata

Capture:

```text
agent
agent_version
provider
model
model_version
```

where available.

---

# 9. Phase 5 — Developer Experience

## TASK-25 — `loop-watchdog init`

Automatically detect:

* operating system
* Git
* Claude Code
* Codex
* Gemini
* Python
* Node
* Rust
* Go
* test framework
* IDE

Generate sensible configuration.

---

## TASK-26 — `loop-watchdog doctor`

Provide environment diagnostics.

Example:

```text
✓ Python
✓ Git
✓ Claude Code
✓ Repository
✓ Persistence

⚠ Test telemetry not configured
```

---

## TASK-27 — CLI Lifecycle

Provide a coherent CLI:

```text
loop-watchdog start
loop-watchdog stop
loop-watchdog status
loop-watchdog sessions
loop-watchdog events
loop-watchdog resume
loop-watchdog reset
loop-watchdog config
```

---

## TASK-28 — Recovery System

When an agent is paused, provide recovery actions:

```text
Resume
Resume with new plan
Run failing test
Inspect repeated files
Stop agent
```

---

## TASK-29 — Changed-Plan Validation V2

Expand the current plan digest mechanism.

A recovery plan should be able to include:

```text
root cause hypothesis
strategy
files
validation command
```

Where possible, detect whether the new strategy is genuinely different.

---

## TASK-30 — Bypass + Failure Policy

Support explicit proxy failure policy:

```yaml
failure_policy: open
```

or:

```yaml
failure_policy: closed
```

Provide an emergency bypass/disable mechanism.

---

# 10. Phase 6 — Cost + Observability

## TASK-31 — Token + Cost Tracking

Capture:

```text
input_tokens
output_tokens
cached_tokens
total_tokens
model
provider
estimated_cost
```

Display estimated spend and potential savings.

---

## TASK-32 — Performance + Resource Benchmarking

Measure:

```text
upstream latency
watchdog latency
proxy overhead
CPU
RAM
events/sec
```

Provide:

```bash
loop-watchdog benchmark
```

---

## TASK-33 — OpenTelemetry

Expose useful spans and metrics for:

* OpenTelemetry Collector
* Prometheus
* Grafana
* Datadog

---

## TASK-34 — SQLite Storage

Implement a SQLite-backed storage implementation behind the storage abstraction.

Keep JSON available where useful for lightweight installations.

---

# 11. Phase 7 — Reliability + Security

## TASK-35 — Proxy Reliability

Harden:

* timeouts
* authentication failures
* rate limits
* upstream failures
* malformed responses
* connection resets
* client disconnects
* streaming
* SSE
* partial streams
* resource cleanup

---

## TASK-36 — Concurrency + Crash Recovery

Test and harden:

* concurrent events
* simultaneous sessions
* crashes
* restart
* partial writes
* corrupt state
* duplicate incidents
* lost events

---

## TASK-37 — API Security

Implement as required for non-local deployment:

* authentication
* authorization
* rate limiting
* payload size limits
* strict validation
* dashboard authentication

---

## TASK-38 — Privacy + Webhook Security

Address:

* webhook SSRF
* secret leakage
* sensitive payloads
* retention
* redaction
* configurable telemetry
* clear privacy documentation

Default behavior should remain local-first.

---

# 12. Phase 8 — Evaluation

## TASK-39 — Detector Evaluation Corpus

Create trace datasets covering:

```text
healthy iteration
repeated failure
oscillation
refactor
migration
dependency upgrade
test fixing
false positives
false negatives
```

Include expected detector outcomes.

---

## TASK-40 — Replay + Evaluation Framework

Implement:

```bash
loop-watchdog replay trace.json
loop-watchdog eval
```

Measure:

```text
precision
recall
F1
false positives
false negatives
detection latency
CPU
RAM
```

---

# 13. Phase 9 — IDE + Developer Interface

## TASK-41 — Dashboard V2

Make the dashboard developer-oriented.

Show:

```text
Session Health
Loop Risk
Progress
Confidence
Attempts
Repeated files
Repeated errors
Estimated cost
Recommended action
```

Use real-time updates where appropriate.

---

## TASK-42 — VS Code Extension

Provide:

* sidebar
* session status
* risk
* progress
* explanation
* pause
* resume
* stop
* notifications

---

## TASK-43 — Notifications + Terminal UX

Support:

* terminal status
* desktop notifications
* IDE notifications

Target:

* Windows
* macOS
* Linux

---

# 14. Phase 10 — SDK + Ecosystem

## TASK-44 — Python SDK

Provide a simple Python API for emitting events and interacting with the watchdog.

---

## TASK-45 — TypeScript SDK

Provide a TypeScript/JavaScript API.

---

## TASK-46 — Public Event Protocol Documentation

Document LWEP integration for:

* HTTP
* Python
* TypeScript
* Rust
* Go

Provide examples.

---

## TASK-47 — MCP Adapter

Expose watchdog status, diagnosis, events, and recovery capabilities through MCP.

MCP must remain an adapter rather than the core architecture.

---

# 15. Phase 11 — Community Readiness

## TASK-48 — Open Source Documentation

Add/update:

```text
CONTRIBUTING.md
SECURITY.md
CODE_OF_CONDUCT.md
DEVELOPMENT.md
ARCHITECTURE.md
EVENT_PROTOCOL.md
```

Add:

```text
examples/
```

for major integrations.

---

## TASK-49 — CI/CD + Release Automation

CI should cover:

```text
Linux
Windows
macOS

Python 3.11
Python 3.12
Python 3.13
```

Run:

```text
ruff
pytest
mypy
build
integration tests
package validation
```

Automate PyPI releases.

---

## TASK-50 — Adoption Experience

Improve:

* README
* installation
* quickstart
* demo GIF
* architecture diagram
* supported agents
* privacy explanation
* security model
* performance claims

The first-time user should understand and run the project within minutes.

---

# 16. Phase 12 — Cloud + Teams

These tasks should only begin after the local developer experience is strong.

## TASK-51 — Cloud API V2

Introduce:

```text
organizations
projects
repositories
sessions
incidents
```

with appropriate API boundaries.

---

## TASK-52 — Team Dashboard

Provide:

```text
active sessions
paused sessions
warnings
loop rate
cost
estimated savings
```

---

## TASK-53 — Team Notifications

Support:

```text
Slack
Email
Webhooks
```

with secure configuration.

---

## TASK-54 — Historical Analytics

Analyze by:

```text
repository
agent
model
provider
language
task
team
time
```

---

## TASK-55 — Organization + RBAC

Introduce:

```text
organization
project
member
role
permissions
API keys
```

Only after team/cloud requirements are validated.

---

# 17. Recommended Execution Order

Execute tasks in this order unless a task is explicitly blocked:

```text
00
01
02
03
04

05
06
07
08
09
10
11
12
13
14
15

16
17
18
19

20
21
22
23
24

25
26
27
28
29
30

31
32
33
34

35
36
37
38

39
40

41
42
43

44
45
46
47

48
49
50

51
52
53
54
55
```

Tasks may be worked on in parallel only when their dependencies are satisfied.

---

# 18. Dependency Rules

Core dependencies:

```text
TASK-01
   ↓
TASK-03
   ↓
TASK-20
```

Detection dependencies:

```text
TASK-05 ─┐
TASK-06 ─┤
TASK-07 ─┼→ TASK-09 → TASK-10 → TASK-13
TASK-08 ─┤                         ↓
TASK-11 ─┘                     TASK-14
                                  ↓
                              TASK-15
```

Telemetry:

```text
TASK-01 → TASK-16/17/18
TASK-07 → TASK-18
```

Agent integration:

```text
TASK-03 → TASK-20 → TASK-21/22/23
```

Storage:

```text
TASK-04 → TASK-34
```

Evaluation:

```text
TASK-05 through TASK-15 → TASK-39 → TASK-40
```

Cloud:

```text
TASK-25 through TASK-50 → TASK-51+
```

---

# 19. Fresh-Chat Development Protocol

Every future implementation session should follow this protocol.

Before changing code:

1. Read `docs/ROADMAP.md`.
2. Read `docs/IMPLEMENTATION_STATUS.md`.
3. Read root `STATUS.md` if present.
4. Inspect the current repository rather than assuming previous implementation details.
5. Identify the current task.
6. Inspect relevant existing code and tests.
7. Implement only the requested task unless a dependency requires a small supporting change.
8. Run relevant tests.
9. Update documentation.
10. Update implementation status.
11. Report the exact next task.

Never assume previous conversation context is available.

---

# 20. Standard Task Completion Record

For every completed task, record:

```text
TASK:
Status:
Date:
Summary:
Files changed:
Tests:
Architecture decisions:
Breaking changes:
Known limitations:
Next task:
```

---

# 21. Definition of Success

Loop Watchdog V2/V3 is successful when a developer can:

```bash
pipx install loop-watchdog
cd my-project
loop-watchdog init
loop-watchdog start claude
```

and receive protection without understanding the internal detector architecture.

The long-term product should support:

```text
Claude Code
Codex
Gemini CLI
other coding agents
VS Code
SDK integrations
HTTP integrations
```

while maintaining:

```text
local-first operation
low latency
deterministic enforcement
explainable decisions
safe recovery
strong privacy
high detector precision
```

---

# 22. Non-Goals

Do not prioritize the following before the core system is mature:

* mobile applications
* unnecessary microservices
* multi-region infrastructure
* complex enterprise RBAC
* LLM-based enforcement
* excessive cloud dependencies
* feature-heavy analytics before useful data exists

The project should remain focused on preventing and recovering from AI coding-agent loops.
