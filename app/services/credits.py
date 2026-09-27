from typing import Optional, List, Dict, Any
from app.db import generate_id
from app.clock import clock


def get_credit_balance(conn, workspace_id: str) -> int:
    """Fetch the active credit balance for a workspace."""
    row = conn.execute("SELECT credit_balance FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
    if row:
        return int(row["credit_balance"])
    return 0


def grant_credits(
    conn,
    workspace_id: str,
    amount: int,
    reason: str,
    reference: Optional[str] = None,
    created_at: Optional[str] = None,
) -> None:
    """Credit a workspace balance and write a positive ledger entry."""
    now_str = created_at or clock.now_iso()
    ledger_id = generate_id("cr")
    conn.execute(
        "UPDATE workspaces SET credit_balance = credit_balance + ? WHERE id = ?",
        (amount, workspace_id),
    )
    conn.execute(
        """
        INSERT INTO credit_ledger (id, workspace_id, delta, reason, reference, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ledger_id, workspace_id, amount, reason, reference or "", now_str),
    )


def deduct_credits(
    conn,
    workspace_id: str,
    amount: int,
    reason: str,
    reference: Optional[str] = None,
    created_at: Optional[str] = None,
) -> bool:
    """Attempt to deduct credits from workspace balance if sufficient."""
    now_str = created_at or clock.now_iso()
    row = conn.execute("SELECT credit_balance FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
    if not row or int(row["credit_balance"]) < amount:
        return False
    ledger_id = generate_id("cr")
    conn.execute(
        "UPDATE workspaces SET credit_balance = credit_balance - ? WHERE id = ?",
        (amount, workspace_id),
    )
    conn.execute(
        """
        INSERT INTO credit_ledger (id, workspace_id, delta, reason, reference, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ledger_id, workspace_id, -amount, reason, reference or "", now_str),
    )
    return True


def record_credit_adjustment(
    conn,
    workspace_id: str,
    delta: int,
    reason: str,
    reference: Optional[str] = None,
    created_at: Optional[str] = None,
) -> int:
    """Operator manual balance adjustment (positive or negative)."""
    now_str = created_at or clock.now_iso()
    ledger_id = generate_id("cr")
    conn.execute(
        "UPDATE workspaces SET credit_balance = credit_balance + ? WHERE id = ?",
        (delta, workspace_id),
    )
    conn.execute(
        """
        INSERT INTO credit_ledger (id, workspace_id, delta, reason, reference, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ledger_id, workspace_id, delta, reason, reference or "operator_adjustment", now_str),
    )
    return get_credit_balance(conn, workspace_id)


def get_credit_ledger(conn, workspace_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieve chronologically ordered credit ledger entries."""
    rows = conn.execute(
        """
        SELECT id, workspace_id, delta, reason, reference, created_at
        FROM credit_ledger
        WHERE workspace_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (workspace_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]
