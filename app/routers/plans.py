from typing import Dict, Any, List
from fastapi import APIRouter, Depends
from app.db import get_db
from app.auth import get_current_workspace
from app.services.entitlements import get_workspace_entitlements, check_feature_allowed

router = APIRouter(tags=["Plans & Entitlements"])


@router.get("/plans")
def list_plans() -> List[Dict[str, Any]]:
    """Retrieve all available subscription plans with feature mappings."""
    with get_db() as conn:
        plan_rows = conn.execute("SELECT * FROM plans ORDER BY sort ASC").fetchall()
        result = []
        for p in plan_rows:
            p_dict = dict(p)
            feature_rows = conn.execute(
                """
                SELECT f.key, f.name, f.description
                FROM plan_features pf
                JOIN features f ON pf.feature_key = f.key
                WHERE pf.plan_id = ?
                ORDER BY f.key ASC
                """,
                (p["id"],),
            ).fetchall()
            p_dict["features"] = [dict(f) for f in feature_rows]
            result.append(p_dict)
        return result


@router.get("/workspace/entitlements")
def get_entitlements(workspace: Dict[str, Any] = Depends(get_current_workspace)) -> Dict[str, Any]:
    """Retrieve the cached active feature set granted to the workspace."""
    with get_db() as conn:
        features = get_workspace_entitlements(conn, workspace["id"])
        return {"features": features}


@router.get("/workspace/features/{key}/check")
def check_feature(key: str, workspace: Dict[str, Any] = Depends(get_current_workspace)) -> Dict[str, Any]:
    """Product feature-gate entitlement check."""
    with get_db() as conn:
        allowed = check_feature_allowed(conn, workspace["id"], key)
        return {"allowed": allowed, "feature_key": key}
