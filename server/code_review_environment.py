"""OpenEnv environment implementation for interactive PR review."""

from __future__ import annotations

import random
import uuid

from openenv.core.env_server.interfaces import Action, Environment, Observation

from code_review_env.models import (
    ChangedFileSummary,
    CodeReviewAction,
    CodeReviewObservation,
    CodeReviewState,
    SearchHit,
)

from .grader import grade_submission
from .task_store import TaskStore
from .task_types import ReviewTask, TaskFile


def render_numbered_excerpt(content: str, start_line: int, end_line: int) -> str:
    lines = content.splitlines()
    if not lines:
        return "(empty file)"

    start = max(1, start_line)
    end = min(len(lines), max(start, end_line))
    rendered = [
        f"{line_number:4d} | {lines[line_number - 1]}"
        for line_number in range(start, end + 1)
    ]
    return "\n".join(rendered)


def summarize_files(task: ReviewTask) -> list[ChangedFileSummary]:
    return [
        ChangedFileSummary(
            path=file.path,
            language=file.language,
            change_type=file.change_type,
            added_lines=file.added_lines,
            removed_lines=file.removed_lines,
            role=file.role,
        )
        for file in task.changed_files
    ]


class CodeReviewEnvironment(Environment):
    """Interactive environment for reviewing realistic pull requests."""

    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self):
        self._task_store = TaskStore()
        self._rng = random.Random()
        self._current_task: ReviewTask | None = None
        self._state = CodeReviewState()

    def reset(
        self,
        task_id: str | None = None,
        difficulty: str | None = None,
        seed: int | None = None,
    ) -> Observation:
        if seed is not None:
            self._rng.seed(seed)

        chosen_seed = seed if seed is not None else self._rng.randint(0, 10_000_000)
        self._current_task = self._task_store.choose(
            task_id=task_id,
            difficulty=difficulty,
            seed=chosen_seed,
        )
        task = self._current_task

        self._state = CodeReviewState(
            episode_id=str(uuid.uuid4()),
            step_count=0,
            task_id=task.id,
            task_title=task.title,
            difficulty=task.difficulty,
            inspected_files=[],
            search_queries=[],
            submitted=False,
            max_steps=task.max_steps,
            score=None,
        )

        overview = (
            f"Repository: {task.repo_name}\n"
            f"PR: {task.pr_title}\n"
            f"Description: {task.pr_description}\n"
            f"CI: {task.ci_summary}\n"
            f"Review budget: {task.max_steps} actions including final submission."
        )

        return self._base_observation(
            phase="overview",
            action_result="Task loaded. Inspect changed files and submit only concrete issues.",
            displayed_content=overview,
            reward=0.0,
            done=False,
        )

    def step(self, action: Action) -> Observation:
        if not isinstance(action, CodeReviewAction):
            raise ValueError(f"Expected CodeReviewAction, got {type(action)}")
        if self._current_task is None:
            raise RuntimeError("reset() must be called before step()")
        if self._state.submitted:
            raise RuntimeError("Episode already finished; call reset() for a new task")

        self._state.step_count += 1
        task = self._current_task

        if action.action_type == "list_files":
            content = self._format_file_index(task)
            observation = self._base_observation(
                phase="inspection",
                action_result="Listed changed files.",
                displayed_content=content,
                reward=-0.005,
                done=False,
            )
        elif action.action_type == "inspect_file":
            observation = self._inspect_file(task, action)
        elif action.action_type == "search_code":
            observation = self._search_code(task, action)
        elif action.action_type == "submit_review":
            observation = self._submit_review(task, action)
        else:
            observation = self._base_observation(
                phase="error",
                action_result=f"Unsupported action_type '{action.action_type}'.",
                displayed_content="Supported actions: list_files, inspect_file, search_code, submit_review",
                reward=-0.05,
                done=False,
            )

        if not observation.done and self._state.step_count >= self._state.max_steps:
            scorecard = grade_submission(task, [], self._state.step_count)
            self._state.submitted = True
            self._state.score = scorecard.overall_score
            return self._base_observation(
                phase="graded",
                action_result="Step budget exhausted before submission. Empty review graded automatically.",
                displayed_content="No findings were submitted before the episode ended.",
                reward=scorecard.overall_score,
                done=True,
                scorecard=scorecard,
            )

        return observation

    @property
    def state(self) -> CodeReviewState:
        return self._state

    def _get_file(self, path: str) -> TaskFile:
        assert self._current_task is not None
        normalized = path.strip().lower()
        for file in self._current_task.changed_files:
            if file.path.lower() == normalized:
                return file
        raise ValueError(f"Unknown file '{path}' for task '{self._current_task.id}'")

    def _inspect_file(self, task: ReviewTask, action: CodeReviewAction) -> CodeReviewObservation:
        file = self._get_file(action.file_path)
        if file.path not in self._state.inspected_files:
            self._state.inspected_files.append(file.path)

        if action.view_mode == "diff":
            content = file.diff
        else:
            content = render_numbered_excerpt(file.full_content, action.start_line, action.end_line)

        return self._base_observation(
            phase="inspection",
            action_result=f"Opened {file.path} ({action.view_mode} view).",
            displayed_content=content,
            reward=-0.01,
            done=False,
        )

    def _search_code(self, task: ReviewTask, action: CodeReviewAction) -> CodeReviewObservation:
        query = action.query.strip()
        if not query:
            return self._base_observation(
                phase="error",
                action_result="Search query cannot be empty.",
                displayed_content="Provide a non-empty query string.",
                reward=-0.03,
                done=False,
            )

        self._state.search_queries.append(query)
        results: list[SearchHit] = []
        lowered = query.lower()
        for file in task.changed_files:
            for line_number, line in enumerate(file.full_content.splitlines(), start=1):
                if lowered in line.lower():
                    results.append(
                        SearchHit(path=file.path, line_number=line_number, snippet=line.strip())
                    )
                if len(results) >= 8:
                    break
            if len(results) >= 8:
                break

        if results:
            content = "\n".join(
                f"{hit.path}:{hit.line_number}  {hit.snippet}" for hit in results
            )
            message = f"Found {len(results)} match(es) for '{query}'."
        else:
            content = f"No matches for '{query}' in changed files."
            message = f"No matches for '{query}'."

        return self._base_observation(
            phase="inspection",
            action_result=message,
            displayed_content=content,
            reward=-0.01,
            done=False,
            search_results=results,
        )

    def _submit_review(self, task: ReviewTask, action: CodeReviewAction) -> CodeReviewObservation:
        scorecard = grade_submission(task, action.findings, self._state.step_count)
        self._state.submitted = True
        self._state.score = scorecard.overall_score
        return self._base_observation(
            phase="graded",
            action_result=scorecard.summary,
            displayed_content=self._render_scorecard(scorecard),
            reward=scorecard.overall_score,
            done=True,
            scorecard=scorecard,
        )

    def _format_file_index(self, task: ReviewTask) -> str:
        lines = []
        for file in task.changed_files:
            lines.append(
                f"- {file.path} [{file.language}] +{file.added_lines}/-{file.removed_lines} role={file.role}"
            )
        return "\n".join(lines)

    def _render_scorecard(self, scorecard) -> str:
        lines = [
            f"overall_score={scorecard.overall_score}",
            f"coverage_score={scorecard.coverage_score}",
            f"precision_score={scorecard.precision_score}",
            f"efficiency_score={scorecard.efficiency_score}",
            f"grade_band={scorecard.grade_band}",
            scorecard.summary,
        ]
        for assessment in scorecard.assessments:
            lines.append(
                f"finding[{assessment.finding_index}] matched={assessment.matched} "
                f"score={assessment.score} ref={assessment.matched_reference_id or '-'} "
                f"notes={assessment.notes}"
            )
        if scorecard.missed_reference_ids:
            lines.append(f"missed={', '.join(scorecard.missed_reference_ids)}")
        return "\n".join(lines)

    def _base_observation(
        self,
        *,
        phase: str,
        action_result: str,
        displayed_content: str,
        reward: float,
        done: bool,
        search_results: list[SearchHit] | None = None,
        scorecard=None,
    ) -> CodeReviewObservation:
        assert self._current_task is not None
        task = self._current_task
        attempts_remaining = max(0, self._state.max_steps - self._state.step_count)
        return CodeReviewObservation(
            task_id=task.id,
            task_title=task.title,
            difficulty=task.difficulty,
            phase=phase,
            instructions=task.instructions,
            repo_name=task.repo_name,
            pr_title=task.pr_title,
            pr_description=task.pr_description,
            ci_summary=task.ci_summary,
            action_result=action_result,
            displayed_content=displayed_content,
            changed_files=summarize_files(task),
            search_results=search_results or [],
            attempts_remaining=attempts_remaining,
            scorecard=scorecard,
            reward=reward,
            done=done,
        )
