"""Deterministic grading logic for submitted code review findings."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from typing import Iterable

from code_review_env.models import FindingAssessment, ReviewFinding, ReviewScorecard

from .task_types import ReferenceFinding, ReviewTask

SEVERITY_WEIGHTS = {
    "low": 0.25,
    "medium": 0.5,
    "high": 0.8,
    "critical": 1.0,
}

CATEGORY_ALIASES = {
    "broken_access_control": {"broken_access_control", "authz", "authorization", "idor", "tenant_isolation"},
    "sql_injection": {"sql_injection", "injection", "unsafe_sql", "raw_sql"},
    "path_traversal": {"path_traversal", "directory_traversal", "file_disclosure"},
    "ssrf": {"ssrf", "server_side_request_forgery", "untrusted_url_fetch"},
    "authentication": {"authentication", "jwt", "session_validation", "aud_claim", "expired_token"},
    "race_condition": {"race_condition", "concurrency", "double_spend", "atomicity"},
    "xss": {"xss", "cross_site_scripting", "unsafe_html"},
}
MIN_OPEN_SCORE = 0.0001
MAX_OPEN_SCORE = 0.9999


@dataclass(frozen=True)
class MatchBreakdown:
    score: float
    line_score: float
    category_score: float
    severity_score: float
    semantic_score: float


def clamp_open_score(value: float) -> float:
    return min(MAX_OPEN_SCORE, max(MIN_OPEN_SCORE, value))


def normalize_text(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else " " for ch in value).strip()


def token_set(values: Iterable[str]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        for token in normalize_text(value).split():
            if len(token) >= 3:
                tokens.add(token)
    return tokens


def normalize_path(path: str) -> str:
    return path.strip().lower().replace("\\", "/")


def category_matches(submitted: str, reference: ReferenceFinding) -> float:
    submitted_normalized = normalize_text(submitted).replace(" ", "_")
    canonical_aliases = set(reference.aliases)
    canonical_aliases.add(reference.category)
    for alias_group in CATEGORY_ALIASES.values():
        if reference.category in alias_group:
            canonical_aliases.update(alias_group)

    if submitted_normalized in canonical_aliases:
        return 1.0

    if submitted_normalized and any(
        submitted_normalized in alias or alias in submitted_normalized for alias in canonical_aliases
    ):
        return 0.65

    return 0.0


def severity_matches(submitted: str, expected: str) -> float:
    order = ["low", "medium", "high", "critical"]
    try:
        delta = abs(order.index(submitted) - order.index(expected))
    except ValueError:
        return 0.0

    if delta == 0:
        return 1.0
    if delta == 1:
        return 0.75
    if delta == 2:
        return 0.35
    return 0.0


def line_alignment_score(submitted: ReviewFinding, reference: ReferenceFinding) -> float:
    start = submitted.line_start
    end = submitted.line_end or submitted.line_start
    ref_start = reference.line_start
    ref_end = reference.line_end

    overlap = max(0, min(end, ref_end) - max(start, ref_start) + 1)
    if overlap > 0:
        return 1.0

    distance = min(abs(start - ref_end), abs(end - ref_start))
    if distance <= 2:
        return 0.85
    if distance <= 5:
        return 0.6
    if distance <= 10:
        return 0.35
    return 0.0


def semantic_score(submitted: ReviewFinding, reference: ReferenceFinding) -> float:
    submitted_tokens = token_set([submitted.title, submitted.explanation])
    reference_tokens = token_set(
        [
            reference.title,
            reference.summary,
            *reference.title_keywords,
            *reference.explanation_keywords,
        ]
    )
    if not reference_tokens:
        return 0.0

    coverage = len(submitted_tokens & reference_tokens) / len(reference_tokens)
    precision = len(submitted_tokens & reference_tokens) / max(len(submitted_tokens), 1)
    return min(1.0, 0.7 * coverage + 0.3 * precision)


def evaluate_match(submitted: ReviewFinding, reference: ReferenceFinding) -> MatchBreakdown:
    if normalize_path(submitted.file_path) != normalize_path(reference.file_path):
        return MatchBreakdown(0.0, 0.0, 0.0, 0.0, 0.0)

    line_score = line_alignment_score(submitted, reference)
    category_score = category_matches(submitted.category, reference)
    severity_score = severity_matches(submitted.severity, reference.severity)
    semantic = semantic_score(submitted, reference)

    if line_score == 0.0 and semantic < 0.3:
        return MatchBreakdown(0.0, line_score, category_score, severity_score, semantic)

    total = (
        0.35 * line_score
        + 0.20 * category_score
        + 0.15 * severity_score
        + 0.30 * semantic
    )
    return MatchBreakdown(min(1.0, total), line_score, category_score, severity_score, semantic)


def duplicate_count(findings: list[ReviewFinding]) -> int:
    duplicates = 0
    for left, right in combinations(findings, 2):
        same_file = normalize_path(left.file_path) == normalize_path(right.file_path)
        close_lines = abs(left.line_start - right.line_start) <= 2
        shared_tokens = token_set([left.title, left.explanation]) & token_set(
            [right.title, right.explanation]
        )
        if same_file and close_lines and len(shared_tokens) >= 3:
            duplicates += 1
    return duplicates


def grade_band(score: float) -> str:
    if score >= 0.9:
        return "excellent"
    if score >= 0.75:
        return "strong"
    if score >= 0.55:
        return "mixed"
    if score >= 0.3:
        return "weak"
    return "poor"


def optimal_assignment(
    findings: list[ReviewFinding], references: list[ReferenceFinding]
) -> list[tuple[int, int, MatchBreakdown]]:
    if not findings or not references:
        return []

    matrix = [
        [evaluate_match(finding, reference) for reference in references]
        for finding in findings
    ]

    @lru_cache(maxsize=None)
    def solve(index: int, used_mask: int) -> tuple[float, tuple[tuple[int, int], ...]]:
        if index >= len(findings):
            return 0.0, ()

        best_score, best_pairs = solve(index + 1, used_mask)
        for ref_index, breakdown in enumerate(matrix[index]):
            if breakdown.score < 0.45 or (used_mask & (1 << ref_index)):
                continue
            candidate_score, candidate_pairs = solve(index + 1, used_mask | (1 << ref_index))
            weighted = breakdown.score * SEVERITY_WEIGHTS[references[ref_index].severity]
            candidate_total = candidate_score + weighted
            if candidate_total > best_score:
                best_score = candidate_total
                best_pairs = ((index, ref_index),) + candidate_pairs
        return best_score, best_pairs

    _, pairs = solve(0, 0)
    return [(i, j, matrix[i][j]) for i, j in pairs]


def grade_submission(
    task: ReviewTask,
    findings: list[ReviewFinding],
    steps_used: int,
) -> ReviewScorecard:
    references = task.gold_findings
    duplicate_penalty = duplicate_count(findings) * 0.06
    efficiency_score = max(0.0, 1.0 - max(0, steps_used - 3) / max(task.max_steps - 2, 1))

    if not references:
        false_positive_penalty = min(1.0, 0.32 * len(findings))
        overall = max(0.0, 1.0 - false_positive_penalty - duplicate_penalty)
        overall = clamp_open_score(overall)
        summary = (
            "Correctly identified that the refactor is clean."
            if not findings
            else "This task is intentionally clean; submitted findings are false positives."
        )
        assessments = [
            FindingAssessment(
                finding_index=index,
                matched=False,
                notes="No rubric issue matches this submission on the clean refactor task.",
            )
            for index, _finding in enumerate(findings)
        ]
        return ReviewScorecard(
            overall_score=round(overall, 4),
            coverage_score=1.0,
            precision_score=0.0 if findings else 1.0,
            efficiency_score=round(efficiency_score, 4),
            false_positive_penalty=round(false_positive_penalty, 4),
            duplicate_penalty=round(duplicate_penalty, 4),
            missed_severity_penalty=0.0,
            matched_findings=0,
            expected_findings=0,
            submitted_findings=len(findings),
            grade_band=grade_band(overall),
            summary=summary,
            assessments=assessments,
            missed_reference_ids=[],
        )

    assignments = optimal_assignment(findings, references)
    assessment_by_index: dict[int, FindingAssessment] = {}
    matched_reference_ids: set[str] = set()
    matched_weight = 0.0

    for finding_index, reference_index, breakdown in assignments:
        reference = references[reference_index]
        matched_reference_ids.add(reference.id)
        weight = SEVERITY_WEIGHTS[reference.severity]
        matched_weight += weight * breakdown.score
        assessment_by_index[finding_index] = FindingAssessment(
            finding_index=finding_index,
            matched=True,
            matched_reference_id=reference.id,
            score=round(breakdown.score, 4),
            line_score=round(breakdown.line_score, 4),
            category_score=round(breakdown.category_score, 4),
            severity_score=round(breakdown.severity_score, 4),
            semantic_score=round(breakdown.semantic_score, 4),
            notes=f"Matched rubric item '{reference.id}'",
        )

    unmatched_refs = [reference for reference in references if reference.id not in matched_reference_ids]
    unmatched_submissions = [index for index in range(len(findings)) if index not in assessment_by_index]

    for index in unmatched_submissions:
        assessment_by_index[index] = FindingAssessment(
            finding_index=index,
            matched=False,
            notes="No rubric issue matched this submission strongly enough.",
        )

    total_weight = sum(SEVERITY_WEIGHTS[reference.severity] for reference in references)
    missed_weight = sum(SEVERITY_WEIGHTS[reference.severity] for reference in unmatched_refs)
    coverage_score = matched_weight / total_weight if total_weight else 1.0
    false_positive_penalty = 0.12 * len(unmatched_submissions)
    precision_score = matched_weight / max(
        matched_weight + false_positive_penalty + (0.04 * duplicate_penalty),
        1e-6,
    )
    missed_penalty = missed_weight / total_weight if total_weight else 0.0

    overall = (
        0.68 * coverage_score
        + 0.18 * precision_score
        + 0.14 * efficiency_score
        - 0.18 * false_positive_penalty
        - 0.10 * duplicate_penalty
        - 0.14 * missed_penalty
    )
    overall = max(0.0, min(1.0, overall))
    overall = clamp_open_score(overall)

    summary = (
        f"Matched {len(assignments)} of {len(references)} reference findings. "
        f"Missed {len(unmatched_refs)} expected issue(s) and flagged {len(unmatched_submissions)} false positive(s)."
    )

    ordered_assessments = [assessment_by_index[index] for index in range(len(findings))]
    return ReviewScorecard(
        overall_score=round(overall, 4),
        coverage_score=round(min(1.0, coverage_score), 4),
        precision_score=round(min(1.0, precision_score), 4),
        efficiency_score=round(efficiency_score, 4),
        false_positive_penalty=round(false_positive_penalty, 4),
        duplicate_penalty=round(duplicate_penalty, 4),
        missed_severity_penalty=round(missed_penalty, 4),
        matched_findings=len(assignments),
        expected_findings=len(references),
        submitted_findings=len(findings),
        grade_band=grade_band(overall),
        summary=summary,
        assessments=ordered_assessments,
        missed_reference_ids=[reference.id for reference in unmatched_refs],
    )
