from datetime import datetime, timezone, timedelta
import random
from typing import List, Dict, Any
from app.config import settings
from app.db import get_db, generate_id
from app.auth import hash_password
from app.clock import clock
from app.services.entitlements import recompute_entitlements


PLANS_DATA = [
    {
        "id": "plan_starter",
        "name": "Starter",
        "monthly_price_cents": 0,
        "yearly_price_cents": 0,
        "included_credits_per_period": 1000,
        "seats": 2,
        "description": "Essential billing foundation for early-stage products and developer sandboxes.",
        "sort": 1,
    },
    {
        "id": "plan_pro",
        "name": "Pro",
        "monthly_price_cents": 4900,
        "yearly_price_cents": 49000,
        "included_credits_per_period": 20000,
        "seats": 10,
        "description": "Advanced metering, webhooks, and analytics for growing software teams.",
        "sort": 2,
    },
    {
        "id": "plan_business",
        "name": "Business",
        "monthly_price_cents": 19900,
        "yearly_price_cents": 199000,
        "included_credits_per_period": 100000,
        "seats": -1,
        "description": "Enterprise-scale volume, unified audit logs, custom domains, and dedicated priority support.",
        "sort": 3,
    },
]

FEATURES_DATA = [
    {
        "key": "api_access",
        "name": "API Access",
        "description": "Direct REST API access for usage ingestion and billing queries.",
    },
    {
        "key": "webhooks",
        "name": "Webhooks",
        "description": "Real-time HTTP callbacks for invoice paid, subscription modified, and credit balance events.",
    },
    {
        "key": "sso_saml",
        "name": "SSO & SAML",
        "description": "Single Sign-On authentication via Okta, Google Workspace, and Azure AD.",
    },
    {
        "key": "audit_log",
        "name": "Audit Logs",
        "description": "Tamper-evident activity logging across team actions and subscription modifications.",
    },
    {
        "key": "priority_support",
        "name": "Priority Support",
        "description": "Dedicated support engineers with 1-hour SLA response guarantees.",
    },
    {
        "key": "custom_domains",
        "name": "Custom Domains",
        "description": "Custom branded portal hostname with automatic TLS certificate provisioning.",
    },
    {
        "key": "advanced_analytics",
        "name": "Advanced Analytics",
        "description": "Cohort retention, MRR breakdown, expansion revenue, and credit drawdown trends.",
    },
    {
        "key": "data_export",
        "name": "Data Export",
        "description": "Scheduled and on-demand CSV and JSON exports for accounting reconciliation.",
    },
]

PLAN_FEATURES_MAPPING = {
    "plan_starter": ["api_access"],
    "plan_pro": ["api_access", "webhooks", "advanced_analytics", "data_export"],
    "plan_business": [
        "api_access",
        "webhooks",
        "sso_saml",
        "audit_log",
        "priority_support",
        "custom_domains",
        "advanced_analytics",
        "data_export",
    ],
}


def seed_database() -> None:
    """Populate database with plans, features, and realistic workspace billing histories."""
    with get_db() as conn:
        # 1. Plans
        for plan in PLANS_DATA:
            conn.execute(
                """
                INSERT OR REPLACE INTO plans (
                    id, name, monthly_price_cents, yearly_price_cents,
                    included_credits_per_period, seats, description, sort
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan["id"],
                    plan["name"],
                    plan["monthly_price_cents"],
                    plan["yearly_price_cents"],
                    plan["included_credits_per_period"],
                    plan["seats"],
                    plan["description"],
                    plan["sort"],
                ),
            )

        # 2. Features
        for feat in FEATURES_DATA:
            conn.execute(
                """
                INSERT OR REPLACE INTO features (key, name, description)
                VALUES (?, ?, ?)
                """,
                (feat["key"], feat["name"], feat["description"]),
            )

        # 3. Plan Features
        for plan_id, keys in PLAN_FEATURES_MAPPING.items():
            for key in keys:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO plan_features (plan_id, feature_key)
                    VALUES (?, ?)
                    """,
                    (plan_id, key),
                )

        # 4. Operator Account
        op_row = conn.execute("SELECT id FROM users WHERE email = ?", (settings.ADMIN_EMAIL,)).fetchone()
        if not op_row:
            op_id = "usr_operator_001"
            op_hash = hash_password(settings.ADMIN_PASSWORD)
            created_at = "2025-01-01T00:00:00Z"
            conn.execute(
                """
                INSERT INTO users (id, name, email, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, 'operator', ?)
                """,
                (op_id, "Platform Operations", settings.ADMIN_EMAIL, op_hash, created_at),
            )
            # Create operator internal workspace
            ws_id = "ws_operator_internal"
            conn.execute(
                """
                INSERT INTO workspaces (id, name, slug, owner_id, billing_email, tax_id, country, credit_balance, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'US', 500000, ?)
                """,
                (ws_id, "Tallyo Platform Operations", "tallyo-ops", op_id, settings.ADMIN_EMAIL, "US-987654321", created_at),
            )
            recompute_entitlements(conn, ws_id, "plan_business")

        # Check if customer workspaces already seeded
        existing_workspaces = conn.execute("SELECT COUNT(*) as cnt FROM workspaces WHERE id != 'ws_operator_internal'").fetchone()["cnt"]
        if existing_workspaces >= 12:
            return

        # 5. Customer Workspaces Definition
        # 12 distinct companies with believable B2B SaaS profiles
        workspaces_config = [
            {
                "name": "Northwind Analytics",
                "slug": "northwind-analytics",
                "owner_name": "Maya Lin",
                "owner_email": "maya@northwind-analytics.com",
                "owner_pass": "northwind-2026",
                "billing_email": "billing@northwind-analytics.com",
                "tax_id": "US-841920144",
                "country": "US",
                "plan_id": "plan_business",
                "interval": "month",
                "status": "active",
                "cancel_at_period_end": 0,
                "history_months": 12,
                "extra_subs": [
                    {"name": "Stream Engine Cluster", "plan_id": "plan_business", "interval": "month"},
                    {"name": "Event Ingestion Inbound", "plan_id": "plan_business", "interval": "month"},
                ],
                "members": [
                    ("David Chen", "david@northwind-analytics.com"),
                    ("Sarah Connor", "sarah@northwind-analytics.com"),
                ],
            },
            {
                "name": "Parcelhop",
                "slug": "parcelhop",
                "owner_name": "Devon Vance",
                "owner_email": "devon@parcelhop.com",
                "owner_pass": "parcelhop-pass-2026",
                "billing_email": "finance@parcelhop.com",
                "tax_id": "US-391827465",
                "country": "US",
                "plan_id": "plan_business",
                "interval": "month",
                "status": "active",
                "cancel_at_period_end": 0,
                "history_months": 14,
                "extra_subs": [
                    {"name": "Carrier Gateway Service", "plan_id": "plan_business", "interval": "month"},
                    {"name": "Tracking Webhook Relays", "plan_id": "plan_business", "interval": "month"},
                ],
                "members": [("Aria Stark", "aria@parcelhop.com")],
            },
            {
                "name": "Brightloom Studio",
                "slug": "brightloom-studio",
                "owner_name": "Elena Rostova",
                "owner_email": "elena@brightloom.io",
                "owner_pass": "brightloom-pass-2026",
                "billing_email": "accounts@brightloom.io",
                "tax_id": "GB-771239845",
                "country": "GB",
                "plan_id": "plan_business",
                "interval": "year",
                "status": "active",
                "cancel_at_period_end": 0,
                "history_months": 10,
                "extra_subs": [],
                "members": [("Liam O'Connor", "liam@brightloom.io")],
            },
            {
                "name": "Quillstack",
                "slug": "quillstack",
                "owner_name": "Marcus Aurelius",
                "owner_email": "marcus@quillstack.com",
                "owner_pass": "quillstack-pass-2026",
                "billing_email": "invoices@quillstack.com",
                "tax_id": "US-554433221",
                "country": "US",
                "plan_id": "plan_business",
                "interval": "month",
                "status": "active",
                "cancel_at_period_end": 0,
                "history_months": 8,
                "extra_subs": [
                    {"name": "Publishing Gateway", "plan_id": "plan_business", "interval": "month"},
                    {"name": "Content Cache Network", "plan_id": "plan_business", "interval": "month"},
                ],
                "members": [],
            },
            {
                "name": "Harbor & Pine Legal",
                "slug": "harbor-pine-legal",
                "owner_name": "Charlotte Harbor",
                "owner_email": "charlotte@harborpine.com",
                "owner_pass": "harborpine-pass-2026",
                "billing_email": "billing@harborpine.com",
                "tax_id": "US-112233445",
                "country": "US",
                "plan_id": "plan_business",
                "interval": "month",
                "status": "active",
                "cancel_at_period_end": 0,
                "history_months": 9,
                "extra_subs": [
                    {"name": "Compliance Vault", "plan_id": "plan_business", "interval": "month"},
                ],
                "members": [("Ethan Hunt", "ethan@harborpine.com")],
            },
            {
                "name": "Fernleaf Health",
                "slug": "fernleaf-health",
                "owner_name": "Dr. Ananya Patel",
                "owner_email": "dr.patel@fernleafhealth.org",
                "owner_pass": "fernleaf-pass-2026",
                "billing_email": "payables@fernleafhealth.org",
                "tax_id": "US-998877665",
                "country": "US",
                "plan_id": "plan_business",
                "interval": "month",
                "status": "active",
                "cancel_at_period_end": 0,
                "history_months": 11,
                "extra_subs": [
                    {"name": "EHR Sync Service", "plan_id": "plan_business", "interval": "month"},
                    {"name": "Telehealth Gateway", "plan_id": "plan_business", "interval": "month"},
                ],
                "members": [("Nurse Miller", "miller@fernleafhealth.org")],
            },
            {
                "name": "Copperline Logistics",
                "slug": "copperline-logistics",
                "owner_name": "Jake Sterling",
                "owner_email": "jake@copperlinelogistics.com",
                "owner_pass": "copperline-pass-2026",
                "billing_email": "accounting@copperlinelogistics.com",
                "tax_id": "US-443322110",
                "country": "US",
                "plan_id": "plan_business",
                "interval": "month",
                "status": "active",
                "cancel_at_period_end": 0,
                "history_months": 7,
                "extra_subs": [
                    {"name": "Fleet Dispatch API", "plan_id": "plan_business", "interval": "month"},
                    {"name": "Route Optimization", "plan_id": "plan_business", "interval": "month"},
                ],
                "members": [],
            },
            {
                "name": "Vanguard Cloud",
                "slug": "vanguard-cloud",
                "owner_name": "Tomas Lindqvist",
                "owner_email": "tomas@vanguardcloud.net",
                "owner_pass": "vanguard-pass-2026",
                "billing_email": "invoicing@vanguardcloud.net",
                "tax_id": "DE-123456789",
                "country": "DE",
                "plan_id": "plan_business",
                "interval": "month",
                "status": "active",
                "cancel_at_period_end": 0,
                "history_months": 12,
                "extra_subs": [
                    {"name": "Kubernetes Orchestrator", "plan_id": "plan_business", "interval": "month"},
                    {"name": "Serverless Mesh", "plan_id": "plan_business", "interval": "month"},
                ],
                "members": [("Lucas Grey", "lucas@vanguardcloud.net")],
            },
            {
                "name": "Meridian Metrics",
                "slug": "meridian-metrics",
                "owner_name": "Avery Brooks",
                "owner_email": "avery@meridianmetrics.io",
                "owner_pass": "meridian-pass-2026",
                "billing_email": "finance@meridianmetrics.io",
                "tax_id": "US-667788990",
                "country": "US",
                "plan_id": "plan_business",
                "interval": "month",
                "status": "active",
                "cancel_at_period_end": 0,
                "history_months": 6,
                "extra_subs": [
                    {"name": "BI Aggregation Worker", "plan_id": "plan_business", "interval": "month"},
                    {"name": "Export Data Connector", "plan_id": "plan_business", "interval": "month"},
                ],
                "members": [],
            },
            {
                "name": "Crestview Media",
                "slug": "crestview-media",
                "owner_name": "Lucas Vance",
                "owner_email": "lucas@crestviewmedia.co",
                "owner_pass": "crestview-pass-2026",
                "billing_email": "ap@crestviewmedia.co",
                "tax_id": "US-778899001",
                "country": "US",
                "plan_id": "plan_pro",
                "interval": "month",
                "status": "active",
                "cancel_at_period_end": 1,  # 1 pending cancel
                "history_months": 5,
                "extra_subs": [],
                "members": [],
            },
            {
                "name": "Solis Energy Labs",
                "slug": "solis-energy-labs",
                "owner_name": "Sarah Jenkins",
                "owner_email": "sarah@solislabs.energy",
                "owner_pass": "solis-pass-2026",
                "billing_email": "treasury@solislabs.energy",
                "tax_id": "US-334455667",
                "country": "US",
                "plan_id": "plan_pro",
                "interval": "month",
                "status": "past_due",  # 1 past_due
                "cancel_at_period_end": 0,
                "history_months": 4,
                "extra_subs": [],
                "members": [],
            },
            {
                "name": "Aegis Security Group",
                "slug": "aegis-security-group",
                "owner_name": "Karl Schmidt",
                "owner_email": "karl@aegissecurity.io",
                "owner_pass": "aegis-pass-2026",
                "billing_email": "billing@aegissecurity.io",
                "tax_id": "US-223344556",
                "country": "US",
                "plan_id": "plan_business",
                "interval": "month",
                "status": "canceled",  # 1st canceled
                "cancel_at_period_end": 0,
                "history_months": 6,
                "extra_subs": [],
                "members": [],
            },
            {
                "name": "Horizon Health Data",
                "slug": "horizon-health-data",
                "owner_name": "Melissa Thorne",
                "owner_email": "melissa@horizonhealth.co",
                "owner_pass": "horizon-pass-2026",
                "billing_email": "billing@horizonhealth.co",
                "tax_id": "US-990011223",
                "country": "US",
                "plan_id": "plan_pro",
                "interval": "month",
                "status": "canceled",  # 2nd canceled
                "cancel_at_period_end": 0,
                "history_months": 3,
                "extra_subs": [],
                "members": [],
            },
        ]

        now = clock.now()
        rng = random.Random(42)  # Deterministic seed

        card_brands = ["Visa", "Mastercard", "American Express"]
        metrics = ["api_calls", "exports", "ai_tokens"]

        for ws_idx, cfg in enumerate(workspaces_config):
            user_id = generate_id("usr")
            user_hash = hash_password(cfg["owner_pass"])
            user_created = (now - timedelta(days=cfg["history_months"] * 30 + 10)).strftime("%Y-%m-%dT%H:%M:%SZ")

            conn.execute(
                """
                INSERT INTO users (id, name, email, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, 'member', ?)
                """,
                (user_id, cfg["owner_name"], cfg["owner_email"], user_hash, user_created),
            )

            # Workspace
            ws_id = generate_id("ws")
            initial_balance = rng.randint(8000, 45000)
            conn.execute(
                """
                INSERT INTO workspaces (id, name, slug, owner_id, billing_email, tax_id, country, credit_balance, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ws_id,
                    cfg["name"],
                    cfg["slug"],
                    user_id,
                    cfg["billing_email"],
                    cfg["tax_id"],
                    cfg["country"],
                    initial_balance,
                    user_created,
                ),
            )

            # Team members
            for m_name, m_email in cfg["members"]:
                m_id = generate_id("usr")
                m_hash = hash_password("member-pass-2026")
                conn.execute(
                    """
                    INSERT INTO users (id, name, email, password_hash, role, created_at)
                    VALUES (?, ?, ?, ?, 'member', ?)
                    """,
                    (m_id, m_name, m_email, m_hash, user_created),
                )

            # Payment method
            pm_id = generate_id("pm")
            brand = card_brands[ws_idx % len(card_brands)]
            last4 = f"{1000 + ws_idx * 137 % 9000}"
            conn.execute(
                """
                INSERT INTO payment_methods (id, workspace_id, brand, last4, exp_month, exp_year, is_default, created_at)
                VALUES (?, ?, ?, ?, 12, 2029, 1, ?)
                """,
                (pm_id, ws_id, brand, last4, user_created),
            )
            card_label = f"{brand} •••• {last4}"

            # Subscription
            sub_id = generate_id("sub")
            period_start = (now - timedelta(days=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
            period_end = (now + timedelta(days=18)).strftime("%Y-%m-%dT%H:%M:%SZ")
            canceled_at = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ") if cfg["status"] == "canceled" else None

            conn.execute(
                """
                INSERT INTO subscriptions (
                    id, workspace_id, plan_id, interval, status,
                    current_period_start, current_period_end, cancel_at_period_end,
                    canceled_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sub_id,
                    ws_id,
                    cfg["plan_id"],
                    cfg["interval"],
                    cfg["status"],
                    period_start,
                    period_end,
                    cfg["cancel_at_period_end"],
                    canceled_at,
                    user_created,
                ),
            )

            # Recompute entitlements
            recompute_entitlements(conn, ws_id, cfg["plan_id"])

            # Extra subscriptions for enterprise workspaces (to reach the realistic ~$4,800 platform MRR)
            for extra in cfg["extra_subs"]:
                extra_sub_id = generate_id("sub")
                conn.execute(
                    """
                    INSERT INTO subscriptions (
                        id, workspace_id, plan_id, interval, status,
                        current_period_start, current_period_end, cancel_at_period_end,
                        created_at
                    ) VALUES (?, ?, ?, ?, 'active', ?, ?, 0, ?)
                    """,
                    (
                        extra_sub_id,
                        ws_id,
                        extra["plan_id"],
                        extra["interval"],
                        period_start,
                        period_end,
                        user_created,
                    ),
                )

            # Historical Invoices and Charges (3 to 14 months)
            months = cfg["history_months"]
            plan_obj = next(p for p in PLANS_DATA if p["id"] == cfg["plan_id"])
            price_cents = plan_obj["yearly_price_cents"] if cfg["interval"] == "year" else plan_obj["monthly_price_cents"]

            for m in range(months, 0, -1):
                inv_dt = now - timedelta(days=m * 30)
                inv_date_str = inv_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                inv_id = generate_id("inv")
                num_row = conn.execute("SELECT current_val FROM counters WHERE name = 'invoice'").fetchone()
                val = int(num_row["current_val"]) + 1 if num_row else 100
                conn.execute("UPDATE counters SET current_val = ? WHERE name = 'invoice'", (val,))
                inv_num = f"TLY-{inv_dt.year}-{val:05d}"

                # Past due on the latest invoice for Solis Energy Labs
                is_failed = (cfg["status"] == "past_due" and m == 1)
                inv_status = "open" if is_failed else "paid"
                paid_at = None if is_failed else inv_date_str

                conn.execute(
                    """
                    INSERT INTO invoices (
                        id, number, workspace_id, subscription_id, status,
                        subtotal_cents, tax_cents, total_cents,
                        period_start, period_end, created_at, paid_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                    """,
                    (
                        inv_id,
                        inv_num,
                        ws_id,
                        sub_id,
                        inv_status,
                        price_cents,
                        price_cents,
                        inv_date_str,
                        (inv_dt + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        inv_date_str,
                        paid_at,
                    ),
                )

                line_id = generate_id("line")
                conn.execute(
                    """
                    INSERT INTO invoice_lines (id, invoice_id, description, quantity, unit_cents, amount_cents)
                    VALUES (?, ?, ?, 1, ?, ?)
                    """,
                    (line_id, inv_id, f"{plan_obj['name']} Plan ({cfg['interval']}ly)", price_cents, price_cents),
                )

                charge_id = generate_id("ch")
                charge_status = "failed" if is_failed else "succeeded"
                conn.execute(
                    """
                    INSERT INTO charges (id, invoice_id, workspace_id, amount_cents, status, payment_method_label, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (charge_id, inv_id, ws_id, price_cents, charge_status, card_label, inv_date_str),
                )

                # Add credit grant for paid invoice
                if not is_failed:
                    cr_id = generate_id("cr")
                    conn.execute(
                        """
                        INSERT INTO credit_ledger (id, workspace_id, delta, reason, reference, created_at)
                        VALUES (?, ?, ?, 'period_grant', ?, ?)
                        """,
                        (cr_id, ws_id, plan_obj["included_credits_per_period"], f"Invoice {inv_num}", inv_date_str),
                    )

            # 60 Days of Usage Events and Deductions
            for d in range(60, 0, -1):
                day_dt = now - timedelta(days=d)
                day_iso = day_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                # 2-4 usage events per day
                for _ in range(rng.randint(2, 4)):
                    met = rng.choice(metrics)
                    if met == "api_calls":
                        qty = rng.randint(50, 400)
                        cost = qty * 1
                    elif met == "exports":
                        qty = rng.randint(1, 3)
                        cost = qty * 50
                    else:  # ai_tokens
                        qty = rng.randint(1200, 8500)
                        cost = (qty + 99) // 100

                    use_id = generate_id("use")
                    conn.execute(
                        """
                        INSERT INTO usage_events (id, workspace_id, metric, quantity, credits_cost, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (use_id, ws_id, met, qty, cost, day_iso),
                    )
                    # Ledger usage deduction
                    cr_id = generate_id("cr")
                    conn.execute(
                        """
                        INSERT INTO credit_ledger (id, workspace_id, delta, reason, reference, created_at)
                        VALUES (?, ?, ?, 'usage', ?, ?)
                        """,
                        (cr_id, ws_id, -cost, f"{met} ({qty})", day_iso),
                    )
