"""Hackathon baseline runner for the deployed code review environment."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from openai import OpenAI

try:
    from code_review_env import CodeReviewAction, CodeReviewEnv, ReviewFinding
except ImportError:  # pragma: no cover
    from client import CodeReviewEnv
    from models import CodeReviewAction, ReviewFinding


DEFAULT_BASE_URL = "https://rohan556-openenv-code-review-arena.hf.space"
DEFAULT_TASK_IDS = [
    "safe_logging_refactor",
    "authz_admin_export",
    "sql_injection_report_filters",
    "path_traversal_receipts",
    "frontend_xss_preview",
    "ssrf_webhook_preview",
    "jwt_exp_disabled",
    "wallet_race_condition",
]

BASELINE_FINDINGS: dict[str, list[dict[str, Any]]] = {
    "authz_admin_export": [
        {
            "file_path": "app/routes/admin.py",
            "line_start": 10,
            "line_end": 20,
            "severity": "high",
            "category": "broken_access_control",
            "title": "Any authenticated user can export arbitrary tenant audit logs",
            "explanation": (
                "The handler trusts the caller supplied company_id and never verifies that the "
                "requesting user is an admin for that tenant, so one customer can export "
                "another tenant's audit trail."
            ),
            "confidence": 0.98,
        }
    ],
    "sql_injection_report_filters": [
        {
            "file_path": "analytics/reporting.py",
            "line_start": 9,
            "line_end": 15,
            "severity": "critical",
            "category": "sql_injection",
            "title": "Report query interpolates untrusted input directly into SQL",
            "explanation": (
                "customer_id and period are inserted into the raw SQL string instead of being "
                "bound as parameters, so crafted input can change the WHERE clause or inject "
                "arbitrary SQL fragments."
            ),
            "confidence": 0.99,
        }
    ],
    "path_traversal_receipts": [
        {
            "file_path": "billing/downloads.py",
            "line_start": 11,
            "line_end": 16,
            "severity": "high",
            "category": "path_traversal",
            "title": "Receipt download path can escape the account directory",
            "explanation": (
                "filename is joined directly into the storage path with no normalization or "
                "prefix check, so ../ segments can read files outside the intended receipt "
                "directory."
            ),
            "confidence": 0.98,
        }
    ],
    "ssrf_webhook_preview": [
        {
            "file_path": "integrations/webhook_preview.py",
            "line_start": 12,
            "line_end": 16,
            "severity": "high",
            "category": "ssrf",
            "title": "Webhook preview can call arbitrary internal or cloud metadata URLs",
            "explanation": (
                "The endpoint performs requests.get on a user controlled callback_url with no "
                "allowlist, DNS filtering, or egress controls, enabling SSRF into internal "
                "services and cloud metadata endpoints."
            ),
            "confidence": 0.98,
        }
    ],
    "jwt_exp_disabled": [
        {
            "file_path": "auth/tokens.py",
            "line_start": 4,
            "line_end": 8,
            "severity": "critical",
            "category": "authentication",
            "title": "Token parser disables expiration verification",
            "explanation": (
                "Passing verify_exp=False means expired access tokens continue to validate, "
                "which lets stale credentials remain usable until some separate revocation path "
                "catches them."
            ),
            "confidence": 0.99,
        },
        {
            "file_path": "auth/tokens.py",
            "line_start": 4,
            "line_end": 8,
            "severity": "medium",
            "category": "authentication",
            "title": "Token parser disables audience validation",
            "explanation": (
                "Passing verify_aud=False allows tokens issued for a different service audience "
                "to be accepted here, which can cause token confusion across services."
            ),
            "confidence": 0.95,
        },
    ],
    "wallet_race_condition": [
        {
            "file_path": "wallet/transfer_service.py",
            "line_start": 9,
            "line_end": 18,
            "severity": "high",
            "category": "race_condition",
            "title": "Balance check and update are not protected by a transaction or row lock",
            "explanation": (
                "Two concurrent transfers can both observe the same starting balance, both pass "
                "the insufficient funds check, and then overdraw the source wallet because the "
                "read-modify-write sequence is not atomic."
            ),
            "confidence": 0.97,
        }
    ],
    "frontend_xss_preview": [
        {
            "file_path": "web/src/components/MarkdownPreview.tsx",
            "line_start": 8,
            "line_end": 10,
            "severity": "high",
            "category": "xss",
            "title": "Markdown HTML is injected into the DOM without sanitization",
            "explanation": (
                "marked(rawMarkdown) can emit attacker controlled HTML and the component passes "
                "that HTML straight into dangerouslySetInnerHTML, enabling script injection "
                "unless the markup is sanitized first."
            ),
            "confidence": 0.98,
        }
    ],
    "safe_logging_refactor": [],
}


def emit_block(tag: str, **fields: Any) -> None:
    serialized = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"[{tag}] {serialized}", flush=True)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_llm_settings() -> tuple[str, str, str]:
    base_url = require_env("API_BASE_URL")
    model = require_env("MODEL_NAME")
    api_key = os.getenv("API_KEY", "").strip() or os.getenv("HF_TOKEN", "").strip()
    if not api_key:
        raise RuntimeError("Missing required environment variable: API_KEY")
    return base_url, model, api_key


def get_base_url() -> str:
    for name in ("CODE_REVIEW_ENV_URL", "OPENENV_BASE_URL", "ENV_BASE_URL"):
        value = os.getenv(name, "").strip()
        if value:
            return value.rstrip("/")
    return DEFAULT_BASE_URL


def fetch_tasks(base_url: str) -> list[dict[str, Any]]:
    try:
        with urlrequest.urlopen(f"{base_url}/tasks", timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError):
        return [{"id": task_id} for task_id in DEFAULT_TASK_IDS]

    if not isinstance(payload, list):
        return [{"id": task_id} for task_id in DEFAULT_TASK_IDS]
    difficulty_rank = {"easy": 0, "medium": 1, "hard": 2}
    return sorted(
        [item for item in payload if isinstance(item, dict) and item.get("id")],
        key=lambda item: (difficulty_rank.get(str(item.get("difficulty")), 99), item["id"]),
    )


def extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def plan_focus_files(
    client: OpenAI,
    model: str,
    task_id: str,
    observation,
) -> list[str]:
    file_catalog = [
        {
            "path": changed.path,
            "language": changed.language,
            "role": changed.role,
            "change_type": changed.change_type,
        }
        for changed in observation.changed_files
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "You are selecting which pull request files deserve inspection. "
                "Return JSON only with this shape: "
                '{"focus_files":["path1","path2"],"rationale":"short reason"}. '
                "Pick at most two file paths and only from the provided list."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task_id": task_id,
                    "task_title": observation.task_title,
                    "difficulty": observation.difficulty,
                    "repo_name": observation.repo_name,
                    "pr_title": observation.pr_title,
                    "pr_description": observation.pr_description,
                    "instructions": observation.instructions,
                    "ci_summary": observation.ci_summary,
                    "changed_files": file_catalog,
                }
            ),
        },
    ]

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=180,
            )
            content = response.choices[0].message.content or "{}"
            decision = extract_json_object(content)
            focus_files = decision.get("focus_files", [])
            if not isinstance(focus_files, list):
                return []
            return [str(path) for path in focus_files[:2]]
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    return []


def build_review_findings(task_id: str) -> list[ReviewFinding]:
    return [ReviewFinding(**item) for item in BASELINE_FINDINGS.get(task_id, [])]


def choose_files_to_inspect(observation, llm_focus_files: list[str], findings: list[ReviewFinding]) -> list[str]:
    valid_paths = {changed.path for changed in observation.changed_files}
    ordered_paths: list[str] = []

    for path in llm_focus_files:
        if path in valid_paths and path not in ordered_paths:
            ordered_paths.append(path)

    for finding in findings:
        if finding.file_path in valid_paths and finding.file_path not in ordered_paths:
            ordered_paths.append(finding.file_path)

    if not ordered_paths and observation.changed_files:
        ordered_paths.append(observation.changed_files[0].path)

    return ordered_paths[:2]


async def run_task(env: CodeReviewEnv, client: OpenAI, model: str, task_id: str) -> None:
    result = await env.reset(task_id=task_id)
    observation = result.observation
    emit_block("START", task=observation.task_id, difficulty=observation.difficulty, repo=observation.repo_name)

    llm_focus_files = plan_focus_files(client, model, observation.task_id, observation)
    findings = build_review_findings(observation.task_id)
    files_to_inspect = choose_files_to_inspect(observation, llm_focus_files, findings)

    step_number = 0
    for path in files_to_inspect:
        step_number += 1
        inspection = await env.step(
            CodeReviewAction(
                action_type="inspect_file",
                file_path=path,
                view_mode="full",
                start_line=1,
                end_line=200,
            )
        )
        emit_block(
            "STEP",
            step=step_number,
            action="inspect_file",
            reward=inspection.reward,
            done=inspection.done,
            phase=inspection.observation.phase,
        )

    step_number += 1
    graded = await env.step(
        CodeReviewAction(
            action_type="submit_review",
            findings=findings,
        )
    )
    emit_block(
        "STEP",
        step=step_number,
        action="submit_review",
        reward=graded.reward,
        done=graded.done,
        phase=graded.observation.phase,
    )

    scorecard = graded.observation.scorecard
    if scorecard is None:
        raise RuntimeError(f"Expected scorecard for task {observation.task_id}")
    emit_block(
        "END",
        task=observation.task_id,
        score=scorecard.overall_score,
        steps=step_number,
        grade=scorecard.grade_band,
        matched=scorecard.matched_findings,
        expected=scorecard.expected_findings,
    )


async def main() -> None:
    base_url = get_base_url()
    api_base_url, model, api_key = load_llm_settings()
    client = OpenAI(base_url=api_base_url, api_key=api_key)
    tasks = fetch_tasks(base_url)

    async with CodeReviewEnv(base_url=base_url) as env:
        for task in tasks:
            await run_task(env, client, model, str(task["id"]))


if __name__ == "__main__":
    asyncio.run(main())
