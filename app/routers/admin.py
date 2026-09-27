from datetime import timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from app.db import get_db
from app.auth import require_operator
from app.clock import clock
from app.services.credits import record_credit_adjustment, get_credit_balance, get_credit_ledger
from app.services.entitlements import get_workspace_entitlements
from app.services.billing import get_active_subscription
from app.schemas import CreditAdjustRequest

router = APIRouter(prefix="/admin", tags=["Operator Admin"])


@router.get("/workspaces")
def list_admin_workspaces(
    user: Dict[str, Any] = Depends(require_operator),
) -> List[Dict[str, Any]]:
    """List all tenant workspaces across the platform."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT w.*, u.name as owner_name, u.email as owner_email,
                   s.id as subscription_id, s.plan_id, s.interval as subscription_interval,
                   s.status as subscription_status, p.name as plan_name
            FROM workspaces w
            JOIN users u ON w.owner_id = u.id
            LEFT JOIN subscriptions s ON w.id = s.workspace_id
            LEFT JOIN plans p ON s.plan_id = p.id
            ORDER BY w.created_at DESC
            """
        ).fetchall()

        # Deduplicate or group by workspace id
        workspaces_dict = {}
        for r in rows:
            ws_id = r["id"]
            if ws_id not in workspaces_dict:
                d = dict(r)
                workspaces_dict[ws_id] = d
        return list(workspaces_dict.values())


@router.get("/workspaces/{workspace_id}")
def get_admin_workspace(
    workspace_id: str,
    user: Dict[str, Any] = Depends(require_operator),
) -> Dict[str, Any]:
    """Retrieve deep operational telemetry for a specific workspace."""
    with get_db() as conn:
        ws_row = conn.execute(
            """
            SELECT w.*, u.name as owner_name, u.email as owner_email
            FROM workspaces w
            JOIN users u ON w.owner_id = u.id
            WHERE w.id = ?
            """,
            (workspace_id,),
        ).fetchone()

        if not ws_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "workspace_not_found", "message": "Workspace not found"}},
            )

        sub = get_active_subscription(conn, workspace_id)
        entitlements = get_workspace_entitlements(conn, workspace_id)
        balance = get_credit_balance(conn, workspace_id)
        ledger = get_credit_ledger(conn, workspace_id, limit=20)

        invoices = conn.execute(
            "SELECT * FROM invoices WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 20",
            (workspace_id,),
        ).fetchall()

        charges = conn.execute(
            "SELECT * FROM charges WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 20",
            (workspace_id,),
        ).fetchall()

        usage = conn.execute(
            "SELECT * FROM usage_events WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 20",
            (workspace_id,),
        ).fetchall()

        return {
            "workspace": dict(ws_row),
            "subscription": sub,
            "entitlements": entitlements,
            "credit_balance": balance,
            "credit_ledger": ledger,
            "invoices": [dict(i) for i in invoices],
            "charges": [dict(c) for c in charges],
            "usage_events": [dict(u) for u in usage],
        }


@router.get("/subscriptions")
def list_admin_subscriptions(
    status_filter: Optional[str] = None,
    user: Dict[str, Any] = Depends(require_operator),
) -> List[Dict[str, Any]]:
    """List customer subscriptions with optional status filter."""
    with get_db() as conn:
        query = """
            SELECT s.*, w.name as workspace_name, w.slug as workspace_slug,
                   p.name as plan_name, p.monthly_price_cents, p.yearly_price_cents
            FROM subscriptions s
            JOIN workspaces w ON s.workspace_id = w.id
            JOIN plans p ON s.plan_id = p.id
        """
        params: List[Any] = []
        if status_filter:
            query += " WHERE s.status = ?"
            params.append(status_filter)
        query += " ORDER BY s.created_at DESC"

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


@router.get("/invoices")
def list_admin_invoices(
    status_filter: Optional[str] = None,
    user: Dict[str, Any] = Depends(require_operator),
) -> List[Dict[str, Any]]:
    """List platform invoices with optional status filter."""
    with get_db() as conn:
        query = """
            SELECT i.*, w.name as workspace_name, w.slug as workspace_slug
            FROM invoices i
            JOIN workspaces w ON i.workspace_id = w.id
        """
        params: List[Any] = []
        if status_filter:
            query += " WHERE i.status = ?"
            params.append(status_filter)
        query += " ORDER BY i.created_at DESC"

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


@router.get("/metrics")
def get_admin_metrics(
    user: Dict[str, Any] = Depends(require_operator),
) -> Dict[str, Any]:
    """Calculate platform revenue, active subscriptions, churn, and consumption telemetry."""
    with get_db() as conn:
        active_subs = conn.execute(
            """
            SELECT s.interval, p.id as plan_id, p.name as plan_name,
                   p.monthly_price_cents, p.yearly_price_cents
            FROM subscriptions s
            JOIN plans p ON s.plan_id = p.id
            WHERE s.status = 'active'
            """
        ).fetchall()

        mrr_cents = 0
        plan_counts: Dict[str, int] = {}
        for sub in active_subs:
            if sub["interval"] == "year":
                mrr_cents += sub["yearly_price_cents"] // 12
            else:
                mrr_cents += sub["monthly_price_cents"]

            p_name = sub["plan_name"]
            plan_counts[p_name] = plan_counts.get(p_name, 0) + 1

        arr_cents = mrr_cents * 12

        # Churn in last 30 days
        thirty_days_ago = (clock.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        churned_row = conn.execute(
            """
            SELECT COUNT(*) as count
            FROM subscriptions
            WHERE status = 'canceled' AND canceled_at >= ?
            """,
            (thirty_days_ago,),
        ).fetchone()
        churn_count = churned_row["count"] if churned_row else 0

        # Credits consumed total
        credits_row = conn.execute("SELECT SUM(credits_cost) as total FROM usage_events").fetchone()
        credits_consumed = credits_row["total"] if credits_row and credits_row["total"] else 0

        # Workspace count
        ws_count_row = conn.execute("SELECT COUNT(*) as count FROM workspaces WHERE id != 'ws_operator_internal'").fetchone()
        total_workspaces = ws_count_row["count"] if ws_count_row else 0

        return {
            "mrr_cents": mrr_cents,
            "arr_cents": arr_cents,
            "mrr_formatted": f"${mrr_cents / 100:,.2f}",
            "arr_formatted": f"${arr_cents / 100:,.2f}",
            "active_subscriptions_count": len(active_subs),
            "active_subscriptions_by_plan": plan_counts,
            "churn_this_month": churn_count,
            "credits_consumed": credits_consumed,
            "total_workspaces": total_workspaces,
        }


@router.post("/workspaces/{workspace_id}/credits/adjust")
def adjust_workspace_credits(
    workspace_id: str,
    req: CreditAdjustRequest,
    user: Dict[str, Any] = Depends(require_operator),
) -> Dict[str, Any]:
    """Execute manual credit balance modification."""
    with get_db() as conn:
        ws_row = conn.execute("SELECT id FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        if not ws_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "workspace_not_found", "message": "Workspace not found"}},
            )

        new_balance = record_credit_adjustment(
            conn,
            workspace_id=workspace_id,
            delta=req.delta,
            reason=req.reason,
            reference=f"Adjusted by {user['email']}",
        )

        return {
            "workspace_id": workspace_id,
            "delta": req.delta,
            "reason": req.reason,
            "new_balance": new_balance,
        }
