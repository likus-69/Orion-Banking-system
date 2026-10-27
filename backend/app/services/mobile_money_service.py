"""Mobile money deposit provider abstraction.

Supports:
  - "stub" provider: simulates a real MTN MoMo / Airtel Money API for dev/testing
  - MTN MoMo provider: uses https://momodeveloper.mtn.com API (needs real credentials)
  - Airtel Money provider: uses https://developers.airtel.africa API (needs real credentials)

To go live with real mobile money:
  1. Register at https://momodeveloper.mtn.com (MTN) or
     https://developers.airtel.africa (Airtel)
  2. Get your API credentials (API user ID + key for MTN, client ID + secret for Airtel)
  3. Add them to your .env file:
       MOBILE_MONEY_PROVIDER=mtn_momo
       MTN_MOMO_API_USER_ID=your_user_id
       MTN_MOMO_API_KEY=your_api_key
       MTN_MOMO_SUBSCRIPTION_KEY=your_subscription_key
       MTN_MOMO_ENVIRONMENT=sandbox   # or 'production'
  4. Restart the server — deposits via /api/deposit/initiate will now
     trigger real MTN MoMo API calls to collect money from the user's
     mobile money wallet.

Architecture:
  - DepositProvider is an abstract base with one method: initiate_deposit()
  - Each concrete provider implements the actual API calls
  - The stub provider returns a simulated "pending" status so you can
    test the UI flow without real credentials
  - The webhook callback endpoint (/api/deposit/callback/{provider})
    receives async status updates from MTN/Airtel and completes the
    deposit when the mobile money payment is confirmed
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.logging_config import get_logger

log = get_logger(__name__)


class DepositResult:
    """Result of initiating a mobile money deposit request."""

    def __init__(
        self,
        *,
        status: str,  # "pending" | "success" | "failed"
        reference: str,
        provider: str,
        message: str = "",
        provider_reference: Optional[str] = None,
    ):
        self.status = status
        self.reference = reference
        self.provider = provider
        self.message = message
        self.provider_reference = provider_reference


class DepositProvider:
    """Abstract base — concrete providers implement initiate_deposit()."""

    name: str = "base"

    def initiate_deposit(
        self,
        *,
        phone_number: str,
        amount: float,
        reference: str,
        payer_message: str = "",
    ) -> DepositResult:
        raise NotImplementedError

    def verify_callback_signature(self, payload: bytes, signature: str) -> bool:
        """Verify webhook callback signature from the provider."""
        return True  # Override in concrete providers


class StubDepositProvider(DepositProvider):
    """Simulates a mobile money API — for dev/testing without real credentials.

    Always returns "pending" so you can test the UI flow. In production,
    set MOBILE_MONEY_PROVIDER=mtn_momo or airtel_money.
    """

    name = "stub"

    def initiate_deposit(
        self,
        *,
        phone_number: str,
        amount: float,
        reference: str,
        payer_message: str = "",
    ) -> DepositResult:
        log.info(
            "mobile_money.stub_deposit_initiated",
            phone=phone_number,
            amount=amount,
            reference=reference,
        )
        return DepositResult(
            status="pending",
            reference=reference,
            provider=self.name,
            message="Deposit request simulated. In production, this would send a "
                    "prompt to the user's phone to approve the payment.",
            provider_reference=f"STUB-{secrets.token_hex(8).upper()}",
        )


class MtnMoMoProvider(DepositProvider):
    """MTN MoMo (Mobile Money) API integration.

    Requires:
      - MTN_MOMO_API_USER_ID
      - MTN_MOMO_API_KEY
      - MTN_MOMO_SUBSCRIPTION_KEY
      - MTN_MOMO_ENVIRONMENT (sandbox or production)

    API docs: https://momodeveloper.mtn.com/
    Flow:
      1. POST /collection/token/ → get access token
      2. POST /collection/v1_0/requesttopay → initiate deposit
      3. User receives prompt on phone to approve
      4. MTN calls our webhook → we complete the deposit
    """

    name = "mtn_momo"

    def __init__(self):
        self.api_user_id = settings.mtn_momo_api_user_id
        self.api_key = settings.mtn_momo_api_key
        self.subscription_key = settings.mtn_momo_subscription_key
        self.base_url = (
            "https://sandbox.api.mtn.com"
            if settings.mtn_momo_environment == "sandbox"
            else "https://api.mtn.com"
        )

    def initiate_deposit(
        self,
        *,
        phone_number: str,
        amount: float,
        reference: str,
        payer_message: str = "",
    ) -> DepositResult:
        import urllib.request
        import urllib.error
        import base64

        if not self.api_user_id or not self.api_key or not self.subscription_key:
            log.warning("mtn_momo.missing_credentials")
            return DepositResult(
                status="failed",
                reference=reference,
                provider=self.name,
                message="MTN MoMo credentials not configured. Set MTN_MOMO_API_USER_ID, "
                        "MTN_MOMO_API_KEY, and MTN_MOMO_SUBSCRIPTION_KEY in .env",
            )

        try:
            # Step 1: Get access token
            auth_string = f"{self.api_user_id}:{self.api_key}"
            auth_b64 = base64.b64encode(auth_string.encode()).decode()

            token_req = urllib.request.Request(
                f"{self.base_url}/collection/token/",
                method="POST",
                headers={
                    "Authorization": f"Basic {auth_b64}",
                    "Ocp-Apim-Subscription-Key": self.subscription_key,
                },
            )
            with urllib.request.urlopen(token_req, timeout=10) as resp:
                token_data = json.loads(resp.read())
                access_token = token_data["access_token"]

            # Step 2: Initiate request-to-pay
            x_reference_id = secrets.token_hex(16)
            pay_req = urllib.request.Request(
                f"{self.base_url}/collection/v1_0/requesttopay",
                method="POST",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Reference-Id": x_reference_id,
                    "X-Target-Environment": "sandbox"
                    if settings.mtn_momo_environment == "sandbox" else "production",
                    "Ocp-Apim-Subscription-Key": self.subscription_key,
                    "Content-Type": "application/json",
                },
                data=json.dumps({
                    "amount": str(amount),
                    "currency": "USD",
                    "externalId": reference,
                    "payer": {
                        "partyIdType": "MSISDN",
                        "partyId": phone_number.lstrip("+"),
                    },
                    "payerMessage": payer_message or f"Orion Banking deposit {reference}",
                    "payeeNote": f"Deposit to Orion account",
                }).encode(),
            )
            urllib.request.urlopen(pay_req, timeout=10)

            log.info(
                "mtn_momo.deposit_initiated",
                phone=phone_number,
                amount=amount,
                reference=reference,
                mtn_reference=x_reference_id,
            )
            return DepositResult(
                status="pending",
                reference=reference,
                provider=self.name,
                message="MTN MoMo payment prompt sent to your phone. Approve it to complete the deposit.",
                provider_reference=x_reference_id,
            )

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            log.error("mtn_momo.api_error", status=e.code, body=error_body)
            return DepositResult(
                status="failed",
                reference=reference,
                provider=self.name,
                message=f"MTN MoMo API error: {e.code} — {error_body[:200]}",
            )
        except Exception as e:
            log.error("mtn_momo.error", error=str(e))
            return DepositResult(
                status="failed",
                reference=reference,
                provider=self.name,
                message=f"MTN MoMo request failed: {e}",
            )


class AirtelMoneyProvider(DepositProvider):
    """Airtel Money API integration.

    Requires:
      - AIRTEL_CLIENT_ID
      - AIRTEL_CLIENT_SECRET
      - AIRTEL_ENVIRONMENT (sandbox or production)

    API docs: https://developers.airtel.africa/
    Flow:
      1. POST /auth/oauth2/token → get access token
      2. POST /merchant/v1/collections/ → initiate deposit
      3. User receives prompt on phone to approve
      4. Airtel calls our webhook → we complete the deposit
    """

    name = "airtel_money"

    def __init__(self):
        self.client_id = settings.airtel_client_id
        self.client_secret = settings.airtel_client_secret
        self.base_url = (
            "https://sandboxapi.airtel.africa"
            if settings.airtel_environment == "sandbox"
            else "https://openapi.airtel.africa"
        )

    def initiate_deposit(
        self,
        *,
        phone_number: str,
        amount: float,
        reference: str,
        payer_message: str = "",
    ) -> DepositResult:
        import urllib.request
        import urllib.error

        if not self.client_id or not self.client_secret:
            log.warning("airtel_money.missing_credentials")
            return DepositResult(
                status="failed",
                reference=reference,
                provider=self.name,
                message="Airtel Money credentials not configured. Set AIRTEL_CLIENT_ID "
                        "and AIRTEL_CLIENT_SECRET in .env",
            )

        try:
            # Step 1: Get access token
            token_req = urllib.request.Request(
                f"{self.base_url}/auth/oauth2/token",
                method="POST",
                headers={"Content-Type": "application/json"},
                data=json.dumps({
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                }).encode(),
            )
            with urllib.request.urlopen(token_req, timeout=10) as resp:
                token_data = json.loads(resp.read())
                access_token = token_data["access_token"]

            # Step 2: Initiate collection (request-to-pay)
            # Airtel phone numbers should be in format: country_code + number
            # e.g. "256700000000" for Uganda
            phone = phone_number.lstrip("+")
            if phone.startswith("256"):
                country = "UG"
                currency = "UGX"
            elif phone.startswith("254"):
                country = "KE"
                currency = "KES"
            else:
                country = "UG"
                currency = "UGX"

            # Convert USD to local currency (approximate — in production use real FX rates)
            local_amount = amount
            if currency == "UGX":
                local_amount = amount * 3800  # approx USD to UGX
            elif currency == "KES":
                local_amount = amount * 130  # approx USD to KES

            collection_req = urllib.request.Request(
                f"{self.base_url}/merchant/v1/collections/",
                method="POST",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "x-country": country,
                    "x-currency": currency,
                },
                data=json.dumps({
                    "reference": reference,
                    "subscriber": {
                        "msisdn": phone,
                    },
                    "transaction": {
                        "amount": str(int(local_amount)),
                        "country": country,
                        "currency": currency,
                        "id": reference,
                    },
                }).encode(),
            )
            with urllib.request.urlopen(collection_req, timeout=10) as resp:
                collection_data = json.loads(resp.read())
                airtel_ref = collection_data.get("data", {}).get("id", "")

            log.info(
                "airtel_money.deposit_initiated",
                phone=phone_number,
                amount=amount,
                reference=reference,
                airtel_reference=airtel_ref,
            )
            return DepositResult(
                status="pending",
                reference=reference,
                provider=self.name,
                message="Airtel Money payment prompt sent to your phone. Approve it to complete the deposit.",
                provider_reference=airtel_ref,
            )

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            log.error("airtel_money.api_error", status=e.code, body=error_body)
            return DepositResult(
                status="failed",
                reference=reference,
                provider=self.name,
                message=f"Airtel Money API error: {e.code} — {error_body[:200]}",
            )
        except Exception as e:
            log.error("airtel_money.error", error=str(e))
            return DepositResult(
                status="failed",
                reference=reference,
                provider=self.name,
                message=f"Airtel Money request failed: {e}",
            )


def get_deposit_provider() -> DepositProvider:
    """Factory — returns the configured deposit provider."""
    provider = settings.mobile_money_provider
    if provider == "mtn_momo":
        return MtnMoMoProvider()
    elif provider == "airtel_money":
        return AirtelMoneyProvider()
    else:
        return StubDepositProvider()
