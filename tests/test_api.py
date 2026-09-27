import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db
from app.seed import seed_database
from app.clock import clock


from pathlib import Path
from app.config import settings


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment(tmp_path_factory):
    """Ensure an isolated database and seeds are initialized before running suite."""
    test_db_dir = tmp_path_factory.mktemp("test_db")
    test_db_file = test_db_dir / "tallyo_test.db"
    settings.DATABASE_PATH = str(test_db_file)
    init_db()
    seed_database()
    yield
    clock.reset_clock()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def member_auth(client):
    """Authenticate with seeded Northwind Analytics owner account."""
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "maya@northwind-analytics.com", "password": "northwind-2026"},
    )
    assert res.status_code == 200
    token = res.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def operator_auth(client):
    """Authenticate with platform operator account."""
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "ops@tallyo.io", "password": "tallyo-admin"},
    )
    assert res.status_code == 200
    token = res.json()["token"]
    return {"Authorization": f"Bearer {token}"}


# 1. Health check
def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


# 2. Signup
def test_auth_signup_flow(client):
    signup_payload = {
        "name": "Evelyn Reed",
        "email": "evelyn@aurora-systems.io",
        "password": "aurora-secure-pass-2026",
        "workspace_name": "Aurora Data Systems",
    }
    res = client.post("/api/v1/auth/signup", json=signup_payload)
    assert res.status_code == 201
    data = res.json()
    assert "token" in data
    assert data["user"]["email"] == "evelyn@aurora-systems.io"
    assert data["workspace"]["name"] == "Aurora Data Systems"
    assert data["workspace"]["credit_balance"] == 1000


# 3. Duplicate email signup
def test_auth_signup_duplicate_email(client):
    payload = {
        "name": "Duplicate User",
        "email": "maya@northwind-analytics.com",
        "password": "another-password-2026",
        "workspace_name": "Duplicate Team",
    }
    res = client.post("/api/v1/auth/signup", json=payload)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "email_exists"


# 4. Login with invalid password
def test_auth_login_invalid_password(client):
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "maya@northwind-analytics.com", "password": "incorrect-password"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_credentials"


# 5. Get current identity
def test_get_me_endpoint(client, member_auth):
    res = client.get("/api/v1/me", headers=member_auth)
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == "maya@northwind-analytics.com"
    assert data["workspace"]["slug"] == "northwind-analytics"


# 6. Unauthorized access
def test_get_me_unauthorized(client):
    res = client.get("/api/v1/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "unauthorized"


# 7. Workspace update
def test_workspace_update(client, member_auth):
    res = client.patch(
        "/api/v1/workspace",
        headers=member_auth,
        json={"billing_email": "accounts-payable@northwind-analytics.com", "country": "US"},
    )
    assert res.status_code == 200
    assert res.json()["billing_email"] == "accounts-payable@northwind-analytics.com"


# 8. List plans
def test_list_plans(client):
    res = client.get("/api/v1/plans")
    assert res.status_code == 200
    plans = res.json()
    assert len(plans) == 3
    plan_ids = [p["id"] for p in plans]
    assert "plan_starter" in plan_ids
    assert "plan_pro" in plan_ids
    assert "plan_business" in plan_ids


# 9. Workspace entitlements
def test_workspace_entitlements(client, member_auth):
    res = client.get("/api/v1/workspace/entitlements", headers=member_auth)
    assert res.status_code == 200
    features = res.json()["features"]
    assert "api_access" in features
    assert "webhooks" in features


# 10. Feature gate checks
def test_feature_gate_check_allowed(client, member_auth):
    res = client.get("/api/v1/workspace/features/api_access/check", headers=member_auth)
    assert res.status_code == 200
    assert res.json()["allowed"] is True


def test_feature_gate_check_denied(client):
    # Create new Starter user and check an enterprise feature
    signup_res = client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Starter User",
            "email": "starter@nebula-metrics.com",
            "password": "nebula-password-2026",
            "workspace_name": "Nebula Metrics",
        },
    )
    token = signup_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/v1/workspace/features/sso_saml/check", headers=headers)
    assert res.status_code == 200
    assert res.json()["allowed"] is False


# 11. Subscription retrieval
def test_get_subscription(client, member_auth):
    res = client.get("/api/v1/subscription", headers=member_auth)
    assert res.status_code == 200
    data = res.json()
    assert "plan_id" in data
    assert data["status"] in ("active", "past_due")


# 12. Subscription upgrade and proration invoice
def test_subscription_upgrade(client):
    signup_res = client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Upgrade User",
            "email": "upgrade@helios-labs.io",
            "password": "helios-password-2026",
            "workspace_name": "Helios Labs",
        },
    )
    token = signup_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upgrade from Starter to Pro
    res = client.post(
        "/api/v1/subscription/change-plan",
        headers=headers,
        json={"plan_id": "plan_pro", "interval": "month"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["subscription"]["plan_id"] == "plan_pro"
    assert "invoice" in data
    assert data["invoice"]["status"] == "paid"

    # Verify that webhooks feature is now granted
    ent_res = client.get("/api/v1/workspace/features/webhooks/check", headers=headers)
    assert ent_res.json()["allowed"] is True


# 13. Immediate subscription cancel
def test_subscription_immediate_cancel(client):
    signup_res = client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Cancel User",
            "email": "cancel@borealis-tech.com",
            "password": "borealis-password-2026",
            "workspace_name": "Borealis Tech",
        },
    )
    token = signup_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/v1/subscription/cancel",
        headers=headers,
        json={"at_period_end": False},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "canceled"
    assert data["canceled_at"] is not None


# 14. Cancel at period end and resume
def test_subscription_cancel_at_period_end_and_resume(client, member_auth):
    res = client.post(
        "/api/v1/subscription/cancel",
        headers=member_auth,
        json={"at_period_end": True},
    )
    assert res.status_code == 200
    assert res.json()["cancel_at_period_end"] == 1

    resume_res = client.post("/api/v1/subscription/resume", headers=member_auth)
    assert resume_res.status_code == 200
    assert resume_res.json()["cancel_at_period_end"] == 0


# 15. Credits balance and ledger
def test_credits_balance_and_ledger(client, member_auth):
    res = client.get("/api/v1/credits", headers=member_auth)
    assert res.status_code == 200
    data = res.json()
    assert "balance" in data
    assert "ledger" in data
    assert isinstance(data["ledger"], list)


# 16. Credit pack top-up
def test_credits_top_up_valid_pack(client, member_auth):
    initial_balance = client.get("/api/v1/credits", headers=member_auth).json()["balance"]
    res = client.post(
        "/api/v1/credits/top-up",
        headers=member_auth,
        json={"credits": 10000},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["credits_added"] == 10000
    assert data["balance"] == initial_balance + 10000
    assert "invoice" in data


def test_credits_top_up_invalid_pack(client, member_auth):
    res = client.post(
        "/api/v1/credits/top-up",
        headers=member_auth,
        json={"credits": 4200},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_credit_pack"


# 17. Usage metering and credit deduction
def test_usage_record_deduction(client, member_auth):
    initial_balance = client.get("/api/v1/credits", headers=member_auth).json()["balance"]
    res = client.post(
        "/api/v1/usage",
        headers=member_auth,
        json={"metric": "api_calls", "quantity": 100},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["credits_cost"] == 100
    assert data["metric"] == "api_calls"

    new_balance = client.get("/api/v1/credits", headers=member_auth).json()["balance"]
    assert new_balance == initial_balance - 100


# 18. Usage recording with idempotency key
def test_usage_with_idempotency_key(client, member_auth):
    key = "tly_idem_key_778899"
    headers = {**member_auth, "Idempotency-Key": key}
    res = client.post(
        "/api/v1/usage",
        headers=headers,
        json={"metric": "exports", "quantity": 2},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["credits_cost"] == 100

    # Repeat with same key
    res_repeat = client.post(
        "/api/v1/usage",
        headers=headers,
        json={"metric": "exports", "quantity": 2},
    )
    assert res_repeat.status_code == 200
    assert res_repeat.json()["id"] == data["id"]


# 19. Usage insufficient credits error
def test_usage_insufficient_credits(client):
    signup_res = client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Zero Balance User",
            "email": "zerocredits@krypton.io",
            "password": "krypton-password-2026",
            "workspace_name": "Krypton Labs",
        },
    )
    token = signup_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Deduct more than the initial 1,000 credits
    res = client.post(
        "/api/v1/usage",
        headers=headers,
        json={"metric": "exports", "quantity": 50},  # 50 * 50 = 2500 credits
    )
    assert res.status_code == 402
    assert res.json()["error"]["code"] == "insufficient_credits"


# 20. Usage telemetry history
def test_get_usage_history(client, member_auth):
    res = client.get("/api/v1/usage", headers=member_auth)
    assert res.status_code == 200
    data = res.json()
    assert "events" in data
    assert "daily_aggregates" in data


# 21. Invoices list and detail
def test_invoices_listing_and_detail(client, member_auth):
    res = client.get("/api/v1/invoices", headers=member_auth)
    assert res.status_code == 200
    invoices = res.json()
    assert len(invoices) > 0
    inv_id = invoices[0]["id"]

    detail_res = client.get(f"/api/v1/invoices/{inv_id}", headers=member_auth)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert "lines" in detail
    assert "charges" in detail


# 22. Invoice print view
def test_invoice_pdf_view(client, member_auth):
    invoices = client.get("/api/v1/invoices", headers=member_auth).json()
    inv_id = invoices[0]["id"]
    res = client.get(f"/api/v1/invoices/{inv_id}/pdf", headers=member_auth)
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Tallyo" in res.text
    assert "Invoice" in res.text


# 23. Charges listing
def test_charges_listing(client, member_auth):
    res = client.get("/api/v1/charges", headers=member_auth)
    assert res.status_code == 200
    charges = res.json()
    assert len(charges) > 0
    assert "amount_cents" in charges[0]


# 24. Payment methods lifecycle
def test_payment_methods_lifecycle(client, member_auth):
    create_res = client.post(
        "/api/v1/payment-methods",
        headers=member_auth,
        json={"brand": "Mastercard", "last4": "5555", "exp_month": 10, "exp_year": 2028},
    )
    assert create_res.status_code == 201
    pm_id = create_res.json()["id"]

    # Set as default
    def_res = client.post(f"/api/v1/payment-methods/{pm_id}/default", headers=member_auth)
    assert def_res.status_code == 200

    # Delete
    del_res = client.delete(f"/api/v1/payment-methods/{pm_id}", headers=member_auth)
    assert del_res.status_code == 200


# 25. Clock retrieval
def test_get_clock(client):
    res = client.get("/api/v1/clock")
    assert res.status_code == 200
    assert "now" in res.json()


# 26. Clock advance and renewal
def test_clock_advance_renewal(client):
    signup_res = client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Renewal User",
            "email": "renewal@zenith-cloud.io",
            "password": "zenith-password-2026",
            "workspace_name": "Zenith Cloud",
        },
    )
    token = signup_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Advance 35 days to pass the 30-day period
    res = client.post("/api/v1/clock/advance", headers=headers, json={"days": 35})
    assert res.status_code == 200
    data = res.json()
    assert "now" in data
    assert "invoices_created" in data


# 27. Operator metrics
def test_operator_metrics(client, operator_auth):
    res = client.get("/api/v1/admin/metrics", headers=operator_auth)
    assert res.status_code == 200
    data = res.json()
    assert "mrr_cents" in data
    assert "arr_cents" in data
    assert data["mrr_cents"] > 0
    assert data["active_subscriptions_count"] > 0


# 28. Operator workspaces listing and detail
def test_operator_workspaces(client, operator_auth):
    res = client.get("/api/v1/admin/workspaces", headers=operator_auth)
    assert res.status_code == 200
    workspaces = res.json()
    assert len(workspaces) >= 12

    ws_id = workspaces[0]["id"]
    detail_res = client.get(f"/api/v1/admin/workspaces/{ws_id}", headers=operator_auth)
    assert detail_res.status_code == 200
    data = detail_res.json()
    assert "workspace" in data
    assert "subscription" in data
    assert "entitlements" in data


# 29. Operator adjust credits
def test_operator_adjust_credits(client, operator_auth):
    workspaces = client.get("/api/v1/admin/workspaces", headers=operator_auth).json()
    ws_id = workspaces[0]["id"]
    res = client.post(
        f"/api/v1/admin/workspaces/{ws_id}/credits/adjust",
        headers=operator_auth,
        json={"delta": 5000, "reason": "Strategic partner courtesy grant"},
    )
    assert res.status_code == 200
    assert res.json()["delta"] == 5000


# 30. Operator route restricted for regular members
def test_operator_endpoints_restricted(client, member_auth):
    res = client.get("/api/v1/admin/metrics", headers=member_auth)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "forbidden"
