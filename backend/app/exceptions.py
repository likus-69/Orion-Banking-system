"""Domain-specific exceptions used across the Orion backend.

Routes catch these via the exception handlers in `main.py` and convert
them to JSON responses with consistent shape.
"""
from __future__ import annotations


class OrionError(Exception):
    """Base for all Orion domain errors."""

    status_code: int = 400
    error_code: str = "orion_error"
    message: str = "An error occurred."

    def __init__(self, message: str | None = None, *, error_code: str | None = None):
        self.message = message or self.message
        if error_code:
            self.error_code = error_code
        super().__init__(self.message)


# ── Auth ───────────────────────────────────────────────────────────
class AuthenticationError(OrionError):
    status_code = 401
    error_code = "authentication_failed"
    message = "Could not validate credentials."


class AuthorizationError(OrionError):
    status_code = 403
    error_code = "authorization_failed"
    message = "You are not allowed to perform this action."


# ── Account / user ─────────────────────────────────────────────────
class UserNotFoundError(OrionError):
    status_code = 404
    error_code = "user_not_found"
    message = "User not found."


class EmailAlreadyRegisteredError(OrionError):
    status_code = 409
    error_code = "email_already_registered"
    message = "Email is already registered."


class AccountNotFoundError(OrionError):
    status_code = 404
    error_code = "account_not_found"
    message = "Recipient account not found."


class SelfTransferError(OrionError):
    status_code = 400
    error_code = "self_transfer_forbidden"
    message = "You cannot transfer to your own account."


# ── Transactions ───────────────────────────────────────────────────
class InvalidAmountError(OrionError):
    status_code = 400
    error_code = "invalid_amount"
    message = "Amount must be greater than zero."


class InsufficientFundsError(OrionError):
    status_code = 422
    error_code = "insufficient_funds"
    message = "Insufficient funds for this operation."


class TransactionLimitExceededError(OrionError):
    status_code = 422
    error_code = "transaction_limit_exceeded"
    message = "This transaction exceeds the allowed limit."


class DailyLimitExceededError(OrionError):
    status_code = 422
    error_code = "daily_limit_exceeded"
    message = "You have reached your daily transaction limit."


class KycRequiredError(OrionError):
    status_code = 403
    error_code = "kyc_required"
    message = "KYC verification is required before making deposits. Please submit your KYC information in Settings."


class TransactionNotFoundError(OrionError):
    status_code = 404
    error_code = "transaction_not_found"
    message = "Transaction not found."


# ── Validation ─────────────────────────────────────────────────────
class ValidationError(OrionError):
    status_code = 422
    error_code = "validation_error"
    message = "Input validation failed."


class WeakPinError(ValidationError):
    error_code = "weak_pin"
    message = "PIN is too weak. Avoid sequential or repeated digits."


# ── Rate limiting ──────────────────────────────────────────────────
class RateLimitExceededError(OrionError):
    status_code = 429
    error_code = "rate_limit_exceeded"
    message = "Too many requests. Please slow down."
