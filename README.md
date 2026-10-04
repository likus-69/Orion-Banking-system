# Orion Banking System

A modern, security-hardened online banking API + UI built with FastAPI, SQLAlchemy 2.0, Jinja2, and PostgreSQL.

> Refactored from a single-file HTML prototype into a layered architecture with services + repositories, JWT access/refresh tokens, concurrency-safe transfers, statement PDF export, and a polished dark/light theme UI.

---

## ✨ Features

### Backend
- **Layered architecture**: routes → services → repositories → models
- **Auth**: bcrypt-hashed PINs, JWT access + refresh token pair, single-use refresh rotation, weak-PIN rejection, login lockout after 5 failures, timing-attack safe login
- **Concurrency-safe money movement**: `SELECT FOR UPDATE` row locks on transfers/withdrawals/deposits, deterministic lock ordering to avoid deadlocks, idempotency keys for transfers
- **New features**: KYC fields, transaction categories/types/statuses, in-app notifications, statement PDF export, request-ID middleware, IP/User-Agent audit logging, **transactional email notifications**
- **Hardening**: CORS allowlist, rate limiting (slowapi), structured logging (structlog), GZip middleware, consistent JSON error shape with request IDs
- **Config**: strict validation (forbids `change-me-in-production` secret, rejects SQLite in prod env), env-driven
- **Email**: SMTP backend with switchable dev (console) + test (memory) backends, fire-and-forget via FastAPI BackgroundTasks, per-event opt-out preferences

### Frontend (Jinja2 + vanilla JS)
- **Refined design tokens**: dark + light theme via `data-theme` attribute, IBM Plex + Playfair Display typography
- **Animated stars background** (canvas)
- **Dashboard** with balance panel, quick actions, recent activity, spending breakdown doughnut chart (Chart.js)
- **Transaction history** with type filters (all/deposit/withdrawal/transfer) + clickable rows → detail view
- **Transfer wizard** with confirm modal + idempotency keys
- **Settings page** with KYC form, notifications panel, session revoke
- **Profile page** with avatar, account details
- **Statement PDF export** (reportlab-generated on the backend)
- **Toast notifications**, loading skeletons, empty states, optimistic UI updates, accessibility (ARIA, keyboard nav)
- **Admin panel** (`/admin/*`) with role-based access — dashboard stats, KYC review queue, user management with search/filter

### Testing
- 76 pytest tests covering auth, accounts, transactions, statements, notifications, the admin panel, email triggers, and webhooks
- GitHub Actions CI workflow (lint + test on every push/PR)

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/likus-69/Orion-Banking-system.git
cd Orion-Banking-system/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum, set a strong SECRET_KEY:
#   openssl rand -hex 32
```

### 3. (Optional) Start Postgres via Docker

```bash
docker-compose up -d
```

For local dev, SQLite works out of the box — no Postgres needed.

### 4. Seed demo data

```bash
python scripts/seed.py
```

Creates four demo accounts (3 customers + 1 admin) with sample transactions:

| Email                          | PIN   | Role     | KYC status  | Balance    |
| ------------------------------ | ----- | -------- | ----------- | ---------- |
| mary.garcia@orionbank.com      | 8421  | customer | verified    | $12,500.00 |
| alex.rivera@orionbank.com      | 7351  | customer | in_review   | $3,200.50  |
| demo@orionbank.com             | 4242  | customer | pending     | $0.00      |
| admin@orionbank.com            | 1357  | admin    | verified    | $0.00      |

### 5. Run the server

```bash
uvicorn app.main:app --reload
```

Visit:
- **Customer UI**: http://localhost:8000/login
- **Admin UI**: http://localhost:8000/admin (login as `admin@orionbank.com` / `1357`)
- **API docs** (Swagger): http://localhost:8000/api/docs
- **Health check**: http://localhost:8000/health

---

## 📁 Project Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app + middleware + exception handlers
│   ├── config.py                # Settings (env-driven, strict validation)
│   ├── database.py              # Engine, session, declarative base
│   ├── deps.py                 # Shared FastAPI dependencies
│   ├── exceptions.py           # Domain exceptions
│   ├── logging_config.py      # structlog configuration
│   ├── models/                 # SQLAlchemy models
│   │   ├── user.py             # User + RefreshToken
│   │   ├── transaction.py      # Transaction + enums
│   │   ├── audit_log.py        # AuditLog
│   │   └── notification.py     # Notification
│   ├── schemas/                 # Pydantic schemas
│   │   ├── auth.py / user.py / transaction.py / notification.py
│   ├── repositories/            # Data access layer (pure DB ops)
│   │   ├── user_repo.py / transaction_repo.py / audit_repo.py / notification_repo.py
│   ├── services/                # Business logic layer
│   │   ├── auth_service.py     # register / login / refresh / logout
│   │   ├── token_service.py    # JWT issuance + refresh rotation
│   │   ├── account_service.py  # profile + KYC
│   │   ├── transaction_service.py # deposit / withdraw / transfer (with locking)
│   │   ├── audit_service.py    # audit log helper
│   │   └── statement_service.py # PDF generator
│   ├── routes/                  # API + page routes (thin wrappers)
│   │   ├── auth.py / accounts.py / transactions.py
│   │   ├── statements.py / notifications.py / pages.py
│   ├── middleware/              # RequestIdMiddleware
│   ├── templates/               # Jinja2 templates
│   │   ├── base.html
│   │   ├── auth/ (login, register)
│   │   └── dashboard/ (index, transactions, transaction_detail, transfer, deposit, settings, profile)
│   └── static/                  # CSS + JS
│       ├── css/ (tokens.css, base.css, components.css)
│       └── js/ (api.js, ui.js)
├── alembic/                     # DB migrations
│   └── versions/ (20241003_initial.py, 20241004_overhaul.py)
├── scripts/
│   └── seed.py                  # Demo data seeder
├── tests/                       # pytest suite (29 tests)
├── .env.example
├── docker-compose.yml
├── requirements.txt
└── alembic.ini
```

---

## 🔒 Security Notes

- **PINs**: 4-6 digits, bcrypt-hashed. Sequential PINs (1234, 4321) and repeated PINs (1111) are rejected.
- **JWT**: Access tokens (30 min) + refresh tokens (7 days). Refresh tokens are SHA-256-hashed before storage and rotated on every use (single-use rotation).
- **Login lockout**: 5 failed attempts → account locked.
- **Timing attacks**: login with non-existent email runs a dummy bcrypt verify to avoid revealing which emails exist.
- **Transfers**: protected by `SELECT FOR UPDATE` row locks + idempotency keys (prevents accidental double-clicks from double-spending).
- **Audit logs**: every auth + transaction action is logged with IP, User-Agent, request ID.
- **CORS**: configurable allowlist (default: localhost only).
- **Rate limiting**: 10/min on auth endpoints, 60/min elsewhere (configurable).
- **Email failures are non-fatal**: if SMTP throws during a transaction, the request still succeeds (`EMAIL_SILENT_FAILURE=true` by default). Audit logs capture the failure.

---

## 📧 Email Configuration

Emails are sent on key events: registration (welcome), deposit/withdrawal confirmations, transfer in/out notifications, and KYC approve/reject decisions.

Configure via `.env`:

```bash
# Dev: print emails to stdout (default)
EMAIL_BACKEND=console

# Production: real SMTP
EMAIL_BACKEND=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=your-account@gmail.com
SMTP_PASSWORD=your-app-password   # use an App Password, not your account password
EMAIL_FROM_ADDRESS=no-reply@yourdomain.com
EMAIL_FROM_NAME=Orion Banking
```

Users can opt out of individual event types from **Settings → Email preferences**. The five toggles are:
- Deposit confirmations
- Withdrawal confirmations
- Incoming transfers
- Outgoing transfers
- KYC decisions

For testing, set `EMAIL_BACKEND=memory` — sent emails are captured in-process and can be inspected via `app.services.email_service.get_sent_emails()`.

---

## 🔔 Webhooks

Users can register webhook URLs to receive event notifications when money moves through their account (or when their KYC status changes). Each delivery is HMAC-SHA256-signed and persisted for audit.

### Supported events

| Event type | Fires when |
|------------|------------|
| `transaction.deposit` | User makes a deposit |
| `transaction.withdrawal` | User makes a withdrawal |
| `transaction.transfer.out` | User sends money to another account |
| `transaction.transfer.in` | User receives money from another account |
| `kyc.approved` | Admin approves the user's KYC |
| `kyc.rejected` | Admin rejects the user's KYC |

### Payload shape

```json
{
  "id": "evt_abc123...",
  "type": "transaction.deposit",
  "created_at": "2024-10-07T12:34:56.789Z",
  "data": {
    "transaction_id": 42,
    "reference": "ORX-AB12-CD34",
    "amount": 250.00,
    "memo": "paycheck",
    "new_balance": 1250.00,
    "created_at": "2024-10-07T12:34:56.789Z"
  }
}
```

### Verifying signatures

Every delivery includes an `X-Orion-Signature` header of the form `sha256=<hex>`. To verify, recompute HMAC-SHA256 of the **raw request body** using the webhook's signing secret (returned on creation or after rotation):

```python
import hmac, hashlib

expected = "sha256=" + hmac.new(
    secret.encode(),
    request_body.encode(),
    hashlib.sha256
).hexdigest()

if not hmac.compare_digest(expected, request.headers["X-Orion-Signature"]):
    return 401  # signature mismatch — reject
```

### Retry behavior

- **2xx response** → delivery marked as `delivered`, no retry
- **4xx response** → delivery marked as `failed`, **no retry** (receiver rejected it; retrying won't help)
- **5xx response or network error** → retry up to 3 attempts with backoff, then marked as `failed`

### API endpoints

All under `/api/webhooks`, all require authentication:

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/webhooks` | List your webhooks |
| `POST` | `/api/webhooks` | Create a webhook (returns signing secret) |
| `GET`  | `/api/webhooks/{id}` | Get a webhook |
| `PATCH`| `/api/webhooks/{id}` | Update name, URL, events, or status |
| `DELETE` | `/api/webhooks/{id}` | Delete a webhook |
| `POST` | `/api/webhooks/{id}/rotate-secret` | Rotate signing secret |
| `POST` | `/api/webhooks/{id}/test` | Send a `ping` event for testing |
| `GET`  | `/api/webhooks/{id}/deliveries` | List recent deliveries |
| `POST` | `/api/webhooks/deliveries/{id}/redeliver` | Re-send a delivery |

### UI

Visit `/webhooks` to manage your subscriptions through a self-serve UI. Each webhook has a detail page showing delivery history with status codes, response bodies, and a "Redeliver" button.

---

## 🧪 Testing

```bash
cd backend
pytest tests/ -v
```

Tests use an in-process SQLite DB with table reset between tests. Coverage:
- Auth: register, login, weak-PIN rejection, lockout, refresh rotation, single-use refresh, logout revokes tokens
- Transactions: deposit/withdraw/transfer, insufficient funds, self-transfer, idempotency, cross-user transaction isolation
- Statements: PDF export
- Notifications: deposit creates a notification

---

## 🐳 Docker (Postgres only)

The `docker-compose.yml` only runs Postgres. The backend itself is intended to be run via `uvicorn` directly (or behind a WSGI server in prod). To run with Postgres:

```bash
docker-compose up -d
# In .env: DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/orion_banking
alembic upgrade head
python scripts/seed.py
uvicorn app.main:app
```

---

## 🗺️ Roadmap / Not yet implemented

- ~~Email notifications (SMTP integration)~~ ✅ Done
- ~~Webhooks for transaction events~~ ✅ Done
- Scheduled / recurring transfers (background task queue)
- Two-factor authentication (TOTP)

---

## 📜 License

MIT
