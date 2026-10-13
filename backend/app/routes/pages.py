"""Page routes — Jinja2-rendered HTML pages served by the backend.

Page routes do NOT require authentication at the route level. They just
render HTML shells. The JavaScript inside each page calls the protected
API endpoints with the token from localStorage. If the API returns 401,
the JS redirects to /login (handled in ui.js via the orion:unauthorized
event + requireAuth() helper).

Browsers don't send Authorization headers on page navigations (they only
send cookies), so requiring a Bearer token at the page-route level would
cause every direct URL visit to return 401 JSON instead of the HTML page.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.config import settings

router = APIRouter(tags=["pages"])


def _ctx(request: Request, **extra) -> dict:
    """Base template context."""
    return {
        "request": request,
        "app_name": settings.app_name,
        "env": settings.env,
        **extra,
    }


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "auth/login.html", _ctx(request, page="login")
    )


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "auth/register.html", _ctx(request, page="register")
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "dashboard/index.html", _ctx(request, page="dashboard")
    )


@router.get("/transactions", response_class=HTMLResponse)
def transactions_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "dashboard/transactions.html", _ctx(request, page="transactions")
    )


@router.get("/transactions/{tx_id}", response_class=HTMLResponse)
def transaction_detail_page(request: Request, tx_id: int):
    return request.app.state.templates.TemplateResponse(
        "dashboard/transaction_detail.html",
        _ctx(request, page="transaction_detail", tx_id=tx_id),
    )


@router.get("/transfer", response_class=HTMLResponse)
def transfer_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "dashboard/transfer.html", _ctx(request, page="transfer")
    )


@router.get("/deposit", response_class=HTMLResponse)
def deposit_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "dashboard/deposit.html", _ctx(request, page="deposit")
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "dashboard/settings.html", _ctx(request, page="settings")
    )


@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "dashboard/profile.html", _ctx(request, page="profile")
    )


# ── Admin pages ───────────────────────────────────────────────────
# No auth at the route level — the JS checks the user's role via
# /api/accounts/me and redirects non-admins to /dashboard.
@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "admin/index.html", _ctx(request, page="admin_dashboard")
    )


@router.get("/admin/kyc", response_class=HTMLResponse)
def admin_kyc_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "admin/kyc.html", _ctx(request, page="admin_kyc")
    )


@router.get("/admin/kyc/{user_id}", response_class=HTMLResponse)
def admin_kyc_detail_page(request: Request, user_id: int):
    return request.app.state.templates.TemplateResponse(
        "admin/kyc_detail.html",
        _ctx(request, page="admin_kyc_detail", target_user_id=user_id),
    )


@router.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "admin/users.html", _ctx(request, page="admin_users")
    )


@router.get("/admin/audit-logs", response_class=HTMLResponse)
def admin_audit_logs_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "admin/audit_logs.html", _ctx(request, page="admin_audit_logs")
    )


# ── Webhooks management ──────────────────────────────────────────
@router.get("/webhooks", response_class=HTMLResponse)
def webhooks_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "webhooks/index.html", _ctx(request, page="webhooks")
    )


@router.get("/webhooks/{webhook_id}", response_class=HTMLResponse)
def webhook_detail_page(request: Request, webhook_id: int):
    return request.app.state.templates.TemplateResponse(
        "webhooks/detail.html",
        _ctx(request, page="webhook_detail", webhook_id=webhook_id),
    )


# ── Scheduled transfers ───────────────────────────────────────────
@router.get("/scheduled-transfers", response_class=HTMLResponse)
def scheduled_transfers_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "scheduled_transfers/index.html", _ctx(request, page="scheduled_transfers")
    )


@router.get("/scheduled-transfers/{schedule_id}", response_class=HTMLResponse)
def scheduled_transfer_detail_page(request: Request, schedule_id: int):
    return request.app.state.templates.TemplateResponse(
        "scheduled_transfers/detail.html",
        _ctx(request, page="scheduled_transfer_detail", schedule_id=schedule_id),
    )


# ── Beneficiaries ─────────────────────────────────────────────────
@router.get("/beneficiaries", response_class=HTMLResponse)
def beneficiaries_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "beneficiaries/index.html", _ctx(request, page="beneficiaries")
    )


# ── Notifications center ──────────────────────────────────────────
@router.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "notifications/index.html", _ctx(request, page="notifications")
    )


# ── Analytics ─────────────────────────────────────────────────────
@router.get("/analytics", response_class=HTMLResponse)
def analytics_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "analytics/index.html", _ctx(request, page="analytics")
    )
