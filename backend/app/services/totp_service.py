"""TOTP (Time-based One-Time Password) service — Google Authenticator compatible.

Provides:
- secret encryption at rest using Fernet (key derived from SECRET_KEY)
- provisioning URI + QR PNG generation for setup
- TOTP code verification (with ±1 timestep tolerance, like Google Auth)
- backup codes (10 single-use, bcrypt-hashed, shown once at setup)

Setup flow:
  1. POST /api/2fa/setup       → returns secret + qr_png_base64 + provisioning_uri
  2. POST /api/2fa/verify       → verifies first code; sets totp_enabled=True
                                   (returns backup codes — only shown once)
  3. POST /api/2fa/disable      → clears totp fields (requires current code)
  4. POST /api/2fa/regenerate-backup-codes → requires current code

Login flow:
  1. POST /api/auth/login       → if 2FA enabled: returns needs_totp=True +
                                   a temporary challenge token (10-min TTL)
  2. POST /api/auth/verify-totp → exchanges challenge token + TOTP code
                                   for a real access+refresh token pair

Recovery:
  - POST /api/auth/verify-totp also accepts a backup_code field
  - Used backup codes are removed (single-use)
  - Admins can disable via POST /api/admin/users/{id}/disable-2fa
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config import settings
from app.exceptions import AuthenticationError, ValidationError
from app.logging_config import get_logger
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService
from app.services.auth_service import (
    _DUMMY_PIN_HASH,
    hash_pin,
    verify_pin,
)
from app.services.token_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
)

log = get_logger(__name__)


# ── Encryption helpers ────────────────────────────────────────────
def _fernet_key() -> bytes:
    """Derive a 32-byte url-safe base64 key from settings.SECRET_KEY.

    The same SECRET_KEY always yields the same Fernet key, so TOTP secrets
    survive a restart but are useless without the SECRET_KEY.
    """
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    return Fernet(_fernet_key())


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a TOTP secret for at-rest storage. Returns base64 string."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt an encrypted TOTP secret. Raises if the key changed."""
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise AuthenticationError("Could not decrypt TOTP secret — server SECRET_KEY may have changed.") from exc


# ── Challenge token (10-min TTL, only valid for verify-totp endpoint) ─
def create_challenge_token(email: str) -> str:
    """A short-lived JWT that only authorises the /verify-totp step."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "iat": now,
        "exp": now + timedelta(minutes=10),
        "type": "totp_challenge",
        "jti": secrets.token_hex(8),
    }
    from jose import jwt as _jwt
    return _jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_challenge_token(token: str) -> str:
    """Verify + return the email claim. Raises AuthenticationError on any failure."""
    payload = decode_token(token, expected_type="totp_challenge")
    email = payload.get("sub")
    if not email:
        raise AuthenticationError("Malformed challenge token.")
    return email


# ── Backup codes ──────────────────────────────────────────────────
def _hash_backup_code(code: str) -> str:
    """Bcrypt-hash a backup code (with a fixed salt prefix for determinism)."""
    return hash_pin(code)


def _verify_backup_code(code: str, hashed: str) -> bool:
    return verify_pin(code, hashed)


def generate_backup_codes(count: int = 10) -> list[str]:
    """Generate `count` random 8-character backup codes (alphanumeric)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous chars (O/0/I/1)
    return [
        "".join(secrets.choice(alphabet) for _ in range(8))
        for _ in range(count)
    ]


def _serialize_backup_codes(plaintext_codes: list[str]) -> str:
    """Hash + comma-join for storage."""
    return ",".join(_hash_backup_code(c) for c in plaintext_codes)


def _parse_backup_codes(stored: str | None) -> list[str]:
    if not stored:
        return []
    return [c for c in stored.split(",") if c.strip()]


# ── Service ───────────────────────────────────────────────────────
class TotpService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.audit = AuditService(db)

    # ── Setup (step 1 of 2) ───────────────────────────────────────
    def begin_setup(self, user: User) -> dict:
        """Generate a fresh TOTP secret + QR code for the user.

        The secret is stored encrypted but totp_enabled stays False until
        the user verifies with a real code (see `complete_setup`).
        """
        secret = pyotp.random_base32()
        user.totp_secret_enc = encrypt_secret(secret)
        user.totp_setup_at = datetime.now(timezone.utc)
        # Don't enable yet — user must verify a code first.
        self.db.commit()

        provisioning_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email, issuer_name=settings.app_name
        )

        # Render QR code as base64 PNG so the UI can inline it.
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        self.audit.log(
            user_id=user.id,
            action="2fa_setup_started",
            details="User began 2FA setup (TOTP secret generated, not yet verified)",
        )
        self.db.commit()

        log.info("2fa.setup_started", user_id=user.id)
        return {
            "secret": secret,  # shown to user for manual entry if QR doesn't scan
            "qr_png_base64": png_b64,
            "provisioning_uri": provisioning_uri,
            "issuer": settings.app_name,
            "account": user.email,
        }

    # ── Setup (step 2 of 2) ───────────────────────────────────────
    def complete_setup(self, user: User, *, code: str) -> dict:
        """Verify the first TOTP code from the user's authenticator app.

        On success: enables 2FA, generates 10 backup codes (returned ONCE).
        On failure: raises ValidationError.
        """
        if not user.totp_secret_enc:
            raise ValidationError("No 2FA setup in progress. Call /2fa/setup first.")
        secret = decrypt_secret(user.totp_secret_enc)
        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):  # ±1 timestep = ±30s
            self.audit.log(
                user_id=user.id,
                action="2fa_setup_failed",
                details="Wrong TOTP code entered during setup",
            )
            self.db.commit()
            raise ValidationError("Invalid TOTP code. Try again.")

        # Generate backup codes
        backup_codes = generate_backup_codes(10)
        user.totp_backup_codes_hashed = _serialize_backup_codes(backup_codes)
        user.totp_enabled = True

        self.audit.log(
            user_id=user.id,
            action="2fa_enabled",
            details="User verified TOTP code and enabled 2FA",
        )
        self.db.commit()
        log.info("2fa.enabled", user_id=user.id)
        return {
            "enabled": True,
            "backup_codes": backup_codes,  # shown once
        }

    # ── Disable ──────────────────────────────────────────────────
    def disable(self, user: User, *, code: str | None = None, backup_code: str | None = None) -> None:
        """Disable 2FA — requires either a current TOTP code or a backup code."""
        if not user.totp_enabled:
            raise ValidationError("2FA is not enabled on this account.")

        verified = False
        if code:
            verified = self.verify_code(user, code)
        if not verified and backup_code:
            verified = self.use_backup_code(user, backup_code)
        if not verified:
            self.audit.log(
                user_id=user.id,
                action="2fa_disable_failed",
                details="Wrong code/backup code entered when disabling 2FA",
            )
            self.db.commit()
            raise ValidationError("Invalid code or backup code.")

        user.totp_enabled = False
        user.totp_secret_enc = None
        user.totp_backup_codes_hashed = None
        user.totp_setup_at = None
        self.audit.log(
            user_id=user.id,
            action="2fa_disabled",
            details="User disabled 2FA",
        )
        self.db.commit()
        log.info("2fa.disabled", user_id=user.id)

    # ── Regenerate backup codes ──────────────────────────────────
    def regenerate_backup_codes(self, user: User, *, code: str | None = None, backup_code: str | None = None) -> dict:
        """Generate a fresh set of 10 backup codes (invalidates old ones).

        Requires either a current TOTP code or a backup code as authorization.
        """
        if not user.totp_enabled:
            raise ValidationError("2FA is not enabled on this account.")

        verified = False
        if code:
            verified = self.verify_code(user, code)
        if not verified and backup_code:
            verified = self.use_backup_code(user, backup_code)
        if not verified:
            raise ValidationError("Invalid code or backup code.")

        new_codes = generate_backup_codes(10)
        user.totp_backup_codes_hashed = _serialize_backup_codes(new_codes)
        self.audit.log(
            user_id=user.id,
            action="2fa_backup_codes_regenerated",
            details="User regenerated backup codes",
        )
        self.db.commit()
        return {"backup_codes": new_codes}

    # ── Verify code (no side effects) ────────────────────────────
    def verify_code(self, user: User, code: str) -> bool:
        """Verify a 6-digit TOTP code without modifying state."""
        if not user.totp_enabled or not user.totp_secret_enc:
            return False
        try:
            secret = decrypt_secret(user.totp_secret_enc)
        except AuthenticationError:
            return False
        return pyotp.TOTP(secret).verify(code, valid_window=1)

    def use_backup_code(self, user: User, code: str) -> bool:
        """Try to consume a backup code. Returns True if matched + removed."""
        if not user.totp_enabled:
            return False
        stored = _parse_backup_codes(user.totp_backup_codes_hashed)
        for i, hashed in enumerate(stored):
            if _verify_backup_code(code, hashed):
                # Remove this one (single-use)
                stored.pop(i)
                user.totp_backup_codes_hashed = ",".join(stored) if stored else None
                self.db.flush()
                self.audit.log(
                    user_id=user.id,
                    action="2fa_backup_code_used",
                    details="A backup code was used for login",
                )
                self.db.commit()
                return True
        return False

    # ── Admin override ───────────────────────────────────────────
    def admin_disable(self, admin: User, target: User) -> None:
        """Admin force-disables 2FA on a user (e.g. lost phone)."""
        target.totp_enabled = False
        target.totp_secret_enc = None
        target.totp_backup_codes_hashed = None
        target.totp_setup_at = None
        self.audit.log(
            user_id=admin.id,
            action="admin_2fa_disabled",
            details=f"Admin force-disabled 2FA for user_id={target.id} (account {target.account_number})",
        )
        self.db.commit()
        log.info("admin.2fa_disabled", admin_id=admin.id, target_user_id=target.id)


__all__ = [
    "TotpService",
    "create_challenge_token",
    "decode_challenge_token",
    "decrypt_secret",
    "encrypt_secret",
    "generate_backup_codes",
]
