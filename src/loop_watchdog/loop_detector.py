from __future__ import annotations

import re
import hashlib
from collections import Counter
from collections.abc import Iterable
from difflib import SequenceMatcher

from .config import WatchdogSettings
from .models import DetectorDecision, EventKind, GitDiffFingerprint, TestFailureIdentity, WatchdogEvent

# --- TASK-05: Error Normalization Regexes ---
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?")
TIMESTAMP_RE = re.compile(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}")
# TASK-07: Diff normalization
DIFF_INDEX_RE = re.compile(r"^index [0-9a-f]+\.\.[0-9a-f]+.*$", re.MULTILINE)
DIFF_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@.*$", re.MULTILINE)
DIFF_PATH_RE = re.compile(r"^(?:---|\+\+\+) [ab]/.*$", re.MULTILINE)
DIFF_SYMBOL_RE = re.compile(r"^[ +-]\s*(?:def |class |function |const |let |var |fn |pub fn )\s*(\w+)", re.MULTILINE)

# Directories (Specificity order matters!)
TMP_DIR_RE = re.compile(
    r"(?:/private/var/folders/[^\s]+|/tmp/[^\s]+|[A-Z]:\\Temp\\[^\s]+|[A-Z]:\\tmp\\[^\s]+)",
    re.IGNORECASE,
)
USER_DIR_RE = re.compile(
    r"(?:/Users/[^\s]+|/home/[^\s]+|[A-Z]:\\Users\\[^\s]+)",
    re.IGNORECASE,
)
ABS_PATH_RE = re.compile(r"(?:/[^\s]+|[A-Z]:\\[^\s]+)", re.IGNORECASE)

PORT_RE = re.compile(r":(\d{2,5})\b")
HEX_RE = re.compile(r"\b[0-9a-f]{7,}\b")
DIGIT_RE = re.compile(r"\d+")

# Added < and > to allowed characters so placeholders like <path> survive
NON_WORD_RE = re.compile(r"[^a-z0-9_/\-<>.]+")
WS_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    lowered = value.lower()
    
    # 1. UUIDs
    lowered = UUID_RE.sub("<uuid>", lowered)
    
    # 2. Timestamps
    lowered = ISO_DATE_RE.sub("<timestamp>", lowered)
    lowered = TIMESTAMP_RE.sub("<timestamp>", lowered)
    
    # 3. Ports
    lowered = PORT_RE.sub(":<port>", lowered)
    
    # 4. Temp & User Directories (must run before generic paths)
    lowered = TMP_DIR_RE.sub("<tmp_dir>", lowered)
    lowered = USER_DIR_RE.sub("<user_path>", lowered)
    
    # 5. Generic Paths
    lowered = ABS_PATH_RE.sub("<path>", lowered)
    
    # 6. Hex & Digits
    lowered = HEX_RE.sub("<hex>", lowered)
    lowered = DIGIT_RE.sub("<n>", lowered)
    
    # 7. Non-word characters cleanup (allow < and > for placeholders)
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

#task 07
DIFF_HUNK_RE = re.compile(r"^@@.*$")
DIFF_SYMBOL_RE = re.compile(
    r"^\s*(?:def|class|async\s+def|function|func|fn)\s+([A-Za-z_][A-Za-z0-9_]*)"
)

def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

def normalize_diff(diff: str) -> str:
    lines: list[str] = []
    for raw_line in diff.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("index "):
            continue
        if DIFF_HUNK_RE.match(line):
            lines.append("@@")
            continue
        if line[:1] in ("+", "-"):
            marker = line[:1]
            content = normalize_text(line[1:])
            if content:
                lines.append(marker + content)
        else:
            content = normalize_text(line)
            if content:
                lines.append(content)
    return "\n".join(lines)

def reverse_normalized_diff(normalized: str) -> str:
    lines: list[str] = []
    for line in normalized.splitlines():
        if line[:1] == "+":
            lines.append("-" + line[1:])
        elif line[:1] == "-":
            lines.append("+" + line[1:])
        else:
            lines.append(line)
    return "\n".join(lines)

def count_diff_lines(diff: str) -> tuple[int, int]:
    added = removed = 0
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed

def extract_diff_symbols(diff: str) -> list[str]:
    symbols: set[str] = set()
    for line in diff.splitlines():
        if line[:1] in ("+", "-"):
            match = DIFF_SYMBOL_RE.search(line[1:])
            if match:
                symbols.add(match.group(1))
    return sorted(symbols)

class LoopDetector:
    def __init__(self, settings: WatchdogSettings) -> None:
        self.settings = settings

    def fingerprint(self, kind: EventKind, summary: str, files: Iterable[str]) -> str:
        return normalize_text(f"{kind.value} {summarize_signature(summary, files)}")

    def error_signature(self, event: WatchdogEvent) -> str:
        source = event.metadata.get("error") or event.summary
        return normalize_text(str(source))
    
    def extract_test_failure(self, event: WatchdogEvent) -> TestFailureIdentity:
        meta = event.metadata
        stacktrace = str(meta.get("stacktrace") or meta.get("error") or event.summary or "")
        return TestFailureIdentity(
            framework=str(meta.get("framework", "")),
            suite=str(meta.get("suite", "")),
            test_id=str(meta.get("test_id", "")),
            command=str(meta.get("command", "")),
            exit_code=meta.get("exit_code"),
            failure_type=str(meta.get("failure_type", "")),
            stacktrace_signature=normalize_text(stacktrace),
        )
        
    def extract_diff_fingerprint(self, event: WatchdogEvent) -> GitDiffFingerprint:
        meta = event.metadata
        raw_diff = str(meta.get("diff", ""))

        lines_added = meta.get("lines_added")
        lines_removed = meta.get("lines_removed")
        if lines_added is None or lines_removed is None:
            counted_added, counted_removed = count_diff_lines(raw_diff)
            lines_added = counted_added if lines_added is None else lines_added
            lines_removed = counted_removed if lines_removed is None else lines_removed

        normalized = normalize_diff(raw_diff)
        return GitDiffFingerprint(
            diff_hash=hash_text(raw_diff),
            normalized_diff_hash=hash_text(normalized),
            reversed_hash=hash_text(reverse_normalized_diff(normalized)),
            files=sorted(set(event.files)),
            symbols=extract_diff_symbols(raw_diff),
            lines_added=int(lines_added),
            lines_removed=int(lines_removed),
        )
        
    def build_strategy_fingerprint(self, events: list[WatchdogEvent]) -> str:
        """Build a composite strategy fingerprint from a set of events."""
        parts: list[str] = []

        # Request text (the agent's stated goal)
        requests = [e for e in events if e.kind == EventKind.AGENT_REQUEST]
        if requests:
            parts.append(f"req:{normalize_text(requests[-1].summary)}")

        # Files touched
        files: set[str] = set()
        for e in events:
            if e.files:
                files.update(e.files)
        if files:
            parts.append(f"files:{','.join(sorted(files))}")

        # Error signatures encountered
        errors: set[str] = set()
        for e in events:
            if e.error_signature:
                errors.add(e.error_signature)
        if errors:
            parts.append(f"errors:{','.join(sorted(errors))}")

        # Diff fingerprints applied
        diffs: set[str] = set()
        for e in events:
            if e.git_diff and e.git_diff.normalized_diff_hash:
                diffs.add(e.git_diff.normalized_diff_hash)
        if diffs:
            parts.append(f"diffs:{','.join(sorted(diffs))}")

        return "|".join(parts)

    def strategy_similarity(self, left: str, right: str) -> float:
        """Calculate similarity between two strategy fingerprints."""
        if not left and not right:
            return 1.0
        if not left or not right:
            return 0.0
        return max(
            jaccard_similarity(left, right),
            sequence_similarity(left, right),
        )
        
    def extract_git_diff_fingerprint(self, event: WatchdogEvent) -> GitDiffFingerprint:
        meta = event.metadata
        raw_diff = str(meta.get("diff", ""))
        files = list(meta.get("files", event.files) or [])

        # Compute raw hash
        diff_hash = hashlib.sha256(raw_diff.encode("utf-8")).hexdigest()[:16] if raw_diff else ""

        # Normalize diff: strip index hashes, hunk line numbers, file paths
        pre_norm = DIFF_INDEX_RE.sub("", raw_diff)
        pre_norm = DIFF_HUNK_RE.sub("@@", pre_norm)
        pre_norm = DIFF_PATH_RE.sub("", pre_norm)

        # We must preserve '+' and '-' markers to detect reversions!
        norm_lines = []
        rev_lines = []
        for line in pre_norm.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                # Normalize the content, but keep the '+'
                norm_lines.append("+ " + normalize_text(line[1:]))
                rev_lines.append("- " + normalize_text(line[1:]))
            elif line.startswith("-"):
                # Normalize the content, but keep the '-'
                norm_lines.append("- " + normalize_text(line[1:]))
                rev_lines.append("+ " + normalize_text(line[1:]))
            else:
                norm_lines.append("  " + normalize_text(line))
                rev_lines.append("  " + normalize_text(line))
        
        normalized = "\n".join(norm_lines)
        normalized_diff_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16] if normalized else ""
        
        reversed_diff = "\n".join(rev_lines)
        reversed_hash = hashlib.sha256(reversed_diff.encode("utf-8")).hexdigest()[:16] if reversed_diff else ""

        # Extract symbols touched
        symbols = list(set(DIFF_SYMBOL_RE.findall(raw_diff)))

        # Count added/removed lines
        lines_added = sum(1 for line in raw_diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
        lines_removed = sum(1 for line in raw_diff.splitlines() if line.startswith("-") and not line.startswith("---"))

        return GitDiffFingerprint(
            diff_hash=diff_hash,
            normalized_diff_hash=normalized_diff_hash,
            reversed_hash=reversed_hash,
            files=files,
            symbols=symbols,
            lines_added=lines_added,
            lines_removed=lines_removed,
        )

    def evaluate(self, events: list[WatchdogEvent]) -> DetectorDecision:
        recent = events[-self.settings.recent_window :]
        if len(recent) < 4:
            return DetectorDecision()

        score = 0.0
        reasons: list[str] = []
        repeated_files: list[str] = []
        repeated_errors: list[str] = []
        triggering_event_ids: list[str] = []
        progress_score = 0.0
        progress_signals: list[str] = []
        unique_strategy_count = 0  # Clean up the ugly 'in locals()' check from Task 10

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
        for left, right in zip(request_events, request_events[1:], strict=False):
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
                f"Agent retried highly similar requests "
                f"{similar_request_pairs + 1} times in the recent window."
            )

        # TASK-08: File Cluster Similarity
        file_sets = [tuple(sorted(set(event.files))) for event in file_events if event.files]
        
        if file_sets:
            # Greedy clustering based on Jaccard similarity of file sets
            clusters: list[list[tuple[str, ...]]] = []
            CLUSTER_SIMILARITY_THRESHOLD = 0.6
            
            for fset in file_sets:
                assigned = False
                for cluster in clusters:
                    representative = cluster[0]
                    # Calculate Jaccard similarity between the two sets
                    intersect = len(set(representative) & set(fset))
                    union = len(set(representative) | set(fset))
                    sim = intersect / union if union > 0 else 1.0
                    
                    if sim >= CLUSTER_SIMILARITY_THRESHOLD:
                        cluster.append(fset)
                        assigned = True
                        break
                if not assigned:
                    clusters.append([fset])
                    
            # Find the cluster with the most events
            largest_cluster = max(clusters, key=len)
            file_group_count = len(largest_cluster)
            
            if file_group_count >= self.settings.file_repeat_threshold:
                score += self.settings.repeated_file_weight
                
                # The "core" files are the ones present in ALL sets of this cluster
                core_files = set(largest_cluster[0])
                for fset in largest_cluster[1:]:
                    core_files &= set(fset)
                    
                # Fallback: if intersection is somehow empty, use union
                if not core_files:
                    for fset in largest_cluster:
                        core_files |= set(fset)
                        
                repeated_files = sorted(list(core_files))
                reasons.append(
                    f"A similar file cluster (overlapping files) was touched {file_group_count} times "
                    f"without a clear recovery signal."
                )
                triggering_event_ids.extend(
                    event.event_id
                    for event in file_events
                    if event.files and tuple(sorted(set(event.files))) in largest_cluster
                )
                
        # TASK-09: Strategy Similarity between attempts
        # Split events into "attempts" by AGENT_REQUEST boundaries
        attempts: list[list[WatchdogEvent]] = []
        current_attempt: list[WatchdogEvent] = []
        for event in recent:
            if event.kind == EventKind.AGENT_REQUEST and current_attempt:
                attempts.append(current_attempt)
                current_attempt = [event]
            else:
                current_attempt.append(event)
        if current_attempt:
            attempts.append(current_attempt)

        # Compare consecutive strategy fingerprints
        if len(attempts) >= 2:
            strategy_fps = [self.build_strategy_fingerprint(a) for a in attempts]
            # TASK-10: Strategy Diversity signal
            unique_strategy_count = len(set(strategy_fps))
            similar_strategy_pairs = 0
            for left_fp, right_fp in zip(strategy_fps, strategy_fps[1:]):
                sim = self.strategy_similarity(left_fp, right_fp)
                if sim >= self.settings.strategy_similarity_threshold:
                    similar_strategy_pairs += 1

            if similar_strategy_pairs >= 2:
                score += self.settings.repeated_strategy_weight
                reasons.append(
                    f"The agent repeated a highly similar strategy "
                    f"{similar_strategy_pairs + 1} times consecutively."
                )
                # Add triggering events from the repeated attempts
                for i, attempt in enumerate(attempts):
                    if i < len(strategy_fps) - 1:
                        sim = self.strategy_similarity(strategy_fps[i], strategy_fps[i + 1])
                        if sim >= self.settings.strategy_similarity_threshold:
                            triggering_event_ids.extend(
                                e.event_id for e in attempt
                                if e.kind == EventKind.AGENT_REQUEST
                            )
            else:
                # If strategies are not highly similar, check if they are diverse
                if unique_strategy_count >= 3:
                    score += self.settings.strategy_diversity_weight
                    reasons.append(
                        f"Agent is exploring {unique_strategy_count} diverse strategies (healthy behavior)."
                    )

        error_counter = Counter(event.error_signature for event in error_events)
        recurrent_errors = [
            signature for signature, count in error_counter.items() if count >= 2 and signature
        ]
        if recurrent_errors:
            score += self.settings.repeated_error_weight
            repeated_errors = recurrent_errors[:3]
            reasons.append(
                "The session is repeating the same failure signature after multiple attempts."
            )
            triggering_event_ids.extend(
                event.event_id
                for event in error_events
                if event.error_signature in recurrent_errors
            )
                    # TASK-06: Repeated identical test failure detection
        test_failure_events = [
            event
            for event in recent
            if event.kind == EventKind.TEST_FAILURE and event.test_failure is not None
        ]
        if test_failure_events:
            tf_counter = Counter(
                event.test_failure.identity() for event in test_failure_events
            )
            repeated_tf = [
                identity for identity, count in tf_counter.items() if count >= 2 and identity
            ]
            if repeated_tf:
                score += self.settings.repeated_test_failure_weight
                reasons.append(
                    f"The same test failure repeated {max(tf_counter.values())} times."
                )
                triggering_event_ids.extend(
                    event.event_id
                    for event in test_failure_events
                    if event.test_failure.identity() in repeated_tf
                )
                
        # TASK-07: Repeated / reverted patch detection
        diff_events = [
            event for event in recent
            if event.kind in {EventKind.GIT_DIFF, EventKind.PATCH_APPLY} 
            and event.git_diff is not None
            and event.git_diff.normalized_diff_hash
        ]
        if diff_events:
            # 1. Identical patches (raw hash matches)
            diff_hash_counter = Counter(
                e.git_diff.diff_hash for e in diff_events if e.git_diff.diff_hash
            )
            repeated_diffs = [h for h, c in diff_hash_counter.items() if c >= 2]
            if repeated_diffs:
                score += self.settings.repeated_patch_weight
                reasons.append(
                    f"The exact same patch was applied {max(diff_hash_counter.values())} times."
                )
                triggering_event_ids.extend(
                    e.event_id for e in diff_events
                    if e.git_diff.diff_hash in repeated_diffs
                )

            # 2. Near-identical patches (normalized hash matches, raw hash differs)
            norm_counter = Counter(
                e.git_diff.normalized_diff_hash for e in diff_events 
                if e.git_diff.normalized_diff_hash and e.git_diff.diff_hash not in repeated_diffs
            )
            near_identical = [h for h, c in norm_counter.items() if c >= 2]
            if near_identical:
                score += self.settings.repeated_patch_weight * 0.7
                reasons.append(
                    "Near-identical patches were applied repeatedly with minor variations."
                )
                triggering_event_ids.extend(
                    e.event_id for e in diff_events
                    if e.git_diff.normalized_diff_hash in near_identical and e.git_diff.diff_hash not in repeated_diffs
                )

            # 3. Revert detection: A patch was applied, and then its inverse was applied
            seen_hashes: set[str] = set()
            revert_detected = False
            for event in diff_events:
                fp = event.git_diff
                if fp.normalized_diff_hash in seen_hashes:
                    continue
                seen_hashes.add(fp.normalized_diff_hash)
                for other in diff_events:
                    if (
                        other.event_id != event.event_id
                        and other.git_diff
                        and other.git_diff.normalized_diff_hash == fp.reversed_hash
                    ):
                        revert_detected = True
                        triggering_event_ids.extend([event.event_id, other.event_id])
                        break
                if revert_detected:
                    break
            if revert_detected:
                score += self.settings.reverted_patch_weight
                reasons.append("A patch was applied and then reverted within the window.")

        # TASK-11: A->B->A State Oscillation Detection
        state_sequence: list[tuple[str, str]] = []
        for event in recent:
            if event.kind in {EventKind.GIT_DIFF, EventKind.PATCH_APPLY} and event.git_diff and event.git_diff.normalized_diff_hash:
                state_sequence.append(("diff", event.git_diff.normalized_diff_hash))
            elif event.kind in {EventKind.TEST_FAILURE, EventKind.TOOL_ERROR} and event.error_signature:
                state_sequence.append(("error", event.error_signature))
            elif event.kind == EventKind.FILE_EDIT and event.files:
                files_sig = hash_text(",".join(sorted(event.files)))
                state_sequence.append(("files", files_sig))

        aba_cycles = 0
        if len(state_sequence) >= 3:
            for i in range(len(state_sequence) - 2):
                s_a, s_b, s_c = state_sequence[i], state_sequence[i+1], state_sequence[i+2]
                # A -> B -> A means first and third are same, middle is different
                if s_a == s_c and s_a != s_b:
                    aba_cycles += 1

        if aba_cycles >= 2:
            score += self.settings.state_oscillation_weight
            reasons.append(
                f"Detected {aba_cycles} A->B->A state oscillations (e.g. apply, revert/fail, reapply)."
            )
            # Add triggering events involved in the oscillations
            for event in recent:
                if (
                    (event.git_diff and event.git_diff.normalized_diff_hash)
                    or event.error_signature
                    or (event.kind == EventKind.FILE_EDIT and event.files)
                ):
                    triggering_event_ids.append(event.event_id)

        if not success_events and len(error_events) >= 2 and len(request_events) >= 3:
            score += self.settings.no_progress_weight
            reasons.append(
                "Spend is growing without a passing test or a recovery event in the recent window."
            )

        paused = score >= self.settings.pause_score_threshold and len(reasons) >= 2
        recommendation = (
            "Pause the agent, inspect the repeated file cluster, "
            "and require a human-approved plan before resuming."
            if paused
            else ""
        )
        
        # TASK-12: Progress Engine
        for event in recent:
            if event.kind.is_progress:
                progress_score += self.settings.progress_success_weight
                progress_signals.append(f"success:{event.kind.value}")

        unique_errors = {e.error_signature for e in error_events if e.error_signature}
        if len(unique_errors) >= 2:
            progress_score += self.settings.progress_error_change_weight
            progress_signals.append(f"errors_changed:{len(unique_errors)}_unique")
        
        return DetectorDecision(
            paused=paused,
            score=round(score, 2),
            progress_score=round(progress_score, 2),
            progress_signals=progress_signals,
            reasons=reasons,
            repeated_files=repeated_files,
            repeated_errors=repeated_errors,
            triggering_event_ids=list(dict.fromkeys(triggering_event_ids)),
            recommendation=recommendation,
            unique_strategies=unique_strategy_count,
        )