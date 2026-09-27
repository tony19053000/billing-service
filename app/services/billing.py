from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from app.db import generate_id
from app.clock import clock
from app.services.invoices import create_invoice
from app.services.credits import grant_credits
from app.services.entitlements import recompute_entitlements
from app.services.proration import calculate_proration


def get_active_subscription(conn, workspace_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve the primary subscription for a workspace."""
    row = conn.execute(
        """
        SELECT s.*, p.name as plan_name, p.monthly_price_cents, p.yearly_price_cents,
               p.included_credits_per_period, p.seats, p.description as plan_description
        FROM subscriptions s
        JOIN plans p ON s.plan_id = p.id
        WHERE s.workspace_id = ?
        ORDER BY s.created_at DESC
        LIMIT 1
        """,
        (workspace_id,),
    ).fetchone()
    if row:
        return dict(row)
    return None


def change_plan(conn, workspace_id: str, new_plan_id: str, interval: str) -> Dict[str, Any]:
    """Execute immediate plan transition with proration and entitlement updates."""
    sub = get_active_subscription(conn, workspace_id)
    if not sub:
        raise ValueError("No subscription found for workspace")

    new_plan_row = conn.execute("SELECT * FROM plans WHERE id = ?", (new_plan_id,)).fetchone()
    if not new_plan_row:
        raise ValueError("Target plan not found")
    new_plan = dict(new_plan_row)

    current_plan = {
        "id": sub["plan_id"],
        "name": sub["plan_name"],
        "monthly_price_cents": sub["monthly_price_cents"],
        "yearly_price_cents": sub["yearly_price_cents"],
        "included_credits_per_period": sub["included_credits_per_period"],
    }

    proration = calculate_proration(
        current_plan=current_plan,
        new_plan=new_plan,
        interval=interval,
        period_start_iso=sub["current_period_start"],
        period_end_iso=sub["current_period_end"],
    )

    lines = []
    if proration["current_unused_credit"] > 0:
        lines.append({
            "description": f"Unused time on {current_plan['name']}",
            "quantity": 1,
            "unit_cents": -proration["current_unused_credit"],
            "amount_cents": -proration["current_unused_credit"],
        })
    if proration["new_plan_cost"] > 0:
        lines.append({
            "description": f"Remaining time on {new_plan['name']}",
            "quantity": 1,
            "unit_cents": proration["new_plan_cost"],
            "amount_cents": proration["new_plan_cost"],
        })

    # If both are 0 (e.g. Starter to Starter or free plan), create nominal transition line
    if not lines:
        lines.append({
            "description": f"Plan switch to {new_plan['name']}",
            "quantity": 1,
            "unit_cents": 0,
            "amount_cents": 0,
        })

    invoice = create_invoice(
        conn,
        workspace_id=workspace_id,
        lines=lines,
        subscription_id=sub["id"],
        status="paid",
        auto_pay=True,
        period_start=sub["current_period_start"],
        period_end=sub["current_period_end"],
    )

    # Update subscription record
    conn.execute(
        """
        UPDATE subscriptions
        SET plan_id = ?, interval = ?
        WHERE id = ?
        """,
        (new_plan_id, interval, sub["id"]),
    )

    # Recompute entitlements
    recompute_entitlements(conn, workspace_id, new_plan_id)

    # Grant credit delta if upgrade
    credit_delta = new_plan["included_credits_per_period"] - current_plan["included_credits_per_period"]
    if credit_delta > 0:
        grant_credits(
            conn,
            workspace_id=workspace_id,
            amount=credit_delta,
            reason="period_grant",
            reference=f"Upgrade to {new_plan['name']}",
        )

    updated_sub = get_active_subscription(conn, workspace_id)
    return {
        "subscription": updated_sub,
        "invoice": invoice,
        "proration": proration,
    }


def cancel_subscription(conn, workspace_id: str, at_period_end: bool) -> Dict[str, Any]:
    """Flag subscription for period-end cancellation or cancel immediately."""
    sub = get_active_subscription(conn, workspace_id)
    if not sub:
        raise ValueError("Subscription not found")

    now_str = clock.now_iso()
    if at_period_end:
        conn.execute(
            """
            UPDATE subscriptions
            SET cancel_at_period_end = 1
            WHERE id = ?
            """,
            (sub["id"],),
        )
    else:
        conn.execute(
            """
            UPDATE subscriptions
            SET status = 'canceled', canceled_at = ?, cancel_at_period_end = 0
            WHERE id = ?
            """,
            (now_str, sub["id"]),
        )

    return get_active_subscription(conn, workspace_id)


def resume_subscription(conn, workspace_id: str) -> Dict[str, Any]:
    """Clear scheduled cancellation on active subscription."""
    sub = get_active_subscription(conn, workspace_id)
    if not sub:
        raise ValueError("Subscription not found")

    conn.execute(
        """
        UPDATE subscriptions
        SET cancel_at_period_end = 0
        WHERE id = ?
        """,
        (sub["id"],),
    )
    return get_active_subscription(conn, workspace_id)


def advance_billing(conn, workspace_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Process period roll-overs and generate renewal charges."""
    now_iso = clock.now_iso()
    query = """
        SELECT s.*, p.name as plan_name, p.monthly_price_cents, p.yearly_price_cents,
               p.included_credits_per_period
        FROM subscriptions s
        JOIN plans p ON s.plan_id = p.id
        WHERE s.status IN ('active', 'past_due')
          AND s.current_period_end <= ?
    """
    params: List[Any] = [now_iso]
    if workspace_id:
        query += " AND s.workspace_id = ?"
        params.append(workspace_id)

    subs_due = conn.execute(query, params).fetchall()
    created_invoices = []

    for sub_row in subs_due:
        sub = dict(sub_row)
        interval = sub["interval"]
        end_dt = datetime.fromisoformat(sub["current_period_end"].replace("Z", "+00:00"))
        
        # Determine next interval duration
        if interval == "year":
            next_end_dt = end_dt + timedelta(days=365)
            price_cents = sub["yearly_price_cents"]
        else:
            next_end_dt = end_dt + timedelta(days=30)
            price_cents = sub["monthly_price_cents"]

        next_start_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        next_end_iso = next_end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Create renewal invoice
        lines = [{
            "description": f"Subscription renewal — {sub['plan_name']} ({interval}ly)",
            "quantity": 1,
            "unit_cents": price_cents,
            "amount_cents": price_cents,
        }]

        inv = create_invoice(
            conn,
            workspace_id=sub["workspace_id"],
            lines=lines,
            subscription_id=sub["id"],
            status="paid",
            auto_pay=True,
            period_start=next_start_iso,
            period_end=next_end_iso,
        )
        created_invoices.append(inv)

        # Grant period credits
        grant_credits(
            conn,
            workspace_id=sub["workspace_id"],
            amount=sub["included_credits_per_period"],
            reason="period_grant",
            reference=f"Renewal for {sub['plan_name']}",
        )

        # Update subscription period
        conn.execute(
            """
            UPDATE subscriptions
            SET current_period_start = ?,
                current_period_end = ?,
                status = 'active'
            WHERE id = ?
            """,
            (next_start_iso, next_end_iso, sub["id"]),
        )

    return created_invoices
