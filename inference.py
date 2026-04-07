"""Minimal end-to-end episode runner for the deployed code review environment."""

from __future__ import annotations

import asyncio
import os
from typing import Any

try:
    from code_review_env import CodeReviewAction, CodeReviewEnv, ReviewFinding
except ImportError:  # pragma: no cover
    from client import CodeReviewEnv
    from models import CodeReviewAction, ReviewFinding


DEFAULT_BASE_URL = "https://rohan556-openenv-code-review-arena.hf.space"


def emit_block(tag: str, **fields: Any) -> None:
    """Print a single structured stdout line for the hackathon validator."""

    serialized = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"[{tag}] {serialized}", flush=True)


async def main() -> None:
    base_url = os.getenv("CODE_REVIEW_ENV_URL", DEFAULT_BASE_URL)

    async with CodeReviewEnv(base_url=base_url) as env:
        result = await env.reset(task_id="sql_injection_report_filters")
        emit_block(
            "START",
            task=result.observation.task_id,
            difficulty=result.observation.difficulty,
            repo=result.observation.repo_name,
        )

        inspection = await env.step(
            CodeReviewAction(
                action_type="inspect_file",
                file_path="analytics/reporting.py",
                view_mode="full",
                start_line=1,
                end_line=80,
            )
        )
        emit_block(
            "STEP",
            step=1,
            action="inspect_file",
            reward=inspection.reward,
            done=inspection.done,
            phase=inspection.observation.phase,
        )

        graded = await env.step(
            CodeReviewAction(
                action_type="submit_review",
                findings=[
                    ReviewFinding(
                        file_path="analytics/reporting.py",
                        line_start=9,
                        line_end=15,
                        severity="critical",
                        category="sql_injection",
                        title="Unsafe string interpolation in SQL report query",
                        explanation=(
                            "customer_id and period are interpolated directly into raw SQL "
                            "instead of being passed as bound parameters, so an attacker can "
                            "inject arbitrary predicates or SQL fragments."
                        ),
                        confidence=0.98,
                    )
                ],
            )
        )
        emit_block(
            "STEP",
            step=2,
            action="submit_review",
            reward=graded.reward,
            done=graded.done,
            phase=graded.observation.phase,
        )

        scorecard = graded.observation.scorecard
        if scorecard is None:
            raise RuntimeError("Expected a scorecard after submit_review")
        emit_block(
            "END",
            task=result.observation.task_id,
            score=scorecard.overall_score,
            steps=2,
            grade=scorecard.grade_band,
            matched=scorecard.matched_findings,
            expected=scorecard.expected_findings,
        )


if __name__ == "__main__":
    asyncio.run(main())
