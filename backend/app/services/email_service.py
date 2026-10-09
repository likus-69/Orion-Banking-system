"""Email service — sends transactional emails to users.

Backend is configurable via `settings.email_backend`:
- "console": prints the rendered email to stdout (dev default)
- "memory":  captures sent emails in a process-global list (test only)
- "smtp":    real SMTP via smtplib + aiosmtplib (production)

Design notes:
- The send_* helpers are fire-and-forget — they catch + log all exceptions
  so email delivery issues never break a financial transaction (configurable
  via `email_silent_failure`).
- HTML + plain-text bodies are rendered from Jinja2 templates in
  app/templates/email/.
- Per-event opt-out is honoured via User's `email_on_*` boolean columns.
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.config import settings
from app.logging_config import get_logger
from app.models.user import User

log = get_logger(__name__)


# ── Template environment ──────────────────────────────────────────
# Path: app/services/email_service.py → up one → app/templates/email/
EMAIL_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"

_email_env = Environment(
    loader=FileSystemLoader(str(EMAIL_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


# ── Memory backend (test-only) ────────────────────────────────────
# Populated by EmailService.send() when backend="memory". Cleared between tests.
_SENT_EMAILS: list[dict] = []


def reset_sent_emails() -> None:
    """Test helper: clear the captured-email list."""
    _SENT_EMAILS.clear()


def get_sent_emails() -> list[dict]:
    """Test helper: return emails captured by the memory backend."""
    return list(_SENT_EMAILS)


# ── EmailService ──────────────────────────────────────────────────
class EmailService:
    """Render + send transactional emails.

    Constructor takes the FastAPI `BackgroundTasks` queue (optional). If
    provided, sends are scheduled on the background task — otherwise they
    run synchronously (useful in tests).
    """

    def __init__(self, db: Optional[Session] = None, background_tasks=None) -> None:
        self.db = db
        self.background_tasks = background_tasks

    # ── Core send ────────────────────────────────────────────────
    def send(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
        from_name: Optional[str] = None,
        from_addr: Optional[str] = None,
    ) -> None:
        """Render and dispatch an email via the configured backend.

        Always fires-and-forgets: if `background_tasks` is set, the actual
        send is deferred to FastAPI's background task queue.
        """
        sender_name = from_name or settings.email_from_name
        sender_addr = from_addr or settings.email_from_address

        if self.background_tasks is not None:
            self.background_tasks.add_task(
                self._dispatch,
                to=to,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                sender_name=sender_name,
                sender_addr=sender_addr,
            )
        else:
            self._dispatch(
                to=to,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                sender_name=sender_name,
                sender_addr=sender_addr,
            )

    def _dispatch(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
        sender_name: str,
        sender_addr: str,
    ) -> None:
        """Pick the right backend and actually deliver the email."""
        backend = settings.email_backend
        try:
            if backend == "console":
                self._send_console(
                    to=to, subject=subject, html_body=html_body, text_body=text_body,
                    sender_name=sender_name, sender_addr=sender_addr,
                )
            elif backend == "memory":
                _SENT_EMAILS.append({
                    "to": to,
                    "subject": subject,
                    "html_body": html_body,
                    "text_body": text_body,
                    "from": f"{sender_name} <{sender_addr}>",
                })
            elif backend == "smtp":
                self._send_smtp(
                    to=to, subject=subject, html_body=html_body, text_body=text_body,
                    sender_name=sender_name, sender_addr=sender_addr,
                )
            else:
                log.warning("email.unknown_backend", backend=backend)
        except Exception as exc:
            log.error("email.send_failed", to=to, subject=subject, error=str(exc))
            if not settings.email_silent_failure:
                raise

    # ── Backends ────────────────────────────────────────────────
    def _send_console(self, *, to, subject, html_body, text_body, sender_name, sender_addr) -> None:
        # Pretty-printed to stdout for local dev.
        print("\n" + "=" * 70)
        print(f"📧 EMAIL  to: {to}")
        print(f"         from: {sender_name} <{sender_addr}>")
        print(f"         subject: {subject}")
        print("-" * 70)
        print(text_body)
        print("=" * 70 + "\n")

    def _send_smtp(self, *, to, subject, html_body, text_body, sender_name, sender_addr) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr((sender_name, sender_addr))
        msg["To"] = to
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=sender_addr.split("@")[-1])
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        if settings.smtp_use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
                s.starttls(context=context)
                if settings.smtp_username:
                    s.login(settings.smtp_username, settings.smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
                if settings.smtp_username:
                    s.login(settings.smtp_username, settings.smtp_password)
                s.send_message(msg)

    # ── Render helper ──────────────────────────────────────────
    def _render(self, template_name: str, context: dict) -> tuple[str, str]:
        """Render both text and HTML variants for a given template base name."""
        text_template = _email_env.get_template(f"{template_name}.txt")
        html_template = _email_env.get_template(f"{template_name}.html")
        return (
            text_template.render(**context),
            html_template.render(**context),
        )

    # ── Event helpers ──────────────────────────────────────────
    def send_welcome(self, user: User) -> None:
        text, html = self._render("welcome", {
            "user": user,
            "app_name": settings.app_name,
        })
        self.send(
            to=user.email,
            subject=f"Welcome to {settings.app_name}",
            html_body=html,
            text_body=text,
        )

    def send_deposit_confirmation(
        self, user: User, *, amount: str, reference: str, memo: Optional[str], new_balance: str
    ) -> None:
        if not getattr(user, "email_on_deposit", True):
            return
        text, html = self._render("deposit", {
            "user": user, "amount": amount, "reference": reference,
            "memo": memo, "new_balance": new_balance,
            "app_name": settings.app_name,
        })
        self.send(
            to=user.email,
            subject=f"Deposit of {amount} confirmed — {reference}",
            html_body=html, text_body=text,
        )

    def send_withdrawal_confirmation(
        self, user: User, *, amount: str, reference: str, memo: Optional[str], new_balance: str
    ) -> None:
        if not getattr(user, "email_on_withdrawal", True):
            return
        text, html = self._render("withdrawal", {
            "user": user, "amount": amount, "reference": reference,
            "memo": memo, "new_balance": new_balance,
            "app_name": settings.app_name,
        })
        self.send(
            to=user.email,
            subject=f"Withdrawal of {amount} confirmed — {reference}",
            html_body=html, text_body=text,
        )

    def send_transfer_outgoing(
        self, user: User, *, amount: str, reference: str, recipient_name: str,
        recipient_account: str, memo: Optional[str], new_balance: str
    ) -> None:
        if not getattr(user, "email_on_transfer_out", True):
            return
        text, html = self._render("transfer_outgoing", {
            "user": user, "amount": amount, "reference": reference,
            "recipient_name": recipient_name, "recipient_account": recipient_account,
            "memo": memo, "new_balance": new_balance,
            "app_name": settings.app_name,
        })
        self.send(
            to=user.email,
            subject=f"Transfer of {amount} sent — {reference}",
            html_body=html, text_body=text,
        )

    def send_transfer_incoming(
        self, user: User, *, amount: str, reference: str, sender_name: str,
        sender_account: str, memo: Optional[str], new_balance: str
    ) -> None:
        if not getattr(user, "email_on_transfer_in", True):
            return
        text, html = self._render("transfer_incoming", {
            "user": user, "amount": amount, "reference": reference,
            "sender_name": sender_name, "sender_account": sender_account,
            "memo": memo, "new_balance": new_balance,
            "app_name": settings.app_name,
        })
        self.send(
            to=user.email,
            subject=f"You received {amount} — {reference}",
            html_body=html, text_body=text,
        )

    def send_kyc_approved(self, user: User, *, reviewed_by: str) -> None:
        if not getattr(user, "email_on_kyc_decision", True):
            return
        text, html = self._render("kyc_approved", {
            "user": user, "reviewed_by": reviewed_by,
            "app_name": settings.app_name,
        })
        self.send(
            to=user.email,
            subject=f"KYC verified — {settings.app_name}",
            html_body=html, text_body=text,
        )

    def send_kyc_rejected(self, user: User, *, reason: str, reviewed_by: str) -> None:
        if not getattr(user, "email_on_kyc_decision", True):
            return
        text, html = self._render("kyc_rejected", {
            "user": user, "reason": reason, "reviewed_by": reviewed_by,
            "app_name": settings.app_name,
        })
        self.send(
            to=user.email,
            subject=f"KYC needs revision — {settings.app_name}",
            html_body=html, text_body=text,
        )
