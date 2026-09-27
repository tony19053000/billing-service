import secrets
from datetime import timedelta
from typing import Optional, Dict, Any
import bcrypt
from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.db import get_db, get_db_connection
from app.clock import clock

security_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash plaintext password with bcrypt salt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify plaintext password against bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_session(conn, user_id: str, days: int = 30) -> str:
    """Generate and store an opaque session token."""
    token = f"tly_sess_{secrets.token_hex(24)}"
    now = clock.now()
    created_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    expires_at = (now + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT INTO sessions (token, user_id, created_at, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        (token, user_id, created_at, expires_at),
    )
    return token


def destroy_session(conn, token: str) -> None:
    """Delete a session token."""
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def get_token_from_request(request: Request) -> Optional[str]:
    """Extract bearer token from Authorization header or HttpOnly cookie."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    cookie_token = request.cookies.get("tallyo_session")
    if cookie_token:
        return cookie_token.strip()
    return None


def get_current_user_optional(request: Request) -> Optional[Dict[str, Any]]:
    """Return the authenticated user if present, or None."""
    token = get_token_from_request(request)
    if not token:
        return None
    conn = get_db_connection()
    try:
        now_str = clock.now_iso()
        row = conn.execute(
            """
            SELECT u.id, u.name, u.email, u.role, u.created_at
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (token, now_str),
        ).fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def get_current_user(request: Request) -> Dict[str, Any]:
    """Enforce authentication and return the active user."""
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "Authentication required"}},
        )
    return user


def get_current_workspace(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Retrieve the primary workspace associated with the active user."""
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT id, name, slug, owner_id, billing_email, tax_id, country, credit_balance, created_at
            FROM workspaces
            WHERE owner_id = ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (user["id"],),
        ).fetchone()
        if not row:
            # If user is operator, retrieve first workspace or raise
            if user["role"] == "operator":
                first_ws = conn.execute(
                    "SELECT id, name, slug, owner_id, billing_email, tax_id, country, credit_balance, created_at FROM workspaces ORDER BY created_at ASC LIMIT 1"
                ).fetchone()
                if first_ws:
                    return dict(first_ws)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "workspace_not_found", "message": "No workspace found for user"}},
            )
        return dict(row)
    finally:
        conn.close()


def require_operator(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Enforce operator role privileges."""
    if user.get("role") != "operator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Operator privileges required"}},
        )
    return user
