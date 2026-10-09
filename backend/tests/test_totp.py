"""TOTP / 2FA tests — setup, verify, login flow, backup codes, admin override."""
from __future__ import annotations

import pyotp


def _enable_2fa_for_user(client, headers) -> tuple[str, list[str]]:
    """Helper — runs setup + verify, returns (secret, backup_codes)."""
    r = client.post("/api/2fa/setup", headers=headers)
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    code = pyotp.TOTP(secret).now()
    r = client.post("/api/2fa/verify", json={"code": code}, headers=headers)
    assert r.status_code == 200, r.text
    return secret, r.json()["backup_codes"]


# ── Setup flow ────────────────────────────────────────────────────
def test_setup_returns_secret_and_qr(client, registered_user):
    r = client.post("/api/2fa/setup", headers=registered_user["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["secret"]  # base32, 16+ chars
    assert body["qr_png_base64"].startswith("iVBORw0KG")  # PNG magic in base64
    assert body["provisioning_uri"].startswith("otpauth://totp/")
    assert body["account"] == registered_user["email"]


def test_status_before_enable(client, registered_user):
    r = client.get("/api/2fa/status", headers=registered_user["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["backup_codes_remaining"] == 0


def test_verify_wrong_code_does_not_enable(client, registered_user):
    client.post("/api/2fa/setup", headers=registered_user["headers"])
    r = client.post("/api/2fa/verify", json={"code": "000000"},
                    headers=registered_user["headers"])
    assert r.status_code == 422
    # Status should still be disabled
    s = client.get("/api/2fa/status", headers=registered_user["headers"]).json()
    assert s["enabled"] is False


def test_verify_correct_code_enables_and_returns_backup_codes(client, registered_user):
    secret, codes = _enable_2fa_for_user(client, registered_user["headers"])
    assert len(codes) == 10
    # All codes are 8 chars from the safe alphabet
    safe = set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
    for c in codes:
        assert len(c) == 8
        assert set(c).issubset(safe)
    # Status should now reflect enabled
    s = client.get("/api/2fa/status", headers=registered_user["headers"]).json()
    assert s["enabled"] is True
    assert s["backup_codes_remaining"] == 10


def test_setup_requires_auth(client):
    r = client.post("/api/2fa/setup")
    assert r.status_code == 401


# ── Login flow with 2FA ──────────────────────────────────────────
def test_login_returns_needs_totp_when_enabled(client, registered_user):
    _enable_2fa_for_user(client, registered_user["headers"])
    r = client.post("/api/auth/login", json={
        "email": registered_user["email"],
        "pin": registered_user["pin"],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["needs_totp"] is True
    assert body["challenge_token"]
    assert body["access_token"] is None  # no access yet


def test_login_without_2fa_returns_access_token_directly(client, registered_user):
    r = client.post("/api/auth/login", json={
        "email": registered_user["email"],
        "pin": registered_user["pin"],
    })
    body = r.json()
    assert body["needs_totp"] is False
    assert body["access_token"]


def test_verify_totp_with_correct_code(client, registered_user):
    secret, _ = _enable_2fa_for_user(client, registered_user["headers"])
    login = client.post("/api/auth/login", json={
        "email": registered_user["email"],
        "pin": registered_user["pin"],
    }).json()
    code = pyotp.TOTP(secret).now()
    r = client.post("/api/auth/verify-totp", json={
        "challenge_token": login["challenge_token"],
        "code": code,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] > 0


def test_verify_totp_with_wrong_code(client, registered_user):
    _enable_2fa_for_user(client, registered_user["headers"])
    login = client.post("/api/auth/login", json={
        "email": registered_user["email"],
        "pin": registered_user["pin"],
    }).json()
    r = client.post("/api/auth/verify-totp", json={
        "challenge_token": login["challenge_token"],
        "code": "000000",
    })
    assert r.status_code == 401


def test_verify_totp_with_backup_code(client, registered_user):
    _, backup_codes = _enable_2fa_for_user(client, registered_user["headers"])
    login = client.post("/api/auth/login", json={
        "email": registered_user["email"],
        "pin": registered_user["pin"],
    }).json()
    r = client.post("/api/auth/verify-totp", json={
        "challenge_token": login["challenge_token"],
        "backup_code": backup_codes[0],
    })
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_backup_code_is_single_use(client, registered_user):
    _, backup_codes = _enable_2fa_for_user(client, registered_user["headers"])
    # First use — should succeed
    login = client.post("/api/auth/login", json={
        "email": registered_user["email"], "pin": registered_user["pin"],
    }).json()
    r = client.post("/api/auth/verify-totp", json={
        "challenge_token": login["challenge_token"],
        "backup_code": backup_codes[0],
    })
    assert r.status_code == 200
    # Second use of the same code — should fail
    login = client.post("/api/auth/login", json={
        "email": registered_user["email"], "pin": registered_user["pin"],
    }).json()
    r = client.post("/api/auth/verify-totp", json={
        "challenge_token": login["challenge_token"],
        "backup_code": backup_codes[0],
    })
    assert r.status_code == 401


def test_backup_code_count_decrements_after_use(client, registered_user):
    _, backup_codes = _enable_2fa_for_user(client, registered_user["headers"])
    login = client.post("/api/auth/login", json={
        "email": registered_user["email"], "pin": registered_user["pin"],
    }).json()
    client.post("/api/auth/verify-totp", json={
        "challenge_token": login["challenge_token"],
        "backup_code": backup_codes[0],
    })
    s = client.get("/api/2fa/status",
                   headers=registered_user["headers"]).json()
    assert s["backup_codes_remaining"] == 9


def test_invalid_challenge_token_rejected(client, registered_user):
    _enable_2fa_for_user(client, registered_user["headers"])
    r = client.post("/api/auth/verify-totp", json={
        "challenge_token": "invalid-token",
        "code": "123456",
    })
    assert r.status_code == 401


# ── Disable 2FA ──────────────────────────────────────────────────
def test_disable_with_totp_code(client, registered_user):
    secret, _ = _enable_2fa_for_user(client, registered_user["headers"])
    code = pyotp.TOTP(secret).now()
    r = client.post("/api/2fa/disable", json={"code": code},
                    headers=registered_user["headers"])
    assert r.status_code == 204
    s = client.get("/api/2fa/status", headers=registered_user["headers"]).json()
    assert s["enabled"] is False


def test_disable_with_backup_code(client, registered_user):
    _, backup_codes = _enable_2fa_for_user(client, registered_user["headers"])
    r = client.post("/api/2fa/disable", json={"backup_code": backup_codes[0]},
                    headers=registered_user["headers"])
    assert r.status_code == 204
    assert client.get("/api/2fa/status",
                      headers=registered_user["headers"]).json()["enabled"] is False


def test_disable_without_code_rejected(client, registered_user):
    _enable_2fa_for_user(client, registered_user["headers"])
    r = client.post("/api/2fa/disable", json={},
                    headers=registered_user["headers"])
    assert r.status_code == 422


def test_disable_with_wrong_code_rejected(client, registered_user):
    _enable_2fa_for_user(client, registered_user["headers"])
    r = client.post("/api/2fa/disable", json={"code": "000000"},
                    headers=registered_user["headers"])
    assert r.status_code == 422
    # 2FA should still be enabled
    assert client.get("/api/2fa/status",
                      headers=registered_user["headers"]).json()["enabled"] is True


# ── Regenerate backup codes ──────────────────────────────────────
def test_regenerate_backup_codes(client, registered_user):
    secret, original_codes = _enable_2fa_for_user(client, registered_user["headers"])
    code = pyotp.TOTP(secret).now()
    r = client.post("/api/2fa/regenerate-backup-codes", json={"code": code},
                    headers=registered_user["headers"])
    assert r.status_code == 200
    new_codes = r.json()["backup_codes"]
    assert len(new_codes) == 10
    # Old codes should no longer work
    login = client.post("/api/auth/login", json={
        "email": registered_user["email"], "pin": registered_user["pin"],
    }).json()
    r = client.post("/api/auth/verify-totp", json={
        "challenge_token": login["challenge_token"],
        "backup_code": original_codes[0],
    })
    assert r.status_code == 401
    # New code should work
    login = client.post("/api/auth/login", json={
        "email": registered_user["email"], "pin": registered_user["pin"],
    }).json()
    r = client.post("/api/auth/verify-totp", json={
        "challenge_token": login["challenge_token"],
        "backup_code": new_codes[0],
    })
    assert r.status_code == 200


# ── Admin override ───────────────────────────────────────────────
def test_admin_can_disable_user_2fa(client, admin_user, registered_user):
    _enable_2fa_for_user(client, registered_user["headers"])
    target_id = registered_user["user"]["id"]
    r = client.post(f"/api/admin/users/{target_id}/disable-2fa",
                    headers=admin_user["headers"])
    assert r.status_code == 200
    # User can now log in without TOTP
    login = client.post("/api/auth/login", json={
        "email": registered_user["email"], "pin": registered_user["pin"],
    }).json()
    assert login["needs_totp"] is False
    assert login["access_token"]


def test_customer_cannot_disable_others_2fa(client, admin_user, registered_user):
    """A regular customer should NOT be able to call /admin/users/{id}/disable-2fa."""
    _enable_2fa_for_user(client, registered_user["headers"])
    target_id = registered_user["user"]["id"]
    # Try as the customer themselves hitting the admin endpoint
    r = client.post(f"/api/admin/users/{target_id}/disable-2fa",
                    headers=registered_user["headers"])
    assert r.status_code == 403


# ── Encrypted-at-rest verification ────────────────────────────────
def test_totp_secret_is_encrypted_at_rest(client, registered_user, db):
    """Verify the secret stored in DB is NOT the plaintext TOTP secret."""
    _enable_2fa_for_user(client, registered_user["headers"])
    from app.models.user import User
    user = db.query(User).filter(User.email == registered_user["email"]).first()
    # The encrypted secret should not be a valid base32 TOTP secret
    assert user.totp_secret_enc is not None
    assert not user.totp_secret_enc.startswith("otpauth:")
    # Decryption should yield a valid base32 secret
    from app.services.totp_service import decrypt_secret
    plaintext = decrypt_secret(user.totp_secret_enc)
    # base32 secrets are 16+ chars, all uppercase A-Z + 2-7
    assert len(plaintext) >= 16
    assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in plaintext)


# ── Page route ───────────────────────────────────────────────────
def test_settings_page_has_2fa_section(client, registered_user):
    r = client.get("/settings", headers=registered_user["headers"],
                   follow_redirects=False)
    assert r.status_code == 200
    assert "Two-factor authentication" in r.text
    assert "Enable 2FA" in r.text
