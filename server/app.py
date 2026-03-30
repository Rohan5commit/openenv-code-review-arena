"""FastAPI server entrypoint for the OpenEnv code review benchmark."""

from __future__ import annotations

try:
    from openenv.core.env_server.http_server import create_app
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "openenv-core is required for the web interface. Install dependencies with 'uv sync'."
    ) from exc

try:
    from ..models import CodeReviewAction, CodeReviewObservation
    from .code_review_environment import CodeReviewEnvironment
    from .task_store import TaskStore
except ImportError:
    from code_review_env.models import CodeReviewAction, CodeReviewObservation
    from code_review_env.server.code_review_environment import CodeReviewEnvironment
    from code_review_env.server.task_store import TaskStore


app = create_app(
    CodeReviewEnvironment,
    CodeReviewAction,
    CodeReviewObservation,
    env_name="code_review_env",
    max_concurrent_envs=4,
)


@app.get("/tasks")
async def list_tasks() -> list[dict[str, str]]:
    store = TaskStore()
    return [
        {
            "id": task.id,
            "difficulty": task.difficulty,
            "title": task.title,
            "description": task.pr_title,
        }
        for task in store.all_tasks
    ]


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=host,
        port=port,
        ws_ping_interval=300,
        ws_ping_timeout=300,
    )


if __name__ == "__main__":
    main()
