"""Beneficiary tests — CRUD, validation, search, cross-user, cap enforcement."""
from __future__ import annotations


# ── Create ────────────────────────────────────────────────────────
def test_create_beneficiary(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    r = client.post("/api/beneficiaries", json={
        "recipient_account_number": b["account_number"],
        "nickname": "Bob the builder",
        "category": "friend",
    }, headers=registered_user["headers"])
    assert r.status_code == 201
    body = r.json()
    assert body["recipient_name"] == "Bob Smith"
    assert body["nickname"] == "Bob the builder"
    assert body["category"] == "friend"
    assert body["owner_user_id"] == registered_user["user"]["id"]


def test_create_validates_recipient_exists(client, registered_user):
    r = client.post("/api/beneficiaries", json={
        "recipient_account_number": "00000000000000",
    }, headers=registered_user["headers"])
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "account_not_found"


def test_create_rejects_self(client, registered_user):
    r = client.post("/api/beneficiaries", json={
        "recipient_account_number": registered_user["user"]["account_number"],
    }, headers=registered_user["headers"])
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "self_transfer_forbidden"


def test_create_rejects_duplicate(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    # First save — ok
    r1 = client.post("/api/beneficiaries", json={
        "recipient_account_number": b["account_number"],
        "nickname": "First save",
    }, headers=registered_user["headers"])
    assert r1.status_code == 201
    # Second save — should fail
    r2 = client.post("/api/beneficiaries", json={
        "recipient_account_number": b["account_number"],
        "nickname": "Second save",
    }, headers=registered_user["headers"])
    assert r2.status_code == 422
    assert r2.json()["detail"]["error"]["code"] == "beneficiary_already_exists"


def test_create_requires_auth(client):
    r = client.post("/api/beneficiaries", json={
        "recipient_account_number": "12345678901234",
    })
    assert r.status_code == 401


# ── List + search ────────────────────────────────────────────────
def test_list_only_my_beneficiaries(client, registered_user):
    # Bob adds Alice
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    client.post("/api/beneficiaries", json={
        "recipient_account_number": b["account_number"],
        "nickname": "Bob",
    }, headers=registered_user["headers"])

    tok_b = client.post("/api/auth/login",
                        json={"email":"bob@orionbank.com","pin":"7351"}).json()["access_token"]
    r = client.get("/api/beneficiaries",
                   headers={"Authorization": f"Bearer {tok_b}"})
    assert r.status_code == 200
    # Bob has no saved beneficiaries
    assert len(r.json()) == 0


def test_search_by_nickname(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    client.post("/api/beneficiaries", json={
        "recipient_account_number": b["account_number"],
        "nickname": "Best buddy",
    }, headers=registered_user["headers"])
    r = client.get("/api/beneficiaries/search?q=buddy", headers=registered_user["headers"])
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["nickname"] == "Best buddy"


def test_search_by_account_number_prefix(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    client.post("/api/beneficiaries", json={
        "recipient_account_number": b["account_number"],
    }, headers=registered_user["headers"])
    # Search by first 6 digits
    r = client.get(f"/api/beneficiaries/search?q={b['account_number'][:6]}",
                   headers=registered_user["headers"])
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_search_returns_empty_for_no_match(client, registered_user):
    r = client.get("/api/beneficiaries/search?q=zzznomatch",
                   headers=registered_user["headers"])
    assert r.status_code == 200
    assert r.json() == []


# ── Update ────────────────────────────────────────────────────────
def test_update_beneficiary(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    r = client.post("/api/beneficiaries", json={
        "recipient_account_number": b["account_number"],
    }, headers=registered_user["headers"])
    bid = r.json()["id"]
    r = client.patch(f"/api/beneficiaries/{bid}", json={
        "nickname": "Updated nickname",
        "category": "business",
    }, headers=registered_user["headers"])
    assert r.status_code == 200
    assert r.json()["nickname"] == "Updated nickname"
    assert r.json()["category"] == "business"


def test_update_clears_nickname_with_empty_string(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    r = client.post("/api/beneficiaries", json={
        "recipient_account_number": b["account_number"],
        "nickname": "Bob",
    }, headers=registered_user["headers"])
    bid = r.json()["id"]
    r = client.patch(f"/api/beneficiaries/{bid}", json={"nickname": ""},
                     headers=registered_user["headers"])
    assert r.status_code == 200
    assert r.json()["nickname"] is None


# ── Delete ────────────────────────────────────────────────────────
def test_delete_beneficiary(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    r = client.post("/api/beneficiaries", json={
        "recipient_account_number": b["account_number"],
    }, headers=registered_user["headers"])
    bid = r.json()["id"]
    r = client.delete(f"/api/beneficiaries/{bid}",
                      headers=registered_user["headers"])
    assert r.status_code == 204
    # Confirm gone
    r = client.get(f"/api/beneficiaries/{bid}",
                   headers=registered_user["headers"])
    assert r.status_code == 404


# ── Cross-user isolation ──────────────────────────────────────────
def test_cannot_view_other_users_beneficiary(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    r = client.post("/api/beneficiaries", json={
        "recipient_account_number": b["account_number"],
    }, headers=registered_user["headers"])
    bid = r.json()["id"]
    # Bob tries to view Alice's beneficiary
    tok_b = client.post("/api/auth/login",
                        json={"email":"bob@orionbank.com","pin":"7351"}).json()["access_token"]
    r = client.get(f"/api/beneficiaries/{bid}",
                   headers={"Authorization": f"Bearer {tok_b}"})
    assert r.status_code == 404


def test_cannot_delete_other_users_beneficiary(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    r = client.post("/api/beneficiaries", json={
        "recipient_account_number": b["account_number"],
    }, headers=registered_user["headers"])
    bid = r.json()["id"]
    tok_b = client.post("/api/auth/login",
                        json={"email":"bob@orionbank.com","pin":"7351"}).json()["access_token"]
    r = client.delete(f"/api/beneficiaries/{bid}",
                      headers={"Authorization": f"Bearer {tok_b}"})
    assert r.status_code == 404
    # Alice's beneficiary should still exist
    r = client.get(f"/api/beneficiaries/{bid}",
                   headers=registered_user["headers"])
    assert r.status_code == 200


# ── Save-from-transfer (opportunistic save) ──────────────────────
def test_save_from_transfer_creates_new(client, registered_user):
    carol = client.post("/api/auth/register",
                        json={"full_name":"Carol King","email":"carol@orionbank.com","pin":"6242"}).json()
    r = client.post("/api/beneficiaries/save-from-transfer", json={
        "recipient_account_number": carol["account_number"],
    }, headers=registered_user["headers"])
    assert r.status_code == 200
    assert r.json()["recipient_name"] == "Carol King"


def test_save_from_transfer_returns_existing_if_already_saved(client, registered_user):
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    r1 = client.post("/api/beneficiaries", json={
        "recipient_account_number": b["account_number"],
        "nickname": "First save",
    }, headers=registered_user["headers"])
    first_id = r1.json()["id"]
    # Now save-from-transfer for the same account
    r2 = client.post("/api/beneficiaries/save-from-transfer", json={
        "recipient_account_number": b["account_number"],
    }, headers=registered_user["headers"])
    assert r2.status_code == 200
    assert r2.json()["id"] == first_id


def test_save_from_transfer_validates_recipient_exists(client, registered_user):
    r = client.post("/api/beneficiaries/save-from-transfer", json={
        "recipient_account_number": "00000000000000",
    }, headers=registered_user["headers"])
    assert r.status_code == 404


# ── Cap enforcement ──────────────────────────────────────────────
def test_cap_at_50_beneficiaries(client, registered_user, db):
    """Creating more than 50 beneficiaries should fail with the limit error."""
    from app.models.beneficiary import Beneficiary, BeneficiaryCategory
    from app.services.token_service import hash_pin
    from app.models.user import KycStatus, User, UserRole

    # Pre-create 50 beneficiaries for the user (bypass API to be fast)
    user = db.query(User).filter(User.email == registered_user["email"]).first()
    for i in range(50):
        # Create a recipient user
        recipient = User(
            account_number=f"{10000000000000 + i:014d}",
            full_name=f"User {i}",
            email=f"user{i}@orionbank.com",
            pin_hash=hash_pin("0000"),
            balance=0,
            role=UserRole.customer,
            kyc_status=KycStatus.pending,
        )
        db.add(recipient)
        db.flush()
        db.add(Beneficiary(
            owner_user_id=user.id,
            recipient_account_number=recipient.account_number,
            recipient_name=recipient.full_name,
            category=BeneficiaryCategory.other,
        ))
    db.commit()

    # Create one more recipient
    extra = client.post("/api/auth/register",
                        json={"full_name":"Extra User","email":"extra@orionbank.com","pin":"6242"}).json()
    r = client.post("/api/beneficiaries", json={
        "recipient_account_number": extra["account_number"],
    }, headers=registered_user["headers"])
    assert r.status_code == 422
    assert r.json()["detail"]["error"]["code"] == "beneficiary_limit_reached"


# ── Page route ───────────────────────────────────────────────────
def test_beneficiaries_page_renders(client, registered_user):
    r = client.get("/beneficiaries", headers=registered_user["headers"],
                   follow_redirects=False)
    assert r.status_code == 200
    assert "Beneficiaries" in r.text
    assert "Add beneficiary" in r.text
