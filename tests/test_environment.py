from fastapi.testclient import TestClient

from inference import (
    BASELINE_FINDINGS,
    choose_files_to_inspect,
    discover_base_url,
    emit_block,
    emit_failed_task,
    is_healthy_base_url,
    load_llm_settings,
)
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


def test_inference_emits_structured_stdout(capsys):
    emit_block("START", task="sql_injection_report_filters", difficulty="medium")
    emit_block("STEP", step=1, reward=-0.005, done=False)
    emit_block("END", task="sql_injection_report_filters", score=0.9355, steps=2)

    lines = capsys.readouterr().out.strip().splitlines()
    assert lines == [
        "[START] task=sql_injection_report_filters difficulty=medium",
        "[STEP] step=1 reward=-0.005 done=False",
        "[END] task=sql_injection_report_filters score=0.9355 steps=2",
    ]


def test_load_llm_settings_prefers_api_key(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "https://proxy.example/v1")
    monkeypatch.setenv("MODEL_NAME", "openai/gpt-4.1-mini")
    monkeypatch.setenv("API_KEY", "primary-key")
    monkeypatch.setenv("HF_TOKEN", "fallback-token")

    assert load_llm_settings() == (
        "https://proxy.example/v1",
        ["openai/gpt-4.1-mini", "gpt-4.1-mini", "gpt-4o-mini"],
        "primary-key",
    )


def test_load_llm_settings_accepts_hf_token_fallback(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "https://proxy.example/v1")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("HF_TOKEN", "fallback-token")

    assert load_llm_settings() == (
        "https://proxy.example/v1",
        ["gpt-4.1-mini", "openai/gpt-4.1-mini", "gpt-4o-mini"],
        "fallback-token",
    )


def test_choose_files_to_inspect_uses_findings_then_falls_back():
    env = CodeReviewEnvironment()
    observation = env.reset(task_id="sql_injection_report_filters")
    findings = [ReviewFinding(**item) for item in BASELINE_FINDINGS["sql_injection_report_filters"]]

    files = choose_files_to_inspect(observation, findings=findings)

    assert files == ["analytics/reporting.py"]


def test_is_healthy_base_url_rejects_unreachable_host():
    assert is_healthy_base_url("http://127.0.0.1:9") is False


def test_discover_base_url_prefers_explicit_healthy_value(monkeypatch):
    monkeypatch.setenv("CODE_REVIEW_ENV_URL", "http://preferred.example")
    monkeypatch.setattr("inference.is_healthy_base_url", lambda url: url == "http://preferred.example")

    assert discover_base_url() == "http://preferred.example"


def test_emit_failed_task_prints_parseable_error_episode(capsys):
    emit_failed_task("sql_injection_report_filters", 0, 1)
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines == [
        "[STEP] step=1 action=error reward=0.0 done=True phase=error",
        "[END] task=sql_injection_report_filters score=0.0 steps=1 grade=error matched=0 expected=1",
    ]


def test_emit_block_swallows_broken_pipe(monkeypatch):
    monkeypatch.setattr("inference.STDOUT_BROKEN", False)

    def raise_broken_pipe(*args, **kwargs):
        raise BrokenPipeError()

    monkeypatch.setattr("inference.os.open", lambda *args, **kwargs: 123)
    monkeypatch.setattr("inference.os.dup2", lambda *args, **kwargs: None)
    monkeypatch.setattr("inference.os.close", lambda *args, **kwargs: None)
    monkeypatch.setattr("inference.builtins.print", raise_broken_pipe)

    emit_block("START", task="safe_logging_refactor")
    emit_block("END", task="safe_logging_refactor", score=1.0, steps=2)
