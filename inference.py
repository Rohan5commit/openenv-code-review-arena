"""Minimal end-to-end episode runner for the deployed code review environment."""

from __future__ import annotations

import asyncio
import os

try:
    from code_review_env import CodeReviewAction, CodeReviewEnv, ReviewFinding
except ImportError:  # pragma: no cover
    from client import CodeReviewEnv
    from models import CodeReviewAction, ReviewFinding


DEFAULT_BASE_URL = "https://rohan556-openenv-code-review-arena.hf.space"


async def main() -> None:
    base_url = os.getenv("CODE_REVIEW_ENV_URL", DEFAULT_BASE_URL)

    async with CodeReviewEnv(base_url=base_url) as env:
        result = await env.reset(task_id="sql_injection_report_filters")
        print(f"task={result.observation.task_id}")
        print(f"pr={result.observation.pr_title}")

        await env.step(
            CodeReviewAction(
                action_type="inspect_file",
                file_path="analytics/reporting.py",
                view_mode="full",
                start_line=1,
                end_line=80,
            )
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

        scorecard = graded.observation.scorecard
        print(f"done={graded.done}")
        if scorecard is None:
            raise RuntimeError("Expected a scorecard after submit_review")
        print(f"score={scorecard.overall_score}")
        print(f"grade_band={scorecard.grade_band}")
        print(scorecard.summary)


if __name__ == "__main__":
    asyncio.run(main())
