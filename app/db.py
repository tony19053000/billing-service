import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from app.config import settings


def generate_id(prefix: str) -> str:
    """Generate a prefixed random identifier like Stripe's."""
    random_part = secrets.token_hex(10)
    return f"{prefix}_{random_part}"


def get_db_connection() -> sqlite3.Connection:
    """Create and configure a SQLite connection."""
    db_path = settings.db_file_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database operations."""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    owner_id TEXT NOT NULL REFERENCES users(id),
    billing_email TEXT NOT NULL,
    tax_id TEXT,
    country TEXT NOT NULL DEFAULT 'US',
    credit_balance INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    monthly_price_cents INTEGER NOT NULL,
    yearly_price_cents INTEGER NOT NULL,
    included_credits_per_period INTEGER NOT NULL,
    seats INTEGER NOT NULL,
    description TEXT NOT NULL,
    sort INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS features (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_features (
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    feature_key TEXT NOT NULL REFERENCES features(key) ON DELETE CASCADE,
    PRIMARY KEY (plan_id, feature_key)
);

CREATE TABLE IF NOT EXISTS workspace_entitlements (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    feature_key TEXT NOT NULL REFERENCES features(key) ON DELETE CASCADE,
    granted_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, feature_key)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    plan_id TEXT NOT NULL REFERENCES plans(id),
    interval TEXT NOT NULL DEFAULT 'month',
    status TEXT NOT NULL DEFAULT 'active',
    current_period_start TEXT NOT NULL,
    current_period_end TEXT NOT NULL,
    cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
    canceled_at TEXT,
    pending_plan_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    number TEXT UNIQUE NOT NULL,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    subscription_id TEXT REFERENCES subscriptions(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'open',
    subtotal_cents INTEGER NOT NULL DEFAULT 0,
    tax_cents INTEGER NOT NULL DEFAULT 0,
    total_cents INTEGER NOT NULL DEFAULT 0,
    period_start TEXT,
    period_end TEXT,
    created_at TEXT NOT NULL,
    paid_at TEXT
);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_cents INTEGER NOT NULL DEFAULT 0,
    amount_cents INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS charges (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    amount_cents INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'succeeded',
    payment_method_label TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_ledger (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL,
    reference TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_events (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    metric TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    credits_cost INTEGER NOT NULL,
    idempotency_key TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT NOT NULL,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    request_hash TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (key, workspace_id)
);

CREATE TABLE IF NOT EXISTS payment_methods (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    brand TEXT NOT NULL,
    last4 TEXT NOT NULL,
    exp_month INTEGER NOT NULL,
    exp_year INTEGER NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clock (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    offset_seconds INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS counters (
    name TEXT PRIMARY KEY,
    current_val INTEGER NOT NULL DEFAULT 0
);
"""


def init_db() -> None:
    """Initialize SQLite database tables idempotently."""
    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)
        # Ensure clock row exists
        now_iso = "2026-09-27T00:00:00Z"
        conn.execute(
            """
            INSERT OR IGNORE INTO clock (id, offset_seconds, updated_at)
            VALUES (1, 0, ?)
            """,
            (now_iso,),
        )
        # Ensure invoice counter exists
        conn.execute(
            """
            INSERT OR IGNORE INTO counters (name, current_val)
            VALUES ('invoice', 42)
            """
        )
