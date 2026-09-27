from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from app.db import get_db
from app.auth import get_current_workspace
from app.clock import clock
from app.services.billing import advance_billing
from app.schemas import ClockAdvanceRequest

router = APIRouter(tags=["Test Clock"])


@router.get("/clock")
def get_clock() -> Dict[str, Any]:
    """Retrieve the current simulated platform timestamp."""
    return {"now": clock.now_iso()}


@router.post("/clock/advance")
def advance_clock(
    req: ClockAdvanceRequest,
    workspace: Dict[str, Any] = Depends(get_current_workspace),
) -> Dict[str, Any]:
    """Advance the platform simulation clock and evaluate renewals for the current workspace."""
    if req.days < 1 or req.days > 400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_advance_days", "message": "Days must be between 1 and 400"}},
        )

    # Move clock forward
    new_dt = clock.advance_days(req.days)
    new_now_str = new_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_db() as conn:
        invoices_created = advance_billing(conn, workspace_id=workspace["id"])

    return {
        "now": new_now_str,
        "invoices_created": invoices_created,
    }
