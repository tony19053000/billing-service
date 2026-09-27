from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, Response, status
from fastapi.responses import HTMLResponse
from app.db import get_db, generate_id
from app.auth import get_current_workspace
from app.clock import clock
from app.schemas import PaymentMethodCreateRequest

router = APIRouter(tags=["Invoices & Payment Methods"])


@router.get("/invoices")
def list_invoices(workspace: Dict[str, Any] = Depends(get_current_workspace)) -> List[Dict[str, Any]]:
    """List all issued invoices for the current workspace."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, number, workspace_id, subscription_id, status,
                   subtotal_cents, tax_cents, total_cents, period_start, period_end,
                   created_at, paid_at
            FROM invoices
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            """,
            (workspace["id"],),
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: str, workspace: Dict[str, Any] = Depends(get_current_workspace)) -> Dict[str, Any]:
    """Retrieve full invoice specification including line items and charge receipts."""
    with get_db() as conn:
        inv_row = conn.execute(
            """
            SELECT * FROM invoices
            WHERE id = ? AND workspace_id = ?
            """,
            (invoice_id, workspace["id"]),
        ).fetchone()
        if not inv_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "invoice_not_found", "message": "Invoice not found"}},
            )

        line_rows = conn.execute(
            "SELECT * FROM invoice_lines WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchall()

        charge_rows = conn.execute(
            "SELECT * FROM charges WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchall()

        result = dict(inv_row)
        result["lines"] = [dict(lr) for lr in line_rows]
        result["charges"] = [dict(cr) for cr in charge_rows]
        return result


@router.get("/invoices/{invoice_id}/pdf", response_class=HTMLResponse)
def get_invoice_pdf(invoice_id: str, workspace: Dict[str, Any] = Depends(get_current_workspace)) -> str:
    """Render a standalone, print-optimized invoice view."""
    with get_db() as conn:
        inv_row = conn.execute(
            "SELECT * FROM invoices WHERE id = ? AND workspace_id = ?",
            (invoice_id, workspace["id"]),
        ).fetchone()
        if not inv_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "invoice_not_found", "message": "Invoice not found"}},
            )
        lines = conn.execute("SELECT * FROM invoice_lines WHERE invoice_id = ?", (invoice_id,)).fetchall()

    inv = dict(inv_row)
    subtotal_fmt = f"${inv['subtotal_cents'] / 100:.2f}"
    tax_fmt = f"${inv['tax_cents'] / 100:.2f}"
    total_fmt = f"${inv['total_cents'] / 100:.2f}"
    status_label = inv["status"].upper()

    line_items_html = ""
    for line in lines:
        amount_fmt = f"${line['amount_cents'] / 100:.2f}"
        unit_fmt = f"${line['unit_cents'] / 100:.2f}"
        line_items_html += f"""
        <tr>
            <td style="padding:12px 16px;border-bottom:1px solid #E4E7EC;color:#0B1220;">{line['description']}</td>
            <td style="padding:12px 16px;border-bottom:1px solid #E4E7EC;text-align:center;color:#5B6475;">{line['quantity']}</td>
            <td style="padding:12px 16px;border-bottom:1px solid #E4E7EC;text-align:right;font-family:'JetBrains Mono',monospace;color:#5B6475;">{unit_fmt}</td>
            <td style="padding:12px 16px;border-bottom:1px solid #E4E7EC;text-align:right;font-family:'JetBrains Mono',monospace;font-weight:600;color:#0B1220;">{amount_fmt}</td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8"/>
    <title>Invoice {inv['number']} — Tallyo</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: #FFFFFF;
            color: #0B1220;
            margin: 0;
            padding: 40px;
        }}
        .invoice-card {{
            max-width: 800px;
            margin: 0 auto;
            border: 1px solid #E4E7EC;
            border-radius: 8px;
            padding: 48px;
            box-shadow: 0 1px 3px rgba(16,24,40,0.06);
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 1px solid #E4E7EC;
            padding-bottom: 24px;
            margin-bottom: 32px;
        }}
        .brand {{
            font-size: 24px;
            font-weight: 700;
            color: #4F46E5;
            letter-spacing: -0.02em;
        }}
        .status-pill {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            background: #ECFDF3;
            color: #027A48;
            border: 1px solid #A6F4C5;
        }}
        .grid-meta {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
            margin-bottom: 32px;
            font-size: 14px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 32px;
        }}
        th {{
            background: #F8F9FC;
            padding: 12px 16px;
            text-align: left;
            font-size: 12px;
            font-weight: 600;
            color: #5B6475;
            text-transform: uppercase;
            border-bottom: 1px solid #E4E7EC;
        }}
        .totals {{
            margin-left: auto;
            width: 320px;
            font-size: 14px;
        }}
        .totals-row {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            color: #5B6475;
        }}
        .totals-row.grand {{
            font-size: 18px;
            font-weight: 700;
            color: #0B1220;
            border-top: 2px solid #0B1220;
            padding-top: 12px;
            margin-top: 8px;
        }}
        @media print {{
            body {{ padding: 0; }}
            .invoice-card {{ border: none; box-shadow: none; padding: 20px; }}
            .no-print {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="no-print" style="max-width:800px;margin:0 auto 20px;text-align:right;">
        <button onclick="window.print()" style="background:#4F46E5;color:#FFF;border:none;padding:8px 16px;border-radius:6px;font-size:14px;font-weight:500;cursor:pointer;">
            Print / Save as PDF
        </button>
    </div>
    <div class="invoice-card">
        <div class="header">
            <div>
                <div class="brand">Tallyo</div>
                <div style="font-size:13px;color:#5B6475;margin-top:4px;">Billing & Metering Infrastructure Inc.</div>
                <div style="font-size:13px;color:#5B6475;">100 Montgomery St, Suite 1400, San Francisco, CA</div>
            </div>
            <div style="text-align:right;">
                <span class="status-pill">{status_label}</span>
                <div style="font-family:'JetBrains Mono',monospace;font-size:18px;font-weight:700;margin-top:12px;">{inv['number']}</div>
                <div style="font-size:13px;color:#5B6475;margin-top:4px;">Date: {inv['created_at'][:10]}</div>
            </div>
        </div>

        <div class="grid-meta">
            <div>
                <div style="font-size:12px;font-weight:600;color:#5B6475;text-transform:uppercase;margin-bottom:6px;">Billed To</div>
                <div style="font-weight:600;">{workspace['name']}</div>
                <div style="color:#5B6475;">{workspace['billing_email']}</div>
                <div style="color:#5B6475;">Country: {workspace['country']}</div>
                {f'<div style="color:#5B6475;">Tax ID: {workspace["tax_id"]}</div>' if workspace.get('tax_id') else ''}
            </div>
            <div style="text-align:right;">
                <div style="font-size:12px;font-weight:600;color:#5B6475;text-transform:uppercase;margin-bottom:6px;">Payment Terms</div>
                <div>Charged automatically upon issue</div>
                <div style="color:#5B6475;">Period: {inv['period_start'][:10]} to {inv['period_end'][:10]}</div>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Description</th>
                    <th style="text-align:center;">Qty</th>
                    <th style="text-align:right;">Unit Price</th>
                    <th style="text-align:right;">Amount</th>
                </tr>
            </thead>
            <tbody>
                {line_items_html}
            </tbody>
        </table>

        <div class="totals">
            <div class="totals-row">
                <span>Subtotal</span>
                <span style="font-family:'JetBrains Mono',monospace;">{subtotal_fmt}</span>
            </div>
            <div class="totals-row">
                <span>Tax</span>
                <span style="font-family:'JetBrains Mono',monospace;">{tax_fmt}</span>
            </div>
            <div class="totals-row grand">
                <span>Total Due</span>
                <span style="font-family:'JetBrains Mono',monospace;">{total_fmt}</span>
            </div>
        </div>
    </div>
</body>
</html>"""
    return html


@router.get("/charges")
def list_charges(workspace: Dict[str, Any] = Depends(get_current_workspace)) -> List[Dict[str, Any]]:
    """List all settled payment charges for the workspace."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT c.*, i.number as invoice_number
            FROM charges c
            JOIN invoices i ON c.invoice_id = i.id
            WHERE c.workspace_id = ?
            ORDER BY c.created_at DESC
            """,
            (workspace["id"],),
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/payment-methods")
def list_payment_methods(workspace: Dict[str, Any] = Depends(get_current_workspace)) -> List[Dict[str, Any]]:
    """List saved payment cards for the workspace."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM payment_methods WHERE workspace_id = ? ORDER BY is_default DESC, created_at DESC",
            (workspace["id"],),
        ).fetchall()
        return [dict(r) for r in rows]


@router.post("/payment-methods", status_code=status.HTTP_201_CREATED)
def create_payment_method(
    req: PaymentMethodCreateRequest,
    workspace: Dict[str, Any] = Depends(get_current_workspace),
) -> Dict[str, Any]:
    """Register a new virtual card entry."""
    with get_db() as conn:
        existing_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM payment_methods WHERE workspace_id = ?",
            (workspace["id"],),
        ).fetchone()["cnt"]

        is_default = 1 if existing_count == 0 else 0
        pm_id = generate_id("pm")
        now_str = clock.now_iso()

        conn.execute(
            """
            INSERT INTO payment_methods (id, workspace_id, brand, last4, exp_month, exp_year, is_default, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (pm_id, workspace["id"], req.brand, req.last4, req.exp_month, req.exp_year, is_default, now_str),
        )

        row = conn.execute("SELECT * FROM payment_methods WHERE id = ?", (pm_id,)).fetchone()
        return dict(row)


@router.delete("/payment-methods/{pm_id}")
def delete_payment_method(pm_id: str, workspace: Dict[str, Any] = Depends(get_current_workspace)) -> Dict[str, Any]:
    """Remove a saved card."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM payment_methods WHERE id = ? AND workspace_id = ?", (pm_id, workspace["id"])).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "payment_method_not_found", "message": "Payment method not found"}},
            )
        conn.execute("DELETE FROM payment_methods WHERE id = ?", (pm_id,))
        return {"status": "ok"}


@router.post("/payment-methods/{pm_id}/default")
def set_default_payment_method(pm_id: str, workspace: Dict[str, Any] = Depends(get_current_workspace)) -> Dict[str, Any]:
    """Designate primary payment method for upcoming subscription renewals."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM payment_methods WHERE id = ? AND workspace_id = ?", (pm_id, workspace["id"])).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "payment_method_not_found", "message": "Payment method not found"}},
            )
        conn.execute("UPDATE payment_methods SET is_default = 0 WHERE workspace_id = ?", (workspace["id"],))
        conn.execute("UPDATE payment_methods SET is_default = 1 WHERE id = ?", (pm_id,))
        return {"status": "ok"}
