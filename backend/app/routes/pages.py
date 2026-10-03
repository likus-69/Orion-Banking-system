"""Page routes — Jinja2-rendered HTML pages served by the backend.

This is the "UI" of the monolith: /login, /register, /dashboard, /transactions,
/transfer, /settings, /profile. Each route renders a template from app/templates/.
The HTML pages themselves call /api/* via fetch() for any dynamic data.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.config import settings
from app.deps import get_current_user

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


@router.get("/dashboard", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
def dashboard_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "dashboard/index.html", _ctx(request, page="dashboard")
    )


@router.get("/transactions", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
def transactions_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "dashboard/transactions.html", _ctx(request, page="transactions")
    )


@router.get("/transactions/{tx_id}", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
def transaction_detail_page(request: Request, tx_id: int):
    return request.app.state.templates.TemplateResponse(
        "dashboard/transaction_detail.html",
        _ctx(request, page="transaction_detail", tx_id=tx_id),
    )


@router.get("/transfer", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
def transfer_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "dashboard/transfer.html", _ctx(request, page="transfer")
    )


@router.get("/deposit", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
def deposit_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "dashboard/deposit.html", _ctx(request, page="deposit")
    )


@router.get("/settings", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
def settings_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "dashboard/settings.html", _ctx(request, page="settings")
    )


@router.get("/profile", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
def profile_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "dashboard/profile.html", _ctx(request, page="profile")
    )
