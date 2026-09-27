from typing import List, Dict, Any, Optional
from app.db import generate_id
from app.clock import clock


def generate_invoice_number(conn) -> str:
    """Generate sequential invoice number with year prefix, e.g., TLY-2026-00042."""
    now = clock.now()
    year = now.year
    row = conn.execute("SELECT current_val FROM counters WHERE name = 'invoice'").fetchone()
    if row:
        val = int(row["current_val"]) + 1
        conn.execute("UPDATE counters SET current_val = ? WHERE name = 'invoice'", (val,))
    else:
        val = 42
        conn.execute("INSERT INTO counters (name, current_val) VALUES ('invoice', ?)", (val,))
    return f"TLY-{year}-{val:05d}"


def create_invoice(
    conn,
    workspace_id: str,
    lines: List[Dict[str, Any]],
    subscription_id: Optional[str] = None,
    status: str = "paid",
    auto_pay: bool = True,
    payment_method_label: str = "Visa •••• 4242",
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an invoice with itemized line items and optional automatic charge capture."""
    inv_id = generate_id("inv")
    inv_number = generate_invoice_number(conn)
    now_str = created_at or clock.now_iso()

    subtotal = sum(int(item["amount_cents"]) for item in lines)
    tax_cents = 0
    total_cents = max(0, subtotal + tax_cents)

    paid_at = now_str if (status == "paid" or (auto_pay and total_cents >= 0)) else None
    actual_status = "paid" if paid_at else status

    conn.execute(
        """
        INSERT INTO invoices (
            id, number, workspace_id, subscription_id, status,
            subtotal_cents, tax_cents, total_cents,
            period_start, period_end, created_at, paid_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            inv_id,
            inv_number,
            workspace_id,
            subscription_id,
            actual_status,
            subtotal,
            tax_cents,
            total_cents,
            period_start or now_str,
            period_end or now_str,
            now_str,
            paid_at,
        ),
    )

    for line in lines:
        line_id = generate_id("line")
        conn.execute(
            """
            INSERT INTO invoice_lines (id, invoice_id, description, quantity, unit_cents, amount_cents)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                line_id,
                inv_id,
                line["description"],
                line.get("quantity", 1),
                line.get("unit_cents", line["amount_cents"]),
                line["amount_cents"],
            ),
        )

    if actual_status == "paid" and total_cents > 0 and auto_pay:
        charge_id = generate_id("ch")
        conn.execute(
            """
            INSERT INTO charges (id, invoice_id, workspace_id, amount_cents, status, payment_method_label, created_at)
            VALUES (?, ?, ?, ?, 'succeeded', ?, ?)
            """,
            (charge_id, inv_id, workspace_id, total_cents, payment_method_label, now_str),
        )

    invoice_row = conn.execute("SELECT * FROM invoices WHERE id = ?", (inv_id,)).fetchone()
    line_rows = conn.execute("SELECT * FROM invoice_lines WHERE invoice_id = ?", (inv_id,)).fetchall()
    result = dict(invoice_row)
    result["lines"] = [dict(lr) for lr in line_rows]
    return result
