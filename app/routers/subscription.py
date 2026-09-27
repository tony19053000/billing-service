from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status
from app.db import get_db
from app.auth import get_current_workspace
from app.services.billing import (
    get_active_subscription,
    change_plan,
    cancel_subscription,
    resume_subscription,
)
from app.schemas import ChangePlanRequest, CancelSubscriptionRequest

router = APIRouter(tags=["Subscriptions"])


@router.get("/subscription")
def get_subscription(workspace: Dict[str, Any] = Depends(get_current_workspace)) -> Dict[str, Any]:
    with get_db() as conn:
        sub = get_active_subscription(conn, workspace["id"])
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "subscription_not_found", "message": "No active subscription found"}},
            )
        return sub


@router.post("/subscription/change-plan")
def post_change_plan(
    req: ChangePlanRequest,
    workspace: Dict[str, Any] = Depends(get_current_workspace),
) -> Dict[str, Any]:
    with get_db() as conn:
        try:
            return change_plan(
                conn,
                workspace_id=workspace["id"],
                new_plan_id=req.plan_id,
                interval=req.interval,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "invalid_plan_change", "message": str(e)}},
            )


@router.post("/subscription/cancel")
def post_cancel(
    req: CancelSubscriptionRequest,
    workspace: Dict[str, Any] = Depends(get_current_workspace),
) -> Dict[str, Any]:
    with get_db() as conn:
        try:
            sub = cancel_subscription(conn, workspace["id"], at_period_end=req.at_period_end)
            return sub
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "cancel_error", "message": str(e)}},
            )


@router.post("/subscription/resume")
def post_resume(workspace: Dict[str, Any] = Depends(get_current_workspace)) -> Dict[str, Any]:
    with get_db() as conn:
        try:
            sub = resume_subscription(conn, workspace["id"])
            return sub
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "resume_error", "message": str(e)}},
            )
