from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DECIMAL, String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_number: Mapped[str] = mapped_column(String(14), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    pin_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    balance: Mapped[float] = mapped_column(DECIMAL(precision=15, scale=2), default=0.00, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    sent_transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="sender",
        foreign_keys="Transaction.from_account_id",
    )
    received_transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="receiver",
        foreign_keys="Transaction.to_account_id",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    from_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    to_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[float] = mapped_column(DECIMAL(precision=15, scale=2), nullable=False)
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="completed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    sender: Mapped[Optional[User]] = relationship(
        "User",
        back_populates="sent_transactions",
        foreign_keys=[from_account_id],
    )
    receiver: Mapped[Optional[User]] = relationship(
        "User",
        back_populates="received_transactions",
        foreign_keys=[to_account_id],
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user: Mapped[Optional[User]] = relationship(back_populates="audit_logs")
