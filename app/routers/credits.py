from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status
from app.db import get_db
from app.auth import get_current_workspace
from app.services.credits import get_credit_balance, get_credit_ledger, grant_credits
from app.services.invoices import create_invoice
from app.schemas import TopUpCreditsRequest

router = APIRouter(tags=["Credits & Top-Ups"])


@router.get("/credits")
def get_credits(workspace: Dict[str, Any] = Depends(get_current_workspace)) -> Dict[str, Any]:
    """Retrieve current credit balance and recent ledger transaction history."""
    with get_db() as conn:
        balance = get_credit_balance(conn, workspace["id"])
        ledger = get_credit_ledger(conn, workspace["id"])
        return {
            "balance": balance,
            "ledger": ledger,
        }


@router.post("/credits/top-up", status_code=status.HTTP_201_CREATED)
def top_up_credits(
    req: TopUpCreditsRequest,
    workspace: Dict[str, Any] = Depends(get_current_workspace),
) -> Dict[str, Any]:
    """Purchase additional usage credits in packs of 5,000 for $10.00."""
    if req.credits % 5000 != 0 or req.credits <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_credit_pack", "message": "Credits must be purchased in increments of 5,000"}},
        )

    packs = req.credits // 5000
    price_cents = packs * 1000  # $10 per 5k credits

    with get_db() as conn:
        lines = [{
            "description": f"Credit Pack Top-Up ({req.credits:,} credits)",
            "quantity": packs,
            "unit_cents": 1000,
            "amount_cents": price_cents,
        }]

        inv = create_invoice(
            conn,
            workspace_id=workspace["id"],
            lines=lines,
            status="paid",
            auto_pay=True,
        )

        grant_credits(
            conn,
            workspace_id=workspace["id"],
            amount=req.credits,
            reason="top_up",
            reference=f"Invoice {inv['number']}",
        )

        new_balance = get_credit_balance(conn, workspace["id"])
        return {
            "credits_added": req.credits,
            "balance": new_balance,
            "invoice": inv,
        }
