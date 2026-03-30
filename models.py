"""Public models for the OpenEnv code review benchmark."""

from __future__ import annotations

from typing import Literal

from openenv.core.env_server.types import Action, Observation, State
from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]
ActionType = Literal["list_files", "inspect_file", "search_code", "submit_review"]
ViewMode = Literal["diff", "full"]


class ChangedFileSummary(BaseModel):
    """High-level summary of a changed file in the PR."""

    path: str
    language: str
    change_type: str
    added_lines: int = Field(default=0, ge=0)
    removed_lines: int = Field(default=0, ge=0)
    role: str = ""


class SearchHit(BaseModel):
    """Single search result within a changed file."""

    path: str
    line_number: int = Field(ge=1)
    snippet: str
    match_type: str = "content"


class ReviewFinding(BaseModel):
    """Structured issue submitted by the reviewing agent."""

    file_path: str
    line_start: int = Field(ge=1)
    line_end: int | None = Field(default=None, ge=1)
    severity: Severity
    category: str
    title: str = Field(min_length=3)
    explanation: str = Field(min_length=10)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class FindingAssessment(BaseModel):
    """Per-finding grading feedback."""

    finding_index: int = Field(ge=0)
    matched: bool = False
    matched_reference_id: str = ""
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    line_score: float = Field(default=0.0, ge=0.0, le=1.0)
    category_score: float = Field(default=0.0, ge=0.0, le=1.0)
    severity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    semantic_score: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: str = ""


class ReviewScorecard(BaseModel):
    """Detailed grading output for a submitted review."""

    overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    coverage_score: float = Field(default=0.0, ge=0.0, le=1.0)
    precision_score: float = Field(default=0.0, ge=0.0, le=1.0)
    efficiency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    false_positive_penalty: float = Field(default=0.0, ge=0.0)
    duplicate_penalty: float = Field(default=0.0, ge=0.0)
    missed_severity_penalty: float = Field(default=0.0, ge=0.0)
    matched_findings: int = Field(default=0, ge=0)
    expected_findings: int = Field(default=0, ge=0)
    submitted_findings: int = Field(default=0, ge=0)
    grade_band: str = ""
    summary: str = ""
    assessments: list[FindingAssessment] = Field(default_factory=list)
    missed_reference_ids: list[str] = Field(default_factory=list)


class CodeReviewAction(Action):
    """Action for inspecting or grading a PR review task."""

    action_type: ActionType = "list_files"
    file_path: str = ""
    view_mode: ViewMode = "diff"
    start_line: int = Field(default=1, ge=1)
    end_line: int = Field(default=160, ge=1)
    query: str = ""
    findings: list[ReviewFinding] = Field(default_factory=list)


class CodeReviewObservation(Observation):
    """Observation returned after each interaction with the environment."""

    task_id: str = ""
    task_title: str = ""
    difficulty: str = ""
    phase: str = "overview"
    instructions: str = ""
    repo_name: str = ""
    pr_title: str = ""
    pr_description: str = ""
    ci_summary: str = ""
    action_result: str = ""
    displayed_content: str = ""
    changed_files: list[ChangedFileSummary] = Field(default_factory=list)
    search_results: list[SearchHit] = Field(default_factory=list)
    attempts_remaining: int = Field(default=0, ge=0)
    scorecard: ReviewScorecard | None = None


class CodeReviewState(State):
    """Server-side state for a review episode."""

    task_id: str = ""
    task_title: str = ""
    difficulty: str = ""
    inspected_files: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    submitted: bool = False
    max_steps: int = Field(default=8, ge=1)
    score: float | None = None

