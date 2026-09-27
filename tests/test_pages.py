import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def member_cookies(client):
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "maya@northwind-analytics.com", "password": "northwind-2026"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["token"]
    return {"tallyo_session": token}


@pytest.fixture
def operator_cookies(client):
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "ops@tallyo.io", "password": "tallyo-admin"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["token"]
    return {"tallyo_session": token}


def test_public_pages_render_successfully(client):
    routes = [
        "/",
        "/pricing",
        "/customers",
        "/customers/northwind-analytics",
        "/docs",
        "/changelog",
        "/about",
        "/contact",
        "/status",
        "/security",
        "/terms",
        "/privacy",
        "/login",
        "/signup",
        "/forgot",
    ]
    for r in routes:
        res = client.get(r)
        assert res.status_code == 200, f"Route {r} failed with status {res.status_code}"
        assert "Tallyo" in res.text


def test_portal_pages_require_auth(client):
    portal_routes = [
        "/app",
        "/app/plans",
        "/app/usage",
        "/app/credits",
        "/app/invoices",
        "/app/payment-methods",
        "/app/settings",
        "/app/developers",
    ]
    for r in portal_routes:
        res = client.get(r, follow_redirects=False)
        assert res.status_code == 302
        assert res.headers["location"] == "/login"


def test_portal_pages_render_for_member(client, member_cookies):
    portal_routes = [
        "/app",
        "/app/plans",
        "/app/usage",
        "/app/credits",
        "/app/invoices",
        "/app/payment-methods",
        "/app/settings",
        "/app/developers",
    ]
    for r in portal_routes:
        res = client.get(r, cookies=member_cookies)
        assert res.status_code == 200, f"Portal route {r} failed for member"
        assert "Tallyo" in res.text


def test_operator_console_requires_operator_role(client, member_cookies, operator_cookies):
    # Member should be redirected to /login when attempting to access /admin
    res_member = client.get("/admin", cookies=member_cookies, follow_redirects=False)
    assert res_member.status_code == 302
    assert res_member.headers["location"] == "/login"

    # Operator should render successfully
    admin_routes = [
        "/admin",
        "/admin/workspaces",
        "/admin/subscriptions",
        "/admin/invoices",
    ]
    for r in admin_routes:
        res = client.get(r, cookies=operator_cookies)
        assert res.status_code == 200, f"Admin route {r} failed for operator"
        assert "Tallyo" in res.text


def test_operator_workspace_detail_page(client, operator_cookies):
    res = client.get("/admin/workspaces", cookies=operator_cookies)
    assert res.status_code == 200

    # Retrieve specific workspace detail from seeded workspaces
    res_api = client.get("/api/v1/admin/workspaces", cookies=operator_cookies)
    assert res_api.status_code == 200
    workspaces = res_api.json()
    assert len(workspaces) > 0
    target_id = workspaces[0]["id"]

    res_detail = client.get(f"/admin/workspaces/{target_id}", cookies=operator_cookies)
    assert res_detail.status_code == 200
    assert target_id in res_detail.text


def test_invoice_pdf_view(client, member_cookies):
    res_invs = client.get("/api/v1/invoices", cookies=member_cookies)
    assert res_invs.status_code == 200
    invs = res_invs.json()
    assert len(invs) > 0
    inv_id = invs[0]["id"]

    res_pdf = client.get(f"/api/v1/invoices/{inv_id}/pdf", cookies=member_cookies)
    assert res_pdf.status_code == 200
    assert "Invoice" in res_pdf.text
    assert invs[0]["number"] in res_pdf.text


def test_404_html_page_rendering(client):
    res = client.get("/non-existent-page-path", headers={"Accept": "text/html"})
    assert res.status_code == 404
    assert "Page Not Found" in res.text
