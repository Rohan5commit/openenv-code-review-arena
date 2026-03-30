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
except ImportError:
    from code_review_env.models import CodeReviewAction, CodeReviewObservation
    from code_review_env.server.code_review_environment import CodeReviewEnvironment


app = create_app(
    CodeReviewEnvironment,
    CodeReviewAction,
    CodeReviewObservation,
    env_name="code_review_env",
    max_concurrent_envs=4,
)


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
