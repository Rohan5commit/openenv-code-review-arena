from fastapi.testclient import TestClient

from code_review_env.models import CodeReviewAction, ReviewFinding
from code_review_env.server.app import app
from code_review_env.server.code_review_environment import CodeReviewEnvironment


def test_environment_reset_and_inspect():
    env = CodeReviewEnvironment()
    observation = env.reset(task_id="path_traversal_receipts")
    assert observation.task_id == "path_traversal_receipts"
    assert observation.attempts_remaining == 7

    inspection = env.step(
        CodeReviewAction(
            action_type="inspect_file",
            file_path="billing/downloads.py",
            view_mode="full",
            start_line=1,
            end_line=20,
        )
    )
    assert "download_receipt" in inspection.displayed_content
    assert inspection.done is False


def test_environment_submit_review_scores_task():
    env = CodeReviewEnvironment()
    env.reset(task_id="jwt_exp_disabled")
    graded = env.step(
        CodeReviewAction(
            action_type="submit_review",
            findings=[
                ReviewFinding(
                    file_path="auth/tokens.py",
                    line_start=4,
                    line_end=8,
                    severity="critical",
                    category="authentication",
                    title="Expiration verification is disabled for JWTs",
                    explanation=(
                        "verify_exp=False means expired access tokens are still accepted, "
                        "which is an authentication bypass."
                    ),
                    confidence=0.98,
                )
            ],
        )
    )
    assert graded.done is True
    assert graded.scorecard is not None
    assert graded.scorecard.overall_score > 0.45


def test_fastapi_endpoints_expose_openenv_contract():
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"

    schema = client.get("/schema")
    assert schema.status_code == 200
    payload = schema.json()
    assert "action" in payload
    assert "observation" in payload
    assert "state" in payload

    tasks = client.get("/tasks")
    assert tasks.status_code == 200
    task_items = tasks.json()
    assert any(item["id"] == "sql_injection_report_filters" for item in task_items)
