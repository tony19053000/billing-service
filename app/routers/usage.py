import json
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Depends, Header, status
from app.db import get_db, generate_id
from app.auth import get_current_workspace
from app.clock import clock
from app.services.credits import deduct_credits
from app.schemas import RecordUsageRequest

router = APIRouter(tags=["Usage Metering"])


def calculate_metric_cost(metric: str, quantity: int) -> int:
    """Compute credit cost per consumption formula."""
    if metric == "api_calls":
        return quantity * 1
    elif metric == "exports":
        return quantity * 50
    elif metric == "ai_tokens":
        return (quantity + 99) // 100
    raise ValueError(f"Unknown metric {metric}")


@router.post("/usage")
def record_usage(
    req: RecordUsageRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    workspace: Dict[str, Any] = Depends(get_current_workspace),
) -> Dict[str, Any]:
    """Ingest a usage event and debit appropriate credits."""
    credits_cost = calculate_metric_cost(req.metric, req.quantity)

    with get_db() as conn:
        # Check and debit workspace credit balance
        debited = deduct_credits(
            conn,
            workspace_id=workspace["id"],
            amount=credits_cost,
            reason="usage",
            reference=f"{req.metric} ({req.quantity})",
        )
        if not debited:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={"error": {"code": "insufficient_credits", "message": "Insufficient credit balance for this operation"}},
            )

        # Idempotency check
        if idempotency_key:
            cached = conn.execute(
                """
                SELECT status_code, response_json
                FROM idempotency_keys
                WHERE key = ? AND workspace_id = ?
                """,
                (idempotency_key, workspace["id"]),
            ).fetchone()
            if cached:
                return json.loads(cached["response_json"])

        use_id = generate_id("use")
        now_str = clock.now_iso()
        conn.execute(
            """
            INSERT INTO usage_events (id, workspace_id, metric, quantity, credits_cost, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (use_id, workspace["id"], req.metric, req.quantity, credits_cost, idempotency_key, now_str),
        )

        response_payload = {
            "id": use_id,
            "workspace_id": workspace["id"],
            "metric": req.metric,
            "quantity": req.quantity,
            "credits_cost": credits_cost,
            "created_at": now_str,
        }

        if idempotency_key:
            conn.execute(
                """
                INSERT OR REPLACE INTO idempotency_keys (
                    key, workspace_id, request_hash, status_code, response_json, created_at
                ) VALUES (?, ?, ?, 200, ?, ?)
                """,
                (
                    idempotency_key,
                    workspace["id"],
                    f"{req.metric}:{req.quantity}",
                    json.dumps(response_payload),
                    now_str,
                ),
            )

        return response_payload


@router.get("/usage")
def get_usage(
    metric: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    workspace: Dict[str, Any] = Depends(get_current_workspace),
) -> Dict[str, Any]:
    """Retrieve filtered usage events and aggregated daily totals."""
    with get_db() as conn:
        conditions = ["workspace_id = ?"]
        params: List[Any] = [workspace["id"]]

        if metric:
            conditions.append("metric = ?")
            params.append(metric)
        if from_date:
            conditions.append("created_at >= ?")
            params.append(from_date)
        if to_date:
            conditions.append("created_at <= ?")
            params.append(to_date)

        where_clause = " AND ".join(conditions)

        events_rows = conn.execute(
            f"""
            SELECT id, workspace_id, metric, quantity, credits_cost, created_at
            FROM usage_events
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT 500
            """,
            params,
        ).fetchall()

        daily_rows = conn.execute(
            f"""
            SELECT substr(created_at, 1, 10) as day, metric,
                   SUM(quantity) as total_quantity,
                   SUM(credits_cost) as total_credits
            FROM usage_events
            WHERE {where_clause}
            GROUP BY substr(created_at, 1, 10), metric
            ORDER BY day DESC
            LIMIT 90
            """,
            params,
        ).fetchall()

        return {
            "events": [dict(r) for r in events_rows],
            "daily_aggregates": [dict(r) for r in daily_rows],
        }
