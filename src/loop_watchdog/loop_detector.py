from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Iterable

from .config import WatchdogSettings
from .models import DetectorDecision, EventKind, WatchdogEvent

NON_WORD_RE = re.compile(r"[^a-z0-9_/\-.]+")
DIGIT_RE = re.compile(r"\d+")
HEX_RE = re.compile(r"\b[0-9a-f]{7,}\b")
WS_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    lowered = value.lower()
    lowered = HEX_RE.sub("<hex>", lowered)
    lowered = DIGIT_RE.sub("<n>", lowered)
    lowered = NON_WORD_RE.sub(" ", lowered)
    return WS_RE.sub(" ", lowered).strip()


def token_set(value: str) -> set[str]:
    return {token for token in normalize_text(value).split(" ") if len(token) > 2}


def jaccard_similarity(left: str, right: str) -> float:
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def sequence_similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def summarize_signature(summary: str, files: Iterable[str]) -> str:
    joined_files = " ".join(sorted(set(files)))
    return normalize_text(f"{summary} {joined_files}")


class LoopDetector:
    def __init__(self, settings: WatchdogSettings) -> None:
        self.settings = settings

    def fingerprint(self, kind: EventKind, summary: str, files: Iterable[str]) -> str:
        return normalize_text(f"{kind.value} {summarize_signature(summary, files)}")

    def error_signature(self, event: WatchdogEvent) -> str:
        source = event.metadata.get("error") or event.summary
        return normalize_text(str(source))

    def evaluate(self, events: list[WatchdogEvent]) -> DetectorDecision:
        recent = events[-self.settings.recent_window :]
        if len(recent) < 4:
            return DetectorDecision()

        score = 0.0
        reasons: list[str] = []
        repeated_files: list[str] = []
        repeated_errors: list[str] = []
        triggering_event_ids: list[str] = []

        request_events = [event for event in recent if event.kind == EventKind.AGENT_REQUEST]
        file_events = [
            event
            for event in recent
            if event.kind in {EventKind.FILE_EDIT, EventKind.PATCH_APPLY, EventKind.TEST_FAILURE}
            and event.files
        ]
        error_events = [
            event
            for event in recent
            if event.kind in {EventKind.TOOL_ERROR, EventKind.TEST_FAILURE}
            and event.error_signature
        ]
        success_events = [event for event in recent if event.kind == EventKind.TEST_PASS]

        similar_request_pairs = 0
        for left, right in zip(request_events, request_events[1:]):
            similarity = max(
                jaccard_similarity(left.summary, right.summary),
                sequence_similarity(left.summary, right.summary),
            )
            if similarity >= self.settings.request_similarity_threshold:
                similar_request_pairs += 1
                triggering_event_ids.extend([left.event_id, right.event_id])
        if similar_request_pairs >= 2:
            score += self.settings.repeated_request_weight
            reasons.append(
                f"Agent retried highly similar requests {similar_request_pairs + 1} times in the recent window."
            )

        repeated_file_group: tuple[str, ...] = ()
        file_group_counter = Counter(tuple(sorted(set(event.files))) for event in file_events if event.files)
        if file_group_counter:
            repeated_file_group, file_group_count = file_group_counter.most_common(1)[0]
            if file_group_count >= self.settings.file_repeat_threshold:
                score += self.settings.repeated_file_weight
                repeated_files = list(repeated_file_group)
                reasons.append(
                    f"The same file cluster was touched {file_group_count} times without a clear recovery signal."
                )
                triggering_event_ids.extend(
                    event.event_id
                    for event in file_events
                    if tuple(sorted(set(event.files))) == repeated_file_group
                )

        error_counter = Counter(event.error_signature for event in error_events)
        recurrent_errors = [
            signature for signature, count in error_counter.items() if count >= 2 and signature
        ]
        if recurrent_errors:
            score += self.settings.repeated_error_weight
            repeated_errors = recurrent_errors[:3]
            reasons.append("The session is repeating the same failure signature after multiple attempts.")
            triggering_event_ids.extend(
                event.event_id
                for event in error_events
                if event.error_signature in recurrent_errors
            )

        oscillation_pairs = 0
        for left, right in zip(recent, recent[1:]):
            if left.kind in {EventKind.FILE_EDIT, EventKind.PATCH_APPLY} and right.kind in {
                EventKind.TOOL_ERROR,
                EventKind.TEST_FAILURE,
            }:
                if not left.files or not right.files or set(left.files) & set(right.files):
                    oscillation_pairs += 1
            if left.kind in {EventKind.TOOL_ERROR, EventKind.TEST_FAILURE} and right.kind in {
                EventKind.FILE_EDIT,
                EventKind.PATCH_APPLY,
            }:
                if not left.files or not right.files or set(left.files) & set(right.files):
                    oscillation_pairs += 1
        if oscillation_pairs >= 3:
            score += self.settings.oscillation_weight
            reasons.append("The session is oscillating between edits and failures on the same surface area.")

        if not success_events and len(error_events) >= 2 and len(request_events) >= 3:
            score += self.settings.no_progress_weight
            reasons.append("Spend is growing without a passing test or a recovery event in the recent window.")

        paused = score >= self.settings.pause_score_threshold and len(reasons) >= 2
        recommendation = (
            "Pause the agent, inspect the repeated file cluster, and require a human-approved plan before resuming."
            if paused
            else ""
        )
        return DetectorDecision(
            paused=paused,
            score=round(score, 2),
            reasons=reasons,
            repeated_files=repeated_files,
            repeated_errors=repeated_errors,
            triggering_event_ids=list(dict.fromkeys(triggering_event_ids)),
            recommendation=recommendation,
        )

