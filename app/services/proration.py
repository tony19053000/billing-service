from datetime import datetime
from typing import Dict, Any
from app.clock import clock


def calculate_proration(
    current_plan: Dict[str, Any],
    new_plan: Dict[str, Any],
    interval: str,
    period_start_iso: str,
    period_end_iso: str,
) -> Dict[str, Any]:
    """Compute prorated cost differences between subscriptions."""
    now = clock.now()
    start = datetime.fromisoformat(period_start_iso.replace("Z", "+00:00"))
    end = datetime.fromisoformat(period_end_iso.replace("Z", "+00:00"))

    total_seconds = max(1.0, (end - start).total_seconds())
    remaining_seconds = max(0.0, (end - now).total_seconds())
    fraction_remaining = min(1.0, max(0.0, remaining_seconds / total_seconds))

    price_key = "yearly_price_cents" if interval == "year" else "monthly_price_cents"
    current_price = current_plan[price_key]
    new_price = new_plan[price_key]

    current_unused_credit = int(round(current_price * fraction_remaining))
    new_plan_cost = int(round(new_price * fraction_remaining))
    net_amount_cents = new_plan_cost - current_unused_credit

    return {
        "fraction_remaining": fraction_remaining,
        "current_unused_credit": current_unused_credit,
        "new_plan_cost": new_plan_cost,
        "net_amount_cents": net_amount_cents,
        "is_upgrade": net_amount_cents > 0,
        "is_downgrade": net_amount_cents < 0,
    }
