import re
from datetime import timedelta
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Response, status
from app.db import get_db, generate_id
from app.auth import (
    hash_password,
    verify_password,
    create_session,
    destroy_session,
    get_token_from_request,
    get_current_user,
    get_current_workspace,
)
from app.clock import clock
from app.services.credits import grant_credits
from app.services.entitlements import recompute_entitlements
from app.schemas import SignupRequest, LoginRequest, WorkspaceUpdateRequest

router = APIRouter(tags=["Authentication & Workspace"])


def slugify(text: str) -> str:
    """Generate a clean URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-") or "workspace"


@router.post("/auth/signup", status_code=status.HTTP_201_CREATED)
def signup(req: SignupRequest, response: Response) -> Dict[str, Any]:
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (req.email,)).fetchone()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": {"code": "email_exists", "message": "Email is already registered"}},
            )

        user_id = generate_id("usr")
        now_str = clock.now_iso()
        pw_hash = hash_password(req.password)

        conn.execute(
            """
            INSERT INTO users (id, name, email, password_hash, role, created_at)
            VALUES (?, ?, ?, ?, 'member', ?)
            """,
            (user_id, req.name, req.email, pw_hash, now_str),
        )

        base_slug = slugify(req.workspace_name)
        slug = base_slug
        collision_count = 1
        while conn.execute("SELECT id FROM workspaces WHERE slug = ?", (slug,)).fetchone():
            slug = f"{base_slug}-{collision_count}"
            collision_count += 1

        ws_id = generate_id("ws")
        conn.execute(
            """
            INSERT INTO workspaces (id, name, slug, owner_id, billing_email, tax_id, country, credit_balance, created_at)
            VALUES (?, ?, ?, ?, ?, NULL, 'US', 0, ?)
            """,
            (ws_id, req.workspace_name, slug, user_id, req.email, now_str),
        )

        # Create Starter subscription
        sub_id = generate_id("sub")
        period_start = now_str
        period_end = (clock.now() + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

        conn.execute(
            """
            INSERT INTO subscriptions (
                id, workspace_id, plan_id, interval, status,
                current_period_start, current_period_end, cancel_at_period_end, created_at
            ) VALUES (?, ?, 'plan_starter', 'month', 'active', ?, ?, 0, ?)
            """,
            (sub_id, ws_id, period_start, period_end, now_str),
        )

        # Grant 1,000 Starter credits
        grant_credits(
            conn,
            workspace_id=ws_id,
            amount=1000,
            reason="period_grant",
            reference="Starter plan initial grant",
            created_at=now_str,
        )

        # Grant Starter entitlements
        recompute_entitlements(conn, ws_id, "plan_starter")

        # Session token
        token = create_session(conn, user_id)
        response.set_cookie(
            key="tallyo_session",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=30 * 86400,
        )

        user_row = conn.execute("SELECT id, name, email, role, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        ws_row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()

        return {
            "user": dict(user_row),
            "workspace": dict(ws_row),
            "token": token,
        }


@router.post("/auth/login")
def login(req: LoginRequest, response: Response) -> Dict[str, Any]:
    with get_db() as conn:
        user_row = conn.execute("SELECT * FROM users WHERE email = ?", (req.email,)).fetchone()
        if not user_row or not verify_password(req.password, user_row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"code": "invalid_credentials", "message": "Invalid email or password"}},
            )

        token = create_session(conn, user_row["id"])
        response.set_cookie(
            key="tallyo_session",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=30 * 86400,
        )

        user_data = {
            "id": user_row["id"],
            "name": user_row["name"],
            "email": user_row["email"],
            "role": user_row["role"],
            "created_at": user_row["created_at"],
        }
        return {"user": user_data, "token": token}


@router.post("/auth/logout")
def logout(response: Response, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
    response.delete_cookie("tallyo_session")
    return {"status": "ok"}


@router.get("/me")
def me(
    user: Dict[str, Any] = Depends(get_current_user),
    workspace: Dict[str, Any] = Depends(get_current_workspace),
) -> Dict[str, Any]:
    return {"user": user, "workspace": workspace}


@router.get("/workspace")
def get_workspace(workspace: Dict[str, Any] = Depends(get_current_workspace)) -> Dict[str, Any]:
    return workspace


@router.patch("/workspace")
def update_workspace(
    req: WorkspaceUpdateRequest,
    workspace: Dict[str, Any] = Depends(get_current_workspace),
) -> Dict[str, Any]:
    with get_db() as conn:
        updates = []
        params = []
        if req.name is not None:
            updates.append("name = ?")
            params.append(req.name)
        if req.billing_email is not None:
            updates.append("billing_email = ?")
            params.append(req.billing_email)
        if req.tax_id is not None:
            updates.append("tax_id = ?")
            params.append(req.tax_id)
        if req.country is not None:
            updates.append("country = ?")
            params.append(req.country)

        if updates:
            params.append(workspace["id"])
            conn.execute(f"UPDATE workspaces SET {', '.join(updates)} WHERE id = ?", params)

        updated_row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace["id"],)).fetchone()
        return dict(updated_row)
