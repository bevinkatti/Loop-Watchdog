# Architecture

## Local Proxy

The local proxy is the operational heart of Loop Watchdog.

- It exposes OpenAI-compatible endpoints so existing agents can target it with minimal friction.
- It keeps a short-lived in-memory session timeline keyed by a stable session id.
- It runs loop heuristics before forwarding the next request upstream.
- It pauses a session by returning a structured `409` response once an incident is active.

This means the watchdog does not need to fight the model after a loop starts. It simply refuses to sponsor the next expensive attempt until a human or wrapper explicitly resumes the session.

## Session Model

Each session is a rolling graph of events:

- `agent_request`
- `agent_response`
- `file_edit`
- `patch_apply`
- `tool_error`
- `test_failure`
- `test_pass`
- `manual_resume`
- `manual_kill`
- `session_note`

Events carry summary text, affected files, and arbitrary metadata. The detector turns those into normalized signatures and examines only the recent window, which keeps the decision fast and explainable.

## Loop Heuristics

The detector scores four families of signals:

1. Repeated request context
2. Repeated file churn
3. Repeated failure signatures
4. Edit-error oscillation with no success event

The threshold is configurable. A session only pauses when at least two signal families agree, which sharply reduces false positives during normal iterative debugging.

## Alert Flow

When a session pauses:

1. The local proxy creates a `LoopIncident`
2. The incident is posted to the configured webhook
3. The Cloudflare Worker verifies the request
4. The Worker stores the incident in D1
5. The Worker optionally relays a human-friendly summary to Slack and email

## Why Not Rely On Another LLM For Detection

This version does not depend on a second model to decide whether the first model is looping.

- It avoids extra latency on every request
- It avoids extra cost while trying to save cost
- It makes the pause decision auditable

Gemini or another model can still add value later for classification, summarization, or policy suggestions, but the stop/no-stop boundary should remain deterministic.

