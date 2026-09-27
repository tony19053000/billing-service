from typing import List, Dict, Any
from app.clock import clock


def recompute_entitlements(conn, workspace_id: str, plan_id: str) -> None:
    """Synchronize entitlements based on current plan."""
    now_str = clock.now_iso()
    feature_rows = conn.execute(
        """
        SELECT feature_key
        FROM plan_features
        WHERE plan_id = ?
        """,
        (plan_id,),
    ).fetchall()

    for row in feature_rows:
        conn.execute(
            """
            INSERT OR IGNORE INTO workspace_entitlements (workspace_id, feature_key, granted_at)
            VALUES (?, ?, ?)
            """,
            (workspace_id, row["feature_key"], now_str),
        )


def get_workspace_entitlements(conn, workspace_id: str) -> List[str]:
    """Retrieve granted feature keys for a workspace."""
    rows = conn.execute(
        """
        SELECT feature_key
        FROM workspace_entitlements
        WHERE workspace_id = ?
        ORDER BY feature_key ASC
        """,
        (workspace_id,),
    ).fetchall()
    return [r["feature_key"] for r in rows]


def check_feature_allowed(conn, workspace_id: str, feature_key: str) -> bool:
    """Verify if a specific feature entitlement is active."""
    row = conn.execute(
        """
        SELECT 1
        FROM workspace_entitlements
        WHERE workspace_id = ? AND feature_key = ?
        """,
        (workspace_id, feature_key),
    ).fetchone()
    return row is not None
