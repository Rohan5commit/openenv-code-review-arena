"""Task loading and selection utilities."""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

from .task_data import BUILTIN_TASKS
from .task_types import ReviewTask


class TaskStore:
    """Loads and selects benchmark tasks."""

    def __init__(self, bundle_path: str | None = None):
        configured_path = bundle_path or os.getenv("CODE_REVIEW_TASK_BUNDLE_PATH")
        if configured_path:
            raw_items = json.loads(Path(configured_path).read_text(encoding="utf-8"))
        else:
            raw_items = BUILTIN_TASKS

        self._tasks = [ReviewTask.model_validate(item) for item in raw_items]
        self._by_id = {task.id: task for task in self._tasks}

    @property
    def task_ids(self) -> list[str]:
        return sorted(self._by_id)

    def get(self, task_id: str) -> ReviewTask:
        try:
            return self._by_id[task_id]
        except KeyError as exc:
            raise ValueError(f"Unknown task_id '{task_id}'") from exc

    def choose(self, task_id: str | None = None, difficulty: str | None = None, seed: int | None = None) -> ReviewTask:
        if task_id:
            task = self.get(task_id)
            if difficulty and task.difficulty != difficulty:
                raise ValueError(
                    f"Task '{task_id}' has difficulty '{task.difficulty}', not '{difficulty}'"
                )
            return task

        candidates = self._tasks
        if difficulty:
            candidates = [task for task in candidates if task.difficulty == difficulty]
            if not candidates:
                raise ValueError(f"No tasks available for difficulty '{difficulty}'")

        rng = random.Random(seed)
        return rng.choice(candidates)

