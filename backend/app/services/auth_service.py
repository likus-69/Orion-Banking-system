"""Auth service — register / login / refresh / logout flows."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.exceptions import (
    AuthenticationError,
    EmailAlreadyRegisteredError,
    WeakPinError,
)
from app.logging_config import get_logger
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService
from app.services.token_service import (
    TokenService,
    hash_pin,
    is_weak_pin,
    verify_pin,
)

log = get_logger(__name__)

# Pre-computed valid bcrypt hash of a random string, used only for the
# timing-attack mitigation on login attempts with unknown emails.
# Generated once per process so the hash is constant for the lifetime of the app.
_DUMMY_PIN_HASH = hash_pin("orion-timing-attack-dummy-pin-do-not-use")


class AuthService:
    """Pure auth flows."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.audit = AuditService(db)
        self.tokens = TokenService(db)

    # ── Register ───────────────────────────────────────────────────
    def register(
        self,
        *,
        full_name: str,
        email: str,
        pin: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> User:
        email = email.lower().strip()
        if self.users.get_by_email(email):
            raise EmailAlreadyRegisteredError()
        if is_weak_pin(pin):
            raise WeakPinError()

        account_number = self.users.generate_unique_account_number()
        user = User(
            account_number=account_number,
            full_name=full_name.strip(),
            email=email,
            pin_hash=hash_pin(pin),
            balance=0,
        )
        self.db.add(user)
        self.db.flush()

        self.audit.log(
            user_id=user.id,
            action="register",
            details=f"User registered account {user.account_number}",
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        self.db.commit()
        self.db.refresh(user)
        log.info("user.registered", user_id=user.id, account=user.account_number)
        return user

    # ── Login ──────────────────────────────────────────────────────
    def login(
        self,
        *,
        email: str,
        pin: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> tuple[User, str, str, int]:
        user = self.users.get_by_email(email)
        if user is None:
            # Always run a hash verify to avoid timing attacks revealing which emails exist.
            verify_pin(pin, _DUMMY_PIN_HASH)
            raise AuthenticationError("Invalid email or PIN.")
        if user.is_locked:
            self.audit.log(
                user_id=user.id,
                action="login_blocked_locked",
                details="Attempted login on locked account",
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )
            self.db.commit()
            raise AuthenticationError("Account is locked. Please contact support.")

        if not verify_pin(pin, user.pin_hash):
            self.users.increment_failed_login(user)
            self.audit.log(
                user_id=user.id,
                action="login_failed",
                details=f"Failed login attempt #{user.failed_login_attempts}",
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )
            self.db.commit()
            raise AuthenticationError("Invalid email or PIN.")

        self.users.reset_failed_login(user)
        access, refresh, expires_in = self.tokens.issue_token_pair(user)
        self.audit.log(
            user_id=user.id,
            action="login_success",
            details="User logged in successfully",
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        self.db.commit()
        log.info("user.login", user_id=user.id)
        return user, access, refresh, expires_in

    # ── Refresh ────────────────────────────────────────────────────
    def refresh(self, refresh_token: str) -> tuple[str, str, int]:
        access, new_refresh, expires_in = self.tokens.rotate_refresh_token(refresh_token)
        self.db.commit()
        return access, new_refresh, expires_in

    # ── Logout ────────────────────────────────────────────────────
    def logout(self, user: User) -> None:
        self.tokens.revoke_all_for_user(user.id)
        self.audit.log(user_id=user.id, action="logout", details="User logged out")
        self.db.commit()


__all__ = ["AuthService"]
