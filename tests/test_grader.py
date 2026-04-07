from code_review_env.models import ReviewFinding
from code_review_env.server.grader import grade_submission
from code_review_env.server.task_store import TaskStore


def test_grader_matches_reference_issue():
    task = TaskStore().get("sql_injection_report_filters")
    scorecard = grade_submission(
        task,
        [
            ReviewFinding(
                file_path="analytics/reporting.py",
                line_start=9,
                line_end=15,
                severity="critical",
                category="sql_injection",
                title="Unsafe SQL string interpolation",
                explanation=(
                    "customer_id and period are interpolated directly into the SQL query "
                    "instead of using bound parameters, so attackers can inject SQL."
                ),
                confidence=0.95,
            )
        ],
        steps_used=3,
    )

    assert scorecard.overall_score > 0.9
    assert scorecard.matched_findings == 1
    assert scorecard.missed_reference_ids == []


def test_clean_task_penalizes_false_positives():
    task = TaskStore().get("safe_logging_refactor")
    scorecard = grade_submission(
        task,
        [
            ReviewFinding(
                file_path="audit/logging.py",
                line_start=3,
                line_end=6,
                severity="high",
                category="xss",
                title="Logger enables XSS",
                explanation="This change supposedly enables script execution in browsers.",
                confidence=0.9,
            )
        ],
        steps_used=2,
    )

    assert scorecard.overall_score < 0.75
    assert scorecard.false_positive_penalty > 0


def test_clean_task_perfect_score_stays_below_one():
    task = TaskStore().get("safe_logging_refactor")
    scorecard = grade_submission(task, [], steps_used=1)

    assert 0.0 < scorecard.overall_score < 1.0


def test_bad_submission_score_stays_above_zero():
    task = TaskStore().get("sql_injection_report_filters")
    scorecard = grade_submission(task, [], steps_used=task.max_steps)

    assert 0.0 < scorecard.overall_score < 1.0
