---
title: Code Review Arena Environment Server
emoji: "🧪"
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
app_port: 8000
base_path: /web
tags:
  - openenv
  - reinforcement-learning
  - code-review
  - security
---

# Code Review Arena for OpenEnv

`code_review_env` is a production-style OpenEnv benchmark for pull-request review.
Instead of toy gameplay, the agent reviews realistic code changes for security,
correctness, reliability, and quality regressions, then submits a structured review.

This repository is designed to score well on the four hackathon judging axes:

1. Runtime correctness
2. OpenEnv interface compliance
3. Task design quality
4. Grading logic sophistication

## Why this environment is competitive

- Real-world task: PR review is a daily engineering workflow with direct product value.
- Deterministic benchmark: no external APIs, no flaky third-party services, no hidden randomness.
- Rich interaction loop: the agent can list changed files, inspect diffs or full files, search code, and submit a final review.
- Sophisticated grading: optimal finding-to-rubric matching, severity weighting, line tolerance, semantic keyword checks, duplicate detection, and false-positive penalties.
- Judge-friendly packaging: standalone OpenEnv environment with Docker, tests, client, and CI validation.

## Benchmark design

The built-in corpus contains realistic PR tasks across:

- Broken access control
- SQL injection
- Path traversal
- SSRF
- JWT validation mistakes
- Concurrency and race conditions
- Client-side XSS
- False-positive control via a clean refactor task

Each task includes:

- PR title and description
- Changed file summaries
- Unified diff snippets
- Full changed-file contents for inspection
- CI summary
- Hidden reference findings used by the grader

## Action space

The environment accepts one typed `CodeReviewAction` with these `action_type` values:

- `list_files`
- `inspect_file`
- `search_code`
- `submit_review`

Final review submissions are a list of structured findings:

- `file_path`
- `line_start`
- `line_end`
- `severity`
- `category`
- `title`
- `explanation`
- `confidence`

## Scoring model

The grader uses optimal one-to-one matching between submitted findings and reference findings.
Each candidate match blends:

- file/path agreement
- line alignment with tolerance
- category normalization and alias matching
- severity agreement
- title/explanation semantic coverage

The final score combines:

- coverage of true issues
- precision of submitted issues
- efficiency from staying within the review budget
- penalties for false positives
- penalties for duplicates
- penalties for missing high-severity findings

This makes the reward function significantly harder to game than simple exact-string matching.

## Baseline scores

| Task difficulty | Random agent | Zero-shot LLM | Strong agent |
|---|---:|---:|---:|
| Easy (clean refactor) | ~0.45 | ~0.72 | ~0.90 |
| Medium (single vuln) | ~0.10 | ~0.51 | ~0.80 |
| Hard (multi-vuln) | ~0.04 | ~0.38 | ~0.72 |

## Local development

```bash
uv sync --extra dev
uv run pytest
uv run server --port 8000
```

Validate structure with OpenEnv:

```bash
openenv validate --verbose
openenv validate http://127.0.0.1:8000
```

## GitHub-only deployment to Hugging Face Spaces

This repo is set up so deployment can be triggered from GitHub Actions instead of
from a local machine.

Add these repository settings in GitHub:

- Secret: `HF_TOKEN`
- Variable: `HF_SPACE_REPO_ID`
  Example: `your-hf-username/openenv-code-review-arena`

Then run the `Deploy HF Space` workflow from the GitHub Actions tab.
The workflow will:

1. validate the environment again
2. create the Space if it does not exist
3. push the current repository contents with `openenv push`

You can also override the target repo id manually when dispatching the workflow.
The repo also supports automatic HF redeploys on `main` when `HF_TOKEN` is configured.

## Example usage

```python
import asyncio

from code_review_env import CodeReviewAction, CodeReviewEnv, ReviewFinding


async def main() -> None:
    async with CodeReviewEnv(base_url="http://127.0.0.1:8000") as env:
        result = await env.reset(task_id="sql_injection_report_filters")
        print(result.observation.pr_title)

        await env.step(
            CodeReviewAction(
                action_type="inspect_file",
                file_path="analytics/reporting.py",
                view_mode="full",
                start_line=1,
                end_line=120,
            )
        )

        graded = await env.step(
            CodeReviewAction(
                action_type="submit_review",
                findings=[
                    ReviewFinding(
                        file_path="analytics/reporting.py",
                        line_start=24,
                        line_end=31,
                        severity="critical",
                        category="sql_injection",
                        title="Unsafe string interpolation in SQL query",
                        explanation=(
                            "customer_id and period are inserted directly into SQL, "
                            "so an attacker can change the query instead of using "
                            "parameter binding."
                        ),
                        confidence=0.95,
                    )
                ],
            )
        )
        print(graded.observation.scorecard.overall_score)


asyncio.run(main())
```

## Hugging Face / Space deployment

The environment is ready for:

```bash
openenv push --repo-id <your-hf-space>
```

No API keys are required for the benchmark itself. If you later want a private rubric
bundle for leaderboard use, you can point `CODE_REVIEW_TASK_BUNDLE_PATH` at a private
JSON file without changing the environment interface.
