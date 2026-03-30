"""Internal task and rubric models used by the environment runtime."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from code_review_env.models import Severity


class TaskFile(BaseModel):
    """Visible file artifact included in a review task."""

    path: str
    language: str
    change_type: str
    added_lines: int = Field(default=0, ge=0)
    removed_lines: int = Field(default=0, ge=0)
    role: str = ""
    diff: str
    full_content: str


class ReferenceFinding(BaseModel):
    """Hidden rubric entry used for deterministic grading."""

    id: str
    file_path: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    severity: Severity
    category: str
    title: str
    summary: str
    title_keywords: list[str] = Field(default_factory=list)
    explanation_keywords: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)


class ReviewTask(BaseModel):
    """Complete PR review scenario."""

    id: str
    title: str
    difficulty: Literal["easy", "medium", "hard"]
    domain: str
    repo_name: str
    pr_title: str
    pr_description: str
    instructions: str
    ci_summary: str
    max_steps: int = Field(default=8, ge=1)
    changed_files: list[TaskFile]
    gold_findings: list[ReferenceFinding] = Field(default_factory=list)

