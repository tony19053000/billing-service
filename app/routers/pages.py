from typing import Optional, List, Dict, Any
from datetime import timedelta
from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.db import get_db, get_db_connection
from app.clock import clock
from app.auth import get_current_user_optional, get_token_from_request
from app.routers.admin import get_admin_metrics

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(settings.BASE_DIR / "app" / "templates"))

def render_template(request: Request, name: str, context: Optional[Dict[str, Any]] = None):
    ctx = dict(context) if context else {}
    ctx["request"] = request
    return templates.TemplateResponse(request=request, name=name, context=ctx)



def get_portal_context(request: Request):
    """Retrieve authenticated user and primary workspace context for portal views."""
    user = get_current_user_optional(request)
    if not user:
        return None, None, None, None, None, None

    token = get_token_from_request(request)

    with get_db() as conn:
        ws_row = conn.execute(
            """
            SELECT * FROM workspaces
            WHERE owner_id = ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (user["id"],),
        ).fetchone()

        if not ws_row and user.get("role") == "operator":
            ws_row = conn.execute(
                "SELECT * FROM workspaces WHERE id != 'ws_operator_internal' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if not ws_row:
                ws_row = conn.execute("SELECT * FROM workspaces ORDER BY created_at ASC LIMIT 1").fetchone()

        if not ws_row:
            return user, None, None, None, [], token

        workspace = dict(ws_row)

        sub_row = conn.execute(
            """
            SELECT * FROM subscriptions
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workspace["id"],),
        ).fetchone()

        subscription = dict(sub_row) if sub_row else None

        plan = None
        if subscription:
            plan_row = conn.execute("SELECT * FROM plans WHERE id = ?", (subscription["plan_id"],)).fetchone()
            if plan_row:
                plan = dict(plan_row)
        else:
            starter_row = conn.execute("SELECT * FROM plans WHERE id = 'plan_starter'").fetchone()
            if starter_row:
                plan = dict(starter_row)

        ent_rows = conn.execute(
            "SELECT feature_key FROM workspace_entitlements WHERE workspace_id = ?",
            (workspace["id"],),
        ).fetchall()
        entitlements = [r["feature_key"] for r in ent_rows]

        return user, workspace, subscription, plan, entitlements, token


# ==========================================
# PUBLIC MARKETING PAGES
# ==========================================

@router.get("/", response_class=HTMLResponse)
def page_home(request: Request):
    user = get_current_user_optional(request)
    return render_template(request, "public/home.html", {"request": request, "user": user})


@router.get("/pricing", response_class=HTMLResponse)
def page_pricing(request: Request):
    user = get_current_user_optional(request)
    return render_template(request, "public/pricing.html", {"request": request, "user": user})


@router.get("/customers", response_class=HTMLResponse)
def page_customers(request: Request):
    user = get_current_user_optional(request)
    return render_template(request, "public/customers.html", {"request": request, "user": user})


@router.get("/customers/northwind-analytics", response_class=HTMLResponse)
def page_case_study(request: Request):
    user = get_current_user_optional(request)
    return render_template(request, "public/case_study.html", {"request": request, "user": user})


@router.get("/docs", response_class=HTMLResponse)
def page_docs(request: Request):
    user = get_current_user_optional(request)
    return render_template(request, "public/docs.html", {"request": request, "user": user})


@router.get("/changelog", response_class=HTMLResponse)
def page_changelog(request: Request):
    user = get_current_user_optional(request)
    return render_template(request, "public/changelog.html", {"request": request, "user": user})


@router.get("/about", response_class=HTMLResponse)
def page_about(request: Request):
    user = get_current_user_optional(request)
    return render_template(request, "public/about.html", {"request": request, "user": user})


@router.get("/contact", response_class=HTMLResponse)
def page_contact(request: Request):
    user = get_current_user_optional(request)
    return render_template(request, "public/contact.html", {"request": request, "user": user})


@router.get("/status", response_class=HTMLResponse)
def page_status(request: Request):
    user = get_current_user_optional(request)
    return render_template(request, "public/status.html", {"request": request, "user": user})


@router.get("/security", response_class=HTMLResponse)
def page_security(request: Request):
    user = get_current_user_optional(request)
    return render_template(request, "public/security.html", {"request": request, "user": user})


@router.get("/terms", response_class=HTMLResponse)
def page_terms(request: Request):
    user = get_current_user_optional(request)
    return render_template(request, "public/terms.html", {"request": request, "user": user})


@router.get("/privacy", response_class=HTMLResponse)
def page_privacy(request: Request):
    user = get_current_user_optional(request)
    return render_template(request, "public/privacy.html", {"request": request, "user": user})


@router.get("/login", response_class=HTMLResponse)
def page_login(request: Request):
    user = get_current_user_optional(request)
    if user:
        if user.get("role") == "operator":
            return RedirectResponse(url="/admin", status_code=302)
        return RedirectResponse(url="/app", status_code=302)
    return render_template(request, "public/login.html", {"request": request})


@router.get("/signup", response_class=HTMLResponse)
def page_signup(request: Request):
    user = get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/app", status_code=302)
    return render_template(request, "public/signup.html", {"request": request})


@router.get("/forgot", response_class=HTMLResponse)
def page_forgot(request: Request):
    return render_template(request, "public/forgot.html", {"request": request})


# ==========================================
# CUSTOMER BILLING PORTAL (/app)
# ==========================================

@router.get("/app", response_class=HTMLResponse)
def page_portal_overview(request: Request):
    user, ws, sub, plan, ents, token = get_portal_context(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    with get_db() as conn:
        inv_rows = conn.execute(
            """
            SELECT * FROM invoices
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT 5
            """,
            (ws["id"],),
        ).fetchall()
        invoices = [dict(r) for r in inv_rows]

    return render_template(request, 
        "app/overview.html",
        {
            "request": request,
            "user": user,
            "workspace": ws,
            "subscription": sub,
            "plan": plan,
            "entitlements": ents,
            "invoices": invoices,
            "page_id": "overview",
            "token": token,
        },
    )


@router.get("/app/plans", response_class=HTMLResponse)
def page_portal_plans(request: Request):
    user, ws, sub, plan, ents, token = get_portal_context(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    with get_db() as conn:
        p_rows = conn.execute("SELECT * FROM plans ORDER BY sort ASC").fetchall()
        plans_list = []
        for pr in p_rows:
            p_dict = dict(pr)
            feats = conn.execute(
                """
                SELECT f.key, f.name, f.description
                FROM plan_features pf
                JOIN features f ON pf.feature_key = f.key
                WHERE pf.plan_id = ?
                """,
                (pr["id"],),
            ).fetchall()
            p_dict["features"] = [dict(f) for f in feats]
            plans_list.append(p_dict)

    return render_template(request, 
        "app/plans.html",
        {
            "request": request,
            "user": user,
            "workspace": ws,
            "subscription": sub,
            "plan": plan,
            "plans": plans_list,
            "entitlements": ents,
            "page_id": "plans",
            "token": token,
        },
    )


@router.get("/app/usage", response_class=HTMLResponse)
def page_portal_usage(
    request: Request,
    metric: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    user, ws, sub, plan, ents, token = get_portal_context(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    with get_db() as conn:
        q = "SELECT * FROM usage_events WHERE workspace_id = ?"
        params: List[Any] = [ws["id"]]
        if metric:
            q += " AND metric = ?"
            params.append(metric)
        if from_date:
            q += " AND created_at >= ?"
            params.append(from_date)
        if to_date:
            q += " AND created_at <= ?"
            params.append(to_date)
        q += " ORDER BY created_at DESC LIMIT 50"

        ev_rows = conn.execute(q, params).fetchall()
        events = [dict(r) for r in ev_rows]

        totals = {}
        for m in ["api_calls", "exports", "ai_tokens"]:
            row = conn.execute(
                "SELECT SUM(quantity) as qty, SUM(credits_cost) as cost FROM usage_events WHERE workspace_id = ? AND metric = ?",
                (ws["id"], m),
            ).fetchone()
            totals[f"{m}_qty"] = row["qty"] if row and row["qty"] else 0
            totals[f"{m}_cost"] = row["cost"] if row and row["cost"] else 0

    return render_template(request, 
        "app/usage.html",
        {
            "request": request,
            "user": user,
            "workspace": ws,
            "subscription": sub,
            "plan": plan,
            "events": events,
            "metric_totals": totals,
            "selected_metric": metric,
            "filter_from": from_date,
            "filter_to": to_date,
            "page_id": "usage",
            "token": token,
        },
    )


@router.get("/app/credits", response_class=HTMLResponse)
def page_portal_credits(request: Request):
    user, ws, sub, plan, ents, token = get_portal_context(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    with get_db() as conn:
        ledger_rows = conn.execute(
            """
            SELECT * FROM credit_ledger
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (ws["id"],),
        ).fetchall()
        ledger = [dict(r) for r in ledger_rows]

    return render_template(request, 
        "app/credits.html",
        {
            "request": request,
            "user": user,
            "workspace": ws,
            "subscription": sub,
            "plan": plan,
            "ledger": ledger,
            "page_id": "credits",
            "token": token,
        },
    )


@router.get("/app/invoices", response_class=HTMLResponse)
def page_portal_invoices(request: Request):
    user, ws, sub, plan, ents, token = get_portal_context(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    with get_db() as conn:
        inv_rows = conn.execute(
            """
            SELECT * FROM invoices
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            """,
            (ws["id"],),
        ).fetchall()
        invoices = [dict(r) for r in inv_rows]

    return render_template(request, 
        "app/invoices.html",
        {
            "request": request,
            "user": user,
            "workspace": ws,
            "subscription": sub,
            "plan": plan,
            "invoices": invoices,
            "page_id": "invoices",
            "token": token,
        },
    )


@router.get("/app/payment-methods", response_class=HTMLResponse)
def page_portal_payment_methods(request: Request):
    user, ws, sub, plan, ents, token = get_portal_context(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    with get_db() as conn:
        pm_rows = conn.execute(
            """
            SELECT * FROM payment_methods
            WHERE workspace_id = ?
            ORDER BY is_default DESC, created_at DESC
            """,
            (ws["id"],),
        ).fetchall()
        payment_methods = [dict(r) for r in pm_rows]

    return render_template(request, 
        "app/payment_methods.html",
        {
            "request": request,
            "user": user,
            "workspace": ws,
            "subscription": sub,
            "plan": plan,
            "payment_methods": payment_methods,
            "page_id": "payment-methods",
            "token": token,
        },
    )


@router.get("/app/settings", response_class=HTMLResponse)
def page_portal_settings(request: Request):
    user, ws, sub, plan, ents, token = get_portal_context(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    return render_template(request, 
        "app/settings.html",
        {
            "request": request,
            "user": user,
            "workspace": ws,
            "subscription": sub,
            "plan": plan,
            "page_id": "settings",
            "token": token,
        },
    )


@router.get("/app/developers", response_class=HTMLResponse)
def page_portal_developers(request: Request):
    user, ws, sub, plan, ents, token = get_portal_context(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    return render_template(request, 
        "app/developers.html",
        {
            "request": request,
            "user": user,
            "workspace": ws,
            "subscription": sub,
            "plan": plan,
            "token": token,
            "page_id": "developers",
        },
    )


# ==========================================
# OPERATOR CONSOLE (/admin)
# ==========================================

@router.get("/admin", response_class=HTMLResponse)
def page_admin_dashboard(request: Request):
    user = get_current_user_optional(request)
    if not user or user.get("role") != "operator":
        return RedirectResponse(url="/login", status_code=302)

    metrics = get_admin_metrics(user=user)

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT w.*, s.status, s.interval, p.name as plan_name
            FROM workspaces w
            LEFT JOIN subscriptions s ON w.id = s.workspace_id
            LEFT JOIN plans p ON s.plan_id = p.id
            WHERE w.id != 'ws_operator_internal'
            ORDER BY w.created_at DESC
            LIMIT 10
            """
        ).fetchall()
        recent_workspaces = [dict(r) for r in rows]

    return render_template(request, 
        "admin/dashboard.html",
        {
            "request": request,
            "user": user,
            "metrics": metrics,
            "recent_workspaces": recent_workspaces,
            "page_id": "dashboard",
        },
    )


@router.get("/admin/workspaces", response_class=HTMLResponse)
def page_admin_workspaces(request: Request):
    user = get_current_user_optional(request)
    if not user or user.get("role") != "operator":
        return RedirectResponse(url="/login", status_code=302)

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT w.*, s.status as subscription_status, s.interval, p.name as plan_name
            FROM workspaces w
            LEFT JOIN subscriptions s ON w.id = s.workspace_id
            LEFT JOIN plans p ON s.plan_id = p.id
            WHERE w.id != 'ws_operator_internal'
            ORDER BY w.created_at DESC
            """
        ).fetchall()
        workspaces = [dict(r) for r in rows]

    return render_template(request, 
        "admin/workspaces.html",
        {
            "request": request,
            "user": user,
            "workspaces": workspaces,
            "page_id": "workspaces",
        },
    )


@router.get("/admin/workspaces/{workspace_id}", response_class=HTMLResponse)
def page_admin_workspace_detail(request: Request, workspace_id: str):
    user = get_current_user_optional(request)
    if not user or user.get("role") != "operator":
        return RedirectResponse(url="/login", status_code=302)

    with get_db() as conn:
        ws_row = conn.execute(
            """
            SELECT w.*, u.name as owner_name, u.email as owner_email
            FROM workspaces w
            JOIN users u ON w.owner_id = u.id
            WHERE w.id = ?
            """,
            (workspace_id,),
        ).fetchone()

        if not ws_row:
            raise HTTPException(status_code=404, detail="Workspace not found")

        workspace = dict(ws_row)

        sub_row = conn.execute(
            """
            SELECT * FROM subscriptions
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()
        subscription = dict(sub_row) if sub_row else None

        plan = None
        if subscription:
            p_row = conn.execute("SELECT * FROM plans WHERE id = ?", (subscription["plan_id"],)).fetchone()
            if p_row:
                plan = dict(p_row)

        ent_rows = conn.execute(
            "SELECT feature_key FROM workspace_entitlements WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchall()
        entitlements = [r["feature_key"] for r in ent_rows]

        ledger_rows = conn.execute(
            """
            SELECT * FROM credit_ledger
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (workspace_id,),
        ).fetchall()
        ledger = [dict(r) for r in ledger_rows]

        inv_rows = conn.execute(
            """
            SELECT * FROM invoices
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (workspace_id,),
        ).fetchall()
        invoices = [dict(r) for r in inv_rows]

    return render_template(request, 
        "admin/workspace_detail.html",
        {
            "request": request,
            "user": user,
            "workspace": workspace,
            "subscription": subscription,
            "plan": plan,
            "entitlements": entitlements,
            "ledger": ledger,
            "invoices": invoices,
            "page_id": "workspaces",
        },
    )


@router.get("/admin/subscriptions", response_class=HTMLResponse)
def page_admin_subscriptions(request: Request, status: Optional[str] = None):
    user = get_current_user_optional(request)
    if not user or user.get("role") != "operator":
        return RedirectResponse(url="/login", status_code=302)

    with get_db() as conn:
        q = """
            SELECT s.*, w.name as workspace_name, p.name as plan_name
            FROM subscriptions s
            JOIN workspaces w ON s.workspace_id = w.id
            JOIN plans p ON s.plan_id = p.id
        """
        params: List[Any] = []
        if status:
            q += " WHERE s.status = ?"
            params.append(status)
        q += " ORDER BY s.created_at DESC"

        rows = conn.execute(q, params).fetchall()
        subscriptions = [dict(r) for r in rows]

    return render_template(request, 
        "admin/subscriptions.html",
        {
            "request": request,
            "user": user,
            "subscriptions": subscriptions,
            "status_filter": status,
            "page_id": "subscriptions",
        },
    )


@router.get("/admin/invoices", response_class=HTMLResponse)
def page_admin_invoices(request: Request, status: Optional[str] = None):
    user = get_current_user_optional(request)
    if not user or user.get("role") != "operator":
        return RedirectResponse(url="/login", status_code=302)

    with get_db() as conn:
        q = """
            SELECT i.*, w.name as workspace_name
            FROM invoices i
            JOIN workspaces w ON i.workspace_id = w.id
        """
        params: List[Any] = []
        if status:
            q += " WHERE i.status = ?"
            params.append(status)
        q += " ORDER BY i.created_at DESC"

        rows = conn.execute(q, params).fetchall()
        invoices = [dict(r) for r in rows]

    return render_template(request, 
        "admin/invoices.html",
        {
            "request": request,
            "user": user,
            "invoices": invoices,
            "status_filter": status,
            "page_id": "invoices",
        },
    )
