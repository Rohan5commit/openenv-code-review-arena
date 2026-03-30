"""Built-in benchmark corpus for the code review environment."""

from __future__ import annotations

from textwrap import dedent


def block(text: str) -> str:
    return dedent(text).strip("\n")


BUILTIN_TASKS = [
    {
        "id": "authz_admin_export",
        "title": "Tenant audit export endpoint",
        "difficulty": "medium",
        "domain": "security",
        "repo_name": "ledger-cloud",
        "pr_title": "Add CSV export endpoint for audit events",
        "pr_description": (
            "Customer success asked for a quick way to export audit events during incident "
            "response. This PR adds an admin route and a basic happy-path test."
        ),
        "instructions": (
            "Review the PR like a senior engineer. Look for security, correctness, data "
            "exposure, and operational risks. Submit only actionable findings."
        ),
        "ci_summary": "pytest -q: 82 passed, 0 failed. No security checks configured.",
        "max_steps": 8,
        "changed_files": [
            {
                "path": "app/routes/admin.py",
                "language": "python",
                "change_type": "modified",
                "added_lines": 22,
                "removed_lines": 1,
                "role": "api",
                "diff": block(
                    """
                    @@ -1,8 +1,29 @@
                     from fastapi import APIRouter, Depends, Query
                     from sqlalchemy.orm import Session

                    +from app.auth import get_current_user
                    +from app.database import get_db
                    +from app.models import AuditEvent, User
                    +
                     router = APIRouter(prefix="/admin", tags=["admin"])
                    +
                    +@router.get("/audit/export")
                    +def export_audit_events(
                    +    company_id: str = Query(...),
                    +    limit: int = Query(500, le=5000),
                    +    db: Session = Depends(get_db),
                    +    user: User = Depends(get_current_user),
                    +):
                    +    rows = (
                    +        db.query(AuditEvent)
                    +        .filter(AuditEvent.company_id == company_id)
                    +        .order_by(AuditEvent.created_at.desc())
                    +        .limit(limit)
                    +        .all()
                    +    )
                    +
                    +    headers = ["actor_email", "action", "created_at", "ip_address"]
                    +    csv_lines = [",".join(headers)]
                    +    return {"filename": f"audit-{company_id}.csv", "content": "\\n".join(csv_lines)}
                    """
                ),
                "full_content": block(
                    """
                    from fastapi import APIRouter, Depends, Query
                    from sqlalchemy.orm import Session

                    from app.auth import get_current_user
                    from app.database import get_db
                    from app.models import AuditEvent, User

                    router = APIRouter(prefix="/admin", tags=["admin"])


                    @router.get("/audit/export")
                    def export_audit_events(
                        company_id: str = Query(...),
                        limit: int = Query(500, le=5000),
                        db: Session = Depends(get_db),
                        user: User = Depends(get_current_user),
                    ):
                        rows = (
                            db.query(AuditEvent)
                            .filter(AuditEvent.company_id == company_id)
                            .order_by(AuditEvent.created_at.desc())
                            .limit(limit)
                            .all()
                        )

                        headers = ["actor_email", "action", "created_at", "ip_address"]
                        csv_lines = [",".join(headers)]
                        for row in rows:
                            csv_lines.append(
                                f"{row.actor_email},{row.action},{row.created_at.isoformat()},{row.ip_address}"
                            )

                        return {
                            "filename": f"audit-{company_id}.csv",
                            "content": "\\n".join(csv_lines),
                        }
                    """
                ),
            },
            {
                "path": "tests/test_admin_export.py",
                "language": "python",
                "change_type": "added",
                "added_lines": 17,
                "removed_lines": 0,
                "role": "test",
                "diff": block(
                    """
                    @@ -0,0 +1,17 @@
                    +def test_admin_export_happy_path(client, admin_user, db_session):
                    +    response = client.get(
                    +        "/admin/audit/export",
                    +        params={"company_id": admin_user.company_id},
                    +        headers={"Authorization": admin_user.token},
                    +    )
                    +
                    +    assert response.status_code == 200
                    +    assert response.json()["filename"].startswith("audit-")
                    """
                ),
                "full_content": block(
                    """
                    def test_admin_export_happy_path(client, admin_user, db_session):
                        response = client.get(
                            "/admin/audit/export",
                            params={"company_id": admin_user.company_id},
                            headers={"Authorization": admin_user.token},
                        )

                        assert response.status_code == 200
                        body = response.json()
                        assert body["filename"].startswith("audit-")
                        assert "content" in body
                    """
                ),
            },
        ],
        "gold_findings": [
            {
                "id": "authz-001",
                "file_path": "app/routes/admin.py",
                "line_start": 10,
                "line_end": 20,
                "severity": "high",
                "category": "broken_access_control",
                "title": "Any authenticated user can export arbitrary tenant audit logs",
                "summary": (
                    "The route trusts user-supplied company_id and never checks that the caller "
                    "is an admin or belongs to that tenant."
                ),
                "title_keywords": ["authenticated", "admin", "tenant", "audit", "export"],
                "explanation_keywords": ["company_id", "authorization", "audit logs", "data exposure"],
                "aliases": ["authz", "authorization", "idor", "tenant_isolation"],
            }
        ],
    },
    {
        "id": "sql_injection_report_filters",
        "title": "Revenue report filter helper",
        "difficulty": "medium",
        "domain": "security",
        "repo_name": "revdash-api",
        "pr_title": "Support customer scoped revenue report filters",
        "pr_description": (
            "Adds a report helper so customer success can pull billing data for a given "
            "customer and period without writing ad-hoc SQL."
        ),
        "instructions": (
            "Focus on injection vectors, correctness of query construction, and data integrity."
        ),
        "ci_summary": "pytest analytics -q: 26 passed. sqlfluff not enabled in CI.",
        "max_steps": 8,
        "changed_files": [
            {
                "path": "analytics/reporting.py",
                "language": "python",
                "change_type": "modified",
                "added_lines": 18,
                "removed_lines": 2,
                "role": "service",
                "diff": block(
                    """
                    @@ -18,10 +18,19 @@
                     from sqlalchemy import text

                     def fetch_revenue_report(db, customer_id: str, period: str):
                    -    query = "SELECT invoice_id FROM invoices"
                    +    query = (
                    +        "SELECT invoice_id, total_cents, currency "
                    +        "FROM invoices "
                    +        f"WHERE customer_id = '{customer_id}' "
                    +        f"AND billing_period = '{period}' "
                    +        "ORDER BY created_at DESC"
                    +    )
                    +    return db.execute(text(query)).mappings().all()
                    """
                ),
                "full_content": block(
                    """
                    from __future__ import annotations

                    from sqlalchemy import text


                    def fetch_revenue_report(db, customer_id: str, period: str):
                        normalized_period = period.strip()
                        if not normalized_period:
                            return []

                        query = (
                            "SELECT invoice_id, total_cents, currency "
                            "FROM invoices "
                            f"WHERE customer_id = '{customer_id}' "
                            f"AND billing_period = '{normalized_period}' "
                            "ORDER BY created_at DESC"
                        )

                        return db.execute(text(query)).mappings().all()
                    """
                ),
            },
            {
                "path": "api/routes/reports.py",
                "language": "python",
                "change_type": "modified",
                "added_lines": 5,
                "removed_lines": 1,
                "role": "api",
                "diff": block(
                    """
                    @@ -9,7 +9,11 @@
                     @router.get("/revenue")
                     def get_revenue_report(customer_id: str, period: str, db=Depends(get_db)):
                    -    return fetch_revenue_report(db, customer_id, period)
                    +    rows = fetch_revenue_report(db, customer_id, period)
                    +    return {"rows": rows, "count": len(rows)}
                    """
                ),
                "full_content": block(
                    """
                    from fastapi import APIRouter, Depends

                    from analytics.reporting import fetch_revenue_report
                    from app.database import get_db

                    router = APIRouter(prefix="/reports", tags=["reports"])


                    @router.get("/revenue")
                    def get_revenue_report(customer_id: str, period: str, db=Depends(get_db)):
                        rows = fetch_revenue_report(db, customer_id, period)
                        return {"rows": rows, "count": len(rows)}
                    """
                ),
            },
        ],
        "gold_findings": [
            {
                "id": "sqli-001",
                "file_path": "analytics/reporting.py",
                "line_start": 9,
                "line_end": 15,
                "severity": "critical",
                "category": "sql_injection",
                "title": "Report query interpolates untrusted input directly into SQL",
                "summary": (
                    "customer_id and period are concatenated into a SQL string instead of "
                    "using bound parameters."
                ),
                "title_keywords": ["sql", "query", "interpolates", "untrusted", "input"],
                "explanation_keywords": ["customer_id", "period", "bound parameters", "inject"],
                "aliases": ["injection", "unsafe_sql", "raw_sql"],
            }
        ],
    },
    {
        "id": "path_traversal_receipts",
        "title": "Receipt download helper",
        "difficulty": "medium",
        "domain": "security",
        "repo_name": "billing-hub",
        "pr_title": "Add direct receipt download API",
        "pr_description": (
            "This endpoint lets support quickly download customer receipts from object storage "
            "mirrored on disk."
        ),
        "instructions": "Look for file system safety issues, path handling bugs, and auth bypasses.",
        "ci_summary": "pytest billing -q: 41 passed. Manual QA only for download flow.",
        "max_steps": 7,
        "changed_files": [
            {
                "path": "billing/downloads.py",
                "language": "python",
                "change_type": "modified",
                "added_lines": 16,
                "removed_lines": 0,
                "role": "api",
                "diff": block(
                    """
                    @@ -1,5 +1,21 @@
                    +import os
                    +
                     from fastapi import APIRouter, HTTPException
                     from fastapi.responses import FileResponse

                    +STORAGE_ROOT = "/srv/receipts"
                    +
                    +@router.get("/accounts/{account_id}/receipts/{filename}")
                    +def download_receipt(account_id: str, filename: str):
                    +    safe_dir = os.path.join(STORAGE_ROOT, account_id)
                    +    target_path = os.path.join(safe_dir, filename)
                    +    if not os.path.exists(target_path):
                    +        raise HTTPException(status_code=404, detail="receipt not found")
                    +    return FileResponse(target_path, filename=filename)
                    """
                ),
                "full_content": block(
                    """
                    import os

                    from fastapi import APIRouter, HTTPException
                    from fastapi.responses import FileResponse

                    router = APIRouter(prefix="/billing", tags=["billing"])

                    STORAGE_ROOT = "/srv/receipts"


                    @router.get("/accounts/{account_id}/receipts/{filename}")
                    def download_receipt(account_id: str, filename: str):
                        safe_dir = os.path.join(STORAGE_ROOT, account_id)
                        target_path = os.path.join(safe_dir, filename)

                        if not os.path.exists(target_path):
                            raise HTTPException(status_code=404, detail="receipt not found")

                        return FileResponse(target_path, filename=filename)
                    """
                ),
            }
        ],
        "gold_findings": [
            {
                "id": "path-001",
                "file_path": "billing/downloads.py",
                "line_start": 11,
                "line_end": 16,
                "severity": "high",
                "category": "path_traversal",
                "title": "Receipt download path can escape the account directory",
                "summary": (
                    "filename is joined directly into the filesystem path, so ../ segments can "
                    "read files outside the expected receipt directory."
                ),
                "title_keywords": ["path", "escape", "directory", "receipt"],
                "explanation_keywords": ["filename", "../", "normalize", "outside", "filesystem"],
                "aliases": ["directory_traversal", "file_disclosure"],
            }
        ],
    },
    {
        "id": "ssrf_webhook_preview",
        "title": "Webhook preview tester",
        "difficulty": "hard",
        "domain": "security",
        "repo_name": "integrations-core",
        "pr_title": "Add webhook preview endpoint for onboarding",
        "pr_description": (
            "Sales engineers wanted a quick endpoint that calls a candidate webhook and returns "
            "the preview body during setup."
        ),
        "instructions": "Check outbound request safety, host validation, and secrets exposure.",
        "ci_summary": "pytest integrations -q: 33 passed. No egress policy tests.",
        "max_steps": 8,
        "changed_files": [
            {
                "path": "integrations/webhook_preview.py",
                "language": "python",
                "change_type": "added",
                "added_lines": 24,
                "removed_lines": 0,
                "role": "api",
                "diff": block(
                    """
                    @@ -0,0 +1,24 @@
                    +import requests
                    +from fastapi import APIRouter
                    +from pydantic import BaseModel
                    +
                    +router = APIRouter(prefix="/integrations", tags=["integrations"])
                    +
                    +class PreviewRequest(BaseModel):
                    +    callback_url: str
                    +
                    +@router.post("/webhook-preview")
                    +def preview_webhook(request: PreviewRequest):
                    +    response = requests.get(
                    +        request.callback_url,
                    +        headers={"X-Preview": "true"},
                    +        timeout=5,
                    +    )
                    +    return {"status_code": response.status_code, "body": response.text[:400]}
                    """
                ),
                "full_content": block(
                    """
                    import requests
                    from fastapi import APIRouter
                    from pydantic import BaseModel

                    router = APIRouter(prefix="/integrations", tags=["integrations"])


                    class PreviewRequest(BaseModel):
                        callback_url: str


                    @router.post("/webhook-preview")
                    def preview_webhook(request: PreviewRequest):
                        response = requests.get(
                            request.callback_url,
                            headers={"X-Preview": "true"},
                            timeout=5,
                        )
                        return {
                            "status_code": response.status_code,
                            "body": response.text[:400],
                        }
                    """
                ),
            }
        ],
        "gold_findings": [
            {
                "id": "ssrf-001",
                "file_path": "integrations/webhook_preview.py",
                "line_start": 12,
                "line_end": 16,
                "severity": "high",
                "category": "ssrf",
                "title": "Webhook preview can call arbitrary internal or cloud metadata URLs",
                "summary": (
                    "The endpoint fetches a user-controlled URL directly with no allowlist or "
                    "network restrictions."
                ),
                "title_keywords": ["arbitrary", "internal", "metadata", "url", "fetch"],
                "explanation_keywords": ["user-controlled", "allowlist", "egress", "ssrf"],
                "aliases": ["server_side_request_forgery", "untrusted_url_fetch"],
            }
        ],
    },
    {
        "id": "jwt_exp_disabled",
        "title": "JWT claim parser cleanup",
        "difficulty": "hard",
        "domain": "security",
        "repo_name": "auth-gateway",
        "pr_title": "Refactor JWT parsing into a single helper",
        "pr_description": (
            "This consolidates token parsing logic and turns off a couple of validations until "
            "all upstream issuers are migrated."
        ),
        "instructions": "Review token validation carefully; auth regressions can be subtle.",
        "ci_summary": "pytest auth -q: 58 passed. Integration tokens are all fresh in tests.",
        "max_steps": 8,
        "changed_files": [
            {
                "path": "auth/tokens.py",
                "language": "python",
                "change_type": "modified",
                "added_lines": 15,
                "removed_lines": 8,
                "role": "security",
                "diff": block(
                    """
                    @@ -10,11 +10,20 @@
                     import jwt

                     def decode_access_token(token: str, settings):
                    -    return jwt.decode(token, settings.JWT_PUBLIC_KEY, algorithms=["RS256"])
                    +    return jwt.decode(
                    +        token,
                    +        settings.JWT_PUBLIC_KEY,
                    +        algorithms=["RS256"],
                    +        options={"verify_aud": False, "verify_exp": False},
                    +    )
                    """
                ),
                "full_content": block(
                    """
                    import jwt


                    def decode_access_token(token: str, settings):
                        claims = jwt.decode(
                            token,
                            settings.JWT_PUBLIC_KEY,
                            algorithms=["RS256"],
                            options={"verify_aud": False, "verify_exp": False},
                        )
                        return {
                            "sub": claims["sub"],
                            "scope": claims.get("scope", ""),
                            "tenant_id": claims.get("tenant_id"),
                        }
                    """
                ),
            }
        ],
        "gold_findings": [
            {
                "id": "jwt-001",
                "file_path": "auth/tokens.py",
                "line_start": 4,
                "line_end": 8,
                "severity": "critical",
                "category": "authentication",
                "title": "Token parser disables expiration verification",
                "summary": (
                    "verify_exp=False makes expired access tokens valid indefinitely until revoked."
                ),
                "title_keywords": ["expiration", "expired", "token", "verification"],
                "explanation_keywords": ["verify_exp", "expired access tokens", "auth bypass"],
                "aliases": ["jwt", "session_validation", "expired_token"],
            },
            {
                "id": "jwt-002",
                "file_path": "auth/tokens.py",
                "line_start": 4,
                "line_end": 8,
                "severity": "medium",
                "category": "authentication",
                "title": "Token parser disables audience validation",
                "summary": (
                    "verify_aud=False allows tokens minted for a different service audience to "
                    "be accepted here."
                ),
                "title_keywords": ["audience", "different service", "token"],
                "explanation_keywords": ["verify_aud", "wrong audience", "accept"],
                "aliases": ["jwt", "aud_claim", "token_confusion"],
            },
        ],
    },
    {
        "id": "wallet_race_condition",
        "title": "Wallet transfer helper",
        "difficulty": "hard",
        "domain": "correctness",
        "repo_name": "payments-ledger",
        "pr_title": "Move wallet transfers into a shared service",
        "pr_description": (
            "This extracts the transfer path into one helper used by checkout and refunds."
        ),
        "instructions": (
            "Prioritize correctness under concurrency, transaction boundaries, and money movement."
        ),
        "ci_summary": "pytest wallet -q: 71 passed. Tests run serially against sqlite.",
        "max_steps": 8,
        "changed_files": [
            {
                "path": "wallet/transfer_service.py",
                "language": "python",
                "change_type": "added",
                "added_lines": 28,
                "removed_lines": 0,
                "role": "service",
                "diff": block(
                    """
                    @@ -0,0 +1,28 @@
                    +from wallet.models import Wallet
                    +
                    +def transfer_funds(db, source_wallet_id: str, destination_wallet_id: str, amount_cents: int):
                    +    source = db.query(Wallet).filter(Wallet.id == source_wallet_id).one()
                    +    destination = db.query(Wallet).filter(Wallet.id == destination_wallet_id).one()
                    +
                    +    if source.balance_cents < amount_cents:
                    +        raise ValueError("insufficient balance")
                    +
                    +    source.balance_cents -= amount_cents
                    +    destination.balance_cents += amount_cents
                    +    db.commit()
                    +    return {"source_balance": source.balance_cents, "destination_balance": destination.balance_cents}
                    """
                ),
                "full_content": block(
                    """
                    from wallet.models import Wallet


                    def transfer_funds(
                        db,
                        source_wallet_id: str,
                        destination_wallet_id: str,
                        amount_cents: int,
                    ):
                        source = db.query(Wallet).filter(Wallet.id == source_wallet_id).one()
                        destination = (
                            db.query(Wallet).filter(Wallet.id == destination_wallet_id).one()
                        )

                        if source.balance_cents < amount_cents:
                            raise ValueError("insufficient balance")

                        source.balance_cents -= amount_cents
                        destination.balance_cents += amount_cents
                        db.commit()
                        return {
                            "source_balance": source.balance_cents,
                            "destination_balance": destination.balance_cents,
                        }
                    """
                ),
            },
            {
                "path": "tests/test_transfer_service.py",
                "language": "python",
                "change_type": "added",
                "added_lines": 14,
                "removed_lines": 0,
                "role": "test",
                "diff": block(
                    """
                    @@ -0,0 +1,14 @@
                    +def test_transfer_moves_money(db_session, source_wallet, destination_wallet):
                    +    result = transfer_funds(db_session, source_wallet.id, destination_wallet.id, 500)
                    +    assert result["source_balance"] == 4500
                    +    assert result["destination_balance"] == 1500
                    """
                ),
                "full_content": block(
                    """
                    from wallet.transfer_service import transfer_funds


                    def test_transfer_moves_money(db_session, source_wallet, destination_wallet):
                        result = transfer_funds(
                            db_session,
                            source_wallet.id,
                            destination_wallet.id,
                            500,
                        )
                        assert result["source_balance"] == 4500
                        assert result["destination_balance"] == 1500
                    """
                ),
            },
        ],
        "gold_findings": [
            {
                "id": "race-001",
                "file_path": "wallet/transfer_service.py",
                "line_start": 9,
                "line_end": 18,
                "severity": "high",
                "category": "race_condition",
                "title": "Balance check and update are not protected by a transaction or row lock",
                "summary": (
                    "Concurrent transfers can both pass the balance check and overdraw the same wallet."
                ),
                "title_keywords": ["balance", "transaction", "row lock", "concurrent"],
                "explanation_keywords": ["race", "overdraw", "serializable", "select for update"],
                "aliases": ["concurrency", "double_spend", "atomicity"],
            }
        ],
    },
    {
        "id": "frontend_xss_preview",
        "title": "Markdown preview component",
        "difficulty": "medium",
        "domain": "security",
        "repo_name": "support-portal-web",
        "pr_title": "Render markdown in the canned reply editor",
        "pr_description": (
            "Adds a live markdown preview to help support reps validate rich-text replies."
        ),
        "instructions": "Review client-side rendering changes for script injection and unsafe DOM sinks.",
        "ci_summary": "pnpm test: 119 passed. No browser security regression tests.",
        "max_steps": 7,
        "changed_files": [
            {
                "path": "web/src/components/MarkdownPreview.tsx",
                "language": "typescript",
                "change_type": "added",
                "added_lines": 17,
                "removed_lines": 0,
                "role": "ui",
                "diff": block(
                    """
                    @@ -0,0 +1,17 @@
                    +import { marked } from "marked";
                    +
                    +type Props = {
                    +  rawMarkdown: string;
                    +};
                    +
                    +export function MarkdownPreview({ rawMarkdown }: Props) {
                    +  return (
                    +    <section className="preview">
                    +      <div dangerouslySetInnerHTML={{ __html: marked(rawMarkdown) }} />
                    +    </section>
                    +  );
                    +}
                    """
                ),
                "full_content": block(
                    """
                    import { marked } from "marked";

                    type Props = {
                      rawMarkdown: string;
                    };

                    export function MarkdownPreview({ rawMarkdown }: Props) {
                      return (
                        <section className="preview">
                          <div dangerouslySetInnerHTML={{ __html: marked(rawMarkdown) }} />
                        </section>
                      );
                    }
                    """
                ),
            }
        ],
        "gold_findings": [
            {
                "id": "xss-001",
                "file_path": "web/src/components/MarkdownPreview.tsx",
                "line_start": 8,
                "line_end": 10,
                "severity": "high",
                "category": "xss",
                "title": "Markdown HTML is injected into the DOM without sanitization",
                "summary": (
                    "marked(rawMarkdown) can emit attacker-controlled HTML, which is passed "
                    "straight into dangerouslySetInnerHTML."
                ),
                "title_keywords": ["html", "dom", "sanitization", "markdown"],
                "explanation_keywords": ["dangerouslySetInnerHTML", "script", "xss", "sanitize"],
                "aliases": ["cross_site_scripting", "unsafe_html"],
            }
        ],
    },
    {
        "id": "safe_logging_refactor",
        "title": "Audit logging refactor",
        "difficulty": "easy",
        "domain": "quality",
        "repo_name": "ops-api",
        "pr_title": "Unify audit logger creation",
        "pr_description": (
            "Simple refactor to centralize audit logger initialization and reduce duplicated code."
        ),
        "instructions": (
            "This task intentionally may not contain a bug. Avoid inventing issues unless you can "
            "point to a concrete, user-impacting problem."
        ),
        "ci_summary": "pytest audit -q: 44 passed. ruff and mypy clean.",
        "max_steps": 6,
        "changed_files": [
            {
                "path": "audit/logging.py",
                "language": "python",
                "change_type": "modified",
                "added_lines": 10,
                "removed_lines": 9,
                "role": "utility",
                "diff": block(
                    """
                    @@ -1,13 +1,14 @@
                     import logging

                    -def get_audit_logger():
                    -    logger = logging.getLogger("audit")
                    -    if not logger.handlers:
                    -        logger.setLevel(logging.INFO)
                    -    return logger
                    +def build_audit_logger() -> logging.Logger:
                    +    logger = logging.getLogger("audit")
                    +    logger.setLevel(logging.INFO)
                    +    return logger
                    +
                    +AUDIT_LOGGER = build_audit_logger()
                    """
                ),
                "full_content": block(
                    """
                    import logging


                    def build_audit_logger() -> logging.Logger:
                        logger = logging.getLogger("audit")
                        logger.setLevel(logging.INFO)
                        return logger


                    AUDIT_LOGGER = build_audit_logger()
                    """
                ),
            }
        ],
        "gold_findings": [],
    },
]
