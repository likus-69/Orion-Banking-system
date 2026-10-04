"""User repository — data access for User + RefreshToken."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.user import RefreshToken, User, UserRole
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self._db = db

    # ── Lookups ───────────────────────────────────────────────────
    def get_by_email(self, email: str) -> Optional[User]:
        return self._db.query(User).filter(User.email == email.lower().strip()).first()

    def get_by_account_number(self, account_number: str) -> Optional[User]:
        return (
            self._db.query(User)
            .filter(User.account_number == account_number)
            .first()
        )

    def get_for_update(self, user_id: int) -> Optional[User]:
        """SELECT ... FOR UPDATE — used for atomic balance mutations."""
        stmt = select(User).where(User.id == user_id).with_for_update()
        return self._db.execute(stmt).scalar_one_or_none()

    # ── Account-number generation (cryptographically random) ─────
    def generate_unique_account_number(self) -> str:
        """Generate a random 14-digit account number, retry on collision."""
        import secrets as _secrets

        for _ in range(10):
            candidate = f"{_secrets.randbelow(90_000_000_000_000) + 10_000_000_000_000}"
            if not self.get_by_account_number(candidate):
                return candidate
        # Extremely unlikely — but raise instead of silently failing.
        raise RuntimeError("Could not generate a unique account number after 10 attempts")

    # ── Refresh tokens ────────────────────────────────────────────
    def store_refresh_token(
        self, user_id: int, token_hash: str, expires_at: datetime
    ) -> RefreshToken:
        rt = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self._db.add(rt)
        self._db.flush()
        return rt

    def get_refresh_token(self, token_hash: str) -> Optional[RefreshToken]:
        return (
            self._db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .first()
        )

    def revoke_refresh_token(self, token_hash: str) -> None:
        rt = self.get_refresh_token(token_hash)
        if rt is not None:
            rt.revoked = True
            self._db.flush()

    def revoke_all_refresh_tokens(self, user_id: int) -> None:
        self._db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False,  # noqa: E712
        ).update({"revoked": True})
        self._db.flush()

    # ── Lockout state ─────────────────────────────────────────────
    def increment_failed_login(self, user: User) -> None:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.is_locked = True
        self._db.flush()

    def reset_failed_login(self, user: User) -> None:
        user.failed_login_attempts = 0
        user.is_locked = False
        self._db.flush()

    # ── Admin lookups ─────────────────────────────────────────────
    def list_users(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        role: Optional[UserRole] = None,
        search: Optional[str] = None,
    ) -> list[User]:
        """Paginated user listing with optional role filter + free-text search."""
        q = self._db.query(User)
        if role is not None:
            q = q.filter(User.role == role)
        if search:
            like = f"%{search.strip().lower()}%"
            q = q.filter(
                or_(
                    User.email.ilike(like),
                    User.full_name.ilike(like),
                    User.account_number.ilike(like),
                )
            )
        return q.order_by(User.created_at.desc()).offset(skip).limit(limit).all()

    def count_users(
        self,
        *,
        role: Optional[UserRole] = None,
        search: Optional[str] = None,
    ) -> int:
        q = self._db.query(User)
        if role is not None:
            q = q.filter(User.role == role)
        if search:
            like = f"%{search.strip().lower()}%"
            q = q.filter(
                or_(
                    User.email.ilike(like),
                    User.full_name.ilike(like),
                    User.account_number.ilike(like),
                )
            )
        return q.count()

    def get_admin_by_email(self, email: str) -> Optional[User]:
        """Look up a user that has admin role by email — used for admin login."""
        u = self.get_by_email(email)
        return u if (u and u.role == UserRole.admin) else None
