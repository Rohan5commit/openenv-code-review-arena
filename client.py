"""Typed OpenEnv client for the code review benchmark."""

from __future__ import annotations

from typing import Any

from openenv.core.env_client import EnvClient
from openenv.core.client_types import StepResult

try:
    from .models import (
        ChangedFileSummary,
        CodeReviewAction,
        CodeReviewObservation,
        CodeReviewState,
        ReviewScorecard,
        SearchHit,
    )
except ImportError:  # pragma: no cover
    from models import (
        ChangedFileSummary,
        CodeReviewAction,
        CodeReviewObservation,
        CodeReviewState,
        ReviewScorecard,
        SearchHit,
    )


class CodeReviewEnv(EnvClient[CodeReviewAction, CodeReviewObservation, CodeReviewState]):
    """Persistent WebSocket client for the code review environment."""

    def _step_payload(self, action: CodeReviewAction) -> dict[str, Any]:
        return action.model_dump(exclude_none=True)

    def _parse_result(self, payload: dict[str, Any]) -> StepResult[CodeReviewObservation]:
        obs_data = payload.get("observation", {})
        scorecard_data = obs_data.get("scorecard")
        observation = CodeReviewObservation(
            task_id=obs_data.get("task_id", ""),
            task_title=obs_data.get("task_title", ""),
            difficulty=obs_data.get("difficulty", ""),
            phase=obs_data.get("phase", "overview"),
            instructions=obs_data.get("instructions", ""),
            repo_name=obs_data.get("repo_name", ""),
            pr_title=obs_data.get("pr_title", ""),
            pr_description=obs_data.get("pr_description", ""),
            ci_summary=obs_data.get("ci_summary", ""),
            action_result=obs_data.get("action_result", ""),
            displayed_content=obs_data.get("displayed_content", ""),
            changed_files=[
                ChangedFileSummary.model_validate(item)
                for item in obs_data.get("changed_files", [])
            ],
            search_results=[
                SearchHit.model_validate(item) for item in obs_data.get("search_results", [])
            ],
            attempts_remaining=obs_data.get("attempts_remaining", 0),
            scorecard=(
                ReviewScorecard.model_validate(scorecard_data) if scorecard_data else None
            ),
            done=payload.get("done", False),
            reward=payload.get("reward"),
        )
        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: dict[str, Any]) -> CodeReviewState:
        return CodeReviewState.model_validate(payload)
