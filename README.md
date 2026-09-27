# Tallyo Billing Service

> **Billing that scales with every seat, call and token.**

Tallyo is an autonomous subscription billing backend, consumption metering engine, and self-serve customer billing portal built for modern B2B SaaS applications. It unifies recurring seat subscriptions, prepaid credit drawdowns, instant mid-cycle proration, tax-compliant invoicing, and entitlement enforcement into a single zero-latency platform.

---

## Architecture Overview

```
                                  +-----------------------------+
                                  |     Customer Webhook / API   |
                                  +--------------+--------------+
                                                 |
                                 Bearer Token / Session Cookie
                                                 v
+-----------------------------------------------------------------------------------+
|                                  TALLYO ENGINE                                    |
|                                                                                   |
|  +-------------------+   +----------------------+   +--------------------------+  |
|  |   Customer Portal |   | REST API (/api/v1)   |   |   Operator Console       |  |
|  |   (/app/*)        |   | - Auth & Workspaces  |   |   (/admin/*)             |  |
|  |   - Overview      |   | - Subscriptions      |   |   - MRR / ARR Analytics  |  |
|  |   - Plan Switching|   | - Credit Drawdowns   |   |   - Tenant Inspection    |  |
|  |   - Invoices & PDF|   | - Entitlement Gating |   |   - Credit Adjustments   |  |
|  |   - Test Clocks   |   | - Invoices & PDF     |   |   - Global Invoices      |  |
|  +---------+---------+   +----------+-----------+   +-------------+------------+  |
|            |                        |                             |               |
+------------|------------------------|-----------------------------|---------------+
             |                        |                             |
             v                        v                             v
+-----------------------------------------------------------------------------------+
|                                 SERVICES CORE                                     |
|  - billing.py (cycle rollovers, intervals, upgrades, downgrades)                  |
|  - credits.py (double-entry ledger accounting, metric calculations)               |
|  - entitlements.py (cached feature gate authorization)                            |
|  - proration.py (second-precision balance adjustments)                            |
|  - clock.py (deterministic simulation clock offset management)                    |
+-----------------------------------------------------------------------------------+
                                      |
                                      v
+-----------------------------------------------------------------------------------+
|                        SQLITE PERSISTENCE (WAL MODE)                              |
|  workspaces, users, sessions, subscriptions, plans, features, plan_features,      |
|  workspace_entitlements, invoices, invoice_lines, charges, credit_ledger,         |
|  usage_events, idempotency_keys, payment_methods, clock                           |
+-----------------------------------------------------------------------------------+
```

---

## Key Capabilities

- **Hybrid Monetization**: Bill flat recurring fees (Starter, Pro, Business) combined with metered prepaid consumption credits for API calls, data exports, and AI tokens.
- **Second-Precision Proration**: Mid-cycle upgrades and downgrades compute the exact remaining duration, credit the unused prior tier, and issue immediate itemized invoices.
- **Sub-Millisecond Entitlements**: Pre-computed workspace entitlement cache allows host SaaS applications to gate features (`sso_saml`, `webhooks`, `custom_domains`) with near-zero latency.
- **High-Throughput Idempotency**: Safe event ingestion via the `Idempotency-Key` HTTP header protects against retry cascades and duplicate deductions.
- **Printable Invoices**: Built-in vector PDF and printable HTML invoices featuring tax registration, subtotal calculations, and itemized lines.
- **Simulation Test Clocks**: Deterministic time travel enables engineering and product teams to advance workspace time by days, months, or years synchronously without waiting for background timers.

---

## Runtime Contract & Configuration

Tallyo runs in self-contained environments without external service dependencies. All configuration is loaded from environment variables:

| Environment Variable | Default Value | Description |
|---|---|---|
| `PORT` | `8000` | HTTP service listener port |
| `HOST` | `0.0.0.0` | Bind network interface address |
| `DATABASE_PATH` | `./data/tallyo.db` | SQLite database file location (directories auto-created) |
| `ADMIN_EMAIL` | `ops@tallyo.io` | Seeded platform operator account |
| `ADMIN_PASSWORD` | `tallyo-admin` | Seeded platform operator password |
| `SEED_DATA` | `true` | Automatically populate plans, features, and customer workspaces |

---

## Quickstart

### Prerequisites

- Python 3.12+
- `uv` package manager

### 1. Install Dependencies

```bash
uv sync
```

### 2. Start the Service

You can launch the server using either the standalone runner module:

```bash
uv run python -m app
```

Or directly via Uvicorn:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3. Verify Health

```bash
curl -s http://localhost:8000/health
# Response: {"status":"ok"}
```

Interactive OpenAPI specifications are available at `http://localhost:8000/api/docs`.

---

## Pre-Configured Accounts

The service comes pre-seeded with customer accounts and an operator administration account:

### Customer Workspace Login (Northwind Analytics)
- **Portal URL**: `http://localhost:8000/login`
- **Email**: `maya@northwind-analytics.com`
- **Password**: `northwind-2026`
- **Workspace**: Northwind Analytics (Business Tier, $199/mo, 100,000 credits)

### Platform Operator Console
- **Console URL**: `http://localhost:8000/login`
- **Email**: `ops@tallyo.io`
- **Password**: `tallyo-admin`
- **Privileges**: Global revenue analytics, tenant inspection, and credit balance adjustments

---

## REST API Reference

All REST endpoints are namespaced under `/api/v1`. Authenticate by providing your bearer token via the `Authorization: Bearer <token>` header, or via the `tallyo_session` cookie in browsers.

### Authentication & Tenant Management

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/signup` | Register workspace owner, create Starter subscription, and allocate credits |
| `POST` | `/api/v1/auth/login` | Authenticate user credentials and return bearer session token |
| `POST` | `/api/v1/auth/logout` | Terminate session |
| `GET` | `/api/v1/auth/me` | Fetch active user profile and primary workspace |
| `GET` | `/api/v1/workspace` | Retrieve current workspace details |
| `PATCH` | `/api/v1/workspace` | Update billing address, tax identification, and country |

### Plans & Entitlements

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/plans` | Public catalog of subscription plans and feature allowances |
| `GET` | `/api/v1/workspace/entitlements` | List all granted feature keys for current workspace |
| `GET` | `/api/v1/workspace/features/{key}/check` | Fast feature gate check (`{ "allowed": true }`) |

### Subscriptions & Lifecycle

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/subscription` | Fetch active subscription, period bounds, and pending actions |
| `POST` | `/api/v1/subscription/change-plan` | Upgrade or downgrade plan tier with second-level proration |
| `POST` | `/api/v1/subscription/cancel` | Cancel subscription immediately or schedule at period end |
| `POST` | `/api/v1/subscription/resume` | Undo scheduled period-end cancellation |

### Credits & Consumption Ingestion

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/credits` | Fetch available balance and immutable transaction ledger |
| `POST` | `/api/v1/credits/top-up` | Purchase non-expiring credit packs (5,000 blocks at $10.00) |
| `POST` | `/api/v1/usage` | Record billable event (`api_calls`, `exports`, `ai_tokens`) |
| `GET` | `/api/v1/usage` | Query ingestion event stream with metric and date filters |

### Invoices & Payment Methods

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/invoices` | List historical invoices, payment status, and totals |
| `GET` | `/api/v1/invoices/{id}` | Retrieve itemized invoice details and line items |
| `GET` | `/api/v1/invoices/{id}/pdf` | Render printable HTML/PDF invoice receipt |
| `GET` | `/api/v1/payment-methods` | List display-only payment methods |
| `POST` | `/api/v1/payment-methods` | Register a display payment method |
| `DELETE` | `/api/v1/payment-methods/{id}` | Delete payment method |
| `POST` | `/api/v1/payment-methods/{id}/default` | Set default payment method |

### Deterministic Simulation Clock

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/clock` | Retrieve current simulated timestamp |
| `POST` | `/api/v1/clock/advance` | Fast-forward workspace clock by 1–400 days and run cycle rollovers |

---

## Test Clock Operations

Tallyo replaces asynchronous background tasks with a deterministic test clock. When you advance the clock, the billing engine evaluates active subscriptions, renews periods, issues recurring invoices, and grants new cycle credits synchronously:

```bash
# Advance time by 30 days
curl -X POST http://localhost:8000/api/v1/clock/advance \
  -H "Authorization: Bearer $TALLYO_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"days": 30}'

# Response:
# {
#   "now": "2026-10-27T09:15:00Z",
#   "invoices_created": ["inv_8912304891"]
# }
```

---

## Automated Test Suite

Run the full end-to-end integration and page verification suite:

```bash
uv run pytest -q
```

All integration suites execute against an isolated temporary SQLite database instance, leaving runtime databases untouched.

---

## License

This software is released under the MIT License. See [LICENSE](LICENSE) for details.
