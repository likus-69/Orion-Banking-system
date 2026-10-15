"""Analytics tests — summary shape, KPIs, charts data, RBAC, date ranges."""
from __future__ import annotations


def test_summary_requires_auth(client):
    r = client.get("/api/analytics/summary")
    assert r.status_code == 401


def test_summary_default_90_days(client, registered_user):
    # Trigger a deposit
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers=registered_user["headers"])
    r = client.get("/api/analytics/summary", headers=registered_user["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["range_days"] == 90
    assert body["transaction_count"] == 1
    assert "kpi" in body
    assert "balance_series" in body
    assert "monthly_income_vs_expense" in body
    assert "by_category" in body
    assert "top_counterparties" in body


def test_summary_explicit_days(client, registered_user):
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers=registered_user["headers"])
    r = client.get("/api/analytics/summary?days=30",
                   headers=registered_user["headers"])
    assert r.status_code == 200
    assert r.json()["range_days"] == 30


def test_summary_all_time(client, registered_user):
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers=registered_user["headers"])
    r = client.get("/api/analytics/summary?all_time=true",
                   headers=registered_user["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["range_days"] is None
    assert body["start_date"] is None


def test_summary_kpis_after_deposit(client, registered_user):
    client.post("/api/transactions/deposit", json={"amount": 500},
                headers=registered_user["headers"])
    r = client.get("/api/analytics/summary", headers=registered_user["headers"])
    kpi = r.json()["kpi"]
    assert kpi["total_income"] == 500.0
    assert kpi["total_expenses"] == 0.0
    assert kpi["net_change"] == 500.0
    assert kpi["current_balance"] == 500.0
    assert kpi["transaction_count_in"] == 1
    assert kpi["transaction_count_out"] == 0
    assert kpi["avg_transaction_size"] == 500.0


def test_summary_kpis_after_withdrawal(client, registered_user):
    client.post("/api/transactions/deposit", json={"amount": 1000},
                headers=registered_user["headers"])
    client.post("/api/transactions/withdraw", json={"amount": 250},
                headers=registered_user["headers"])
    r = client.get("/api/analytics/summary", headers=registered_user["headers"])
    kpi = r.json()["kpi"]
    assert kpi["total_income"] == 1000.0
    assert kpi["total_expenses"] == 250.0
    assert kpi["net_change"] == 750.0
    assert kpi["current_balance"] == 750.0


def test_summary_kpis_after_transfer(client):
    """Outgoing transfer counts as expense; incoming transfer counts as income."""
    a = client.post("/api/auth/register",
                    json={"full_name":"Alice","email":"alice@orionbank.com","pin":"8421"}).json()
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    tok_a = client.post("/api/auth/login",
                        json={"email":"alice@orionbank.com","pin":"8421"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok_a}"}
    # Alice deposits 1000
    client.post("/api/transactions/deposit", json={"amount": 1000}, headers=headers)
    # Alice transfers 300 to Bob
    client.post("/api/transactions/transfer",
                json={"recipient_account_number": b["account_number"], "amount": 300},
                headers=headers)

    r = client.get("/api/analytics/summary", headers=headers)
    kpi = r.json()["kpi"]
    # From Alice's POV: income=1000 (deposit), expense=300 (transfer out)
    assert kpi["total_income"] == 1000.0
    assert kpi["total_expenses"] == 300.0
    assert kpi["net_change"] == 700.0


def test_balance_series_has_data_points(client, registered_user):
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers=registered_user["headers"])
    client.post("/api/transactions/deposit", json={"amount": 200},
                headers=registered_user["headers"])
    r = client.get("/api/analytics/summary", headers=registered_user["headers"])
    series = r.json()["balance_series"]
    assert len(series) >= 1
    # Each point has date + balance
    assert "date" in series[0]
    assert "balance" in series[0]
    # Final balance should match current
    assert series[-1]["balance"] == 300.0


def test_balance_series_empty_when_no_transactions(client, registered_user):
    r = client.get("/api/analytics/summary", headers=registered_user["headers"])
    series = r.json()["balance_series"]
    # Should still return 2 points (start + end) with the current balance
    assert len(series) >= 1
    assert series[-1]["balance"] == 0.0


def test_by_category_groups_outgoing(client):
    """Multiple outgoing transactions should be grouped by category."""
    a = client.post("/api/auth/register",
                    json={"full_name":"Alice","email":"alice@orionbank.com","pin":"8421"}).json()
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    tok_a = client.post("/api/auth/login",
                        json={"email":"alice@orionbank.com","pin":"8421"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok_a}"}
    client.post("/api/transactions/deposit", json={"amount": 1000}, headers=headers)
    # 2 transfers (category=transfer)
    client.post("/api/transactions/transfer",
                json={"recipient_account_number": b["account_number"], "amount": 100},
                headers=headers)
    client.post("/api/transactions/transfer",
                json={"recipient_account_number": b["account_number"], "amount": 200},
                headers=headers)
    # 1 withdrawal (category=general)
    client.post("/api/transactions/withdraw", json={"amount": 50}, headers=headers)

    r = client.get("/api/analytics/summary", headers=headers)
    by_cat = r.json()["by_category"]
    # Should have at least 2 categories: transfer + general
    cat_names = [c["category"] for c in by_cat]
    assert "transfer" in cat_names
    assert "general" in cat_names
    # Transfer total should be 300 (100 + 200)
    transfer_row = next(c for c in by_cat if c["category"] == "transfer")
    assert transfer_row["amount"] == 300.0


def test_top_counterparties(client):
    """Alice transfers to Bob + Carol; Bob is highest volume."""
    a = client.post("/api/auth/register",
                    json={"full_name":"Alice","email":"alice@orionbank.com","pin":"8421"}).json()
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    cc = client.post("/api/auth/register",
                     json={"full_name":"Carol King","email":"carol@orionbank.com","pin":"6242"}).json()
    tok_a = client.post("/api/auth/login",
                        json={"email":"alice@orionbank.com","pin":"8421"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok_a}"}
    client.post("/api/transactions/deposit", json={"amount": 5000}, headers=headers)
    client.post("/api/transactions/transfer",
                json={"recipient_account_number": b["account_number"], "amount": 500},
                headers=headers)
    client.post("/api/transactions/transfer",
                json={"recipient_account_number": cc["account_number"], "amount": 200},
                headers=headers)

    r = client.get("/api/analytics/summary", headers=headers)
    cp = r.json()["top_counterparties"]
    assert len(cp) == 2
    # Bob should be first (higher volume)
    assert cp[0]["name"] == "Bob Smith"
    assert cp[0]["total_out"] == 500.0
    assert cp[0]["total_in"] == 0.0
    assert cp[0]["total_volume"] == 500.0


def test_monthly_breakdown_format(client, registered_user):
    client.post("/api/transactions/deposit", json={"amount": 100},
                headers=registered_user["headers"])
    r = client.get("/api/analytics/summary", headers=registered_user["headers"])
    monthly = r.json()["monthly_income_vs_expense"]
    assert len(monthly) >= 1
    first = monthly[0]
    assert "month" in first  # YYYY-MM
    assert "income" in first
    assert "expense" in first
    assert first["income"] == 100.0
    assert first["expense"] == 0.0


def test_cross_user_isolation(client):
    """Alice's analytics should not include Bob's transactions."""
    a = client.post("/api/auth/register",
                    json={"full_name":"Alice","email":"alice@orionbank.com","pin":"8421"}).json()
    b = client.post("/api/auth/register",
                    json={"full_name":"Bob Smith","email":"bob@orionbank.com","pin":"7351"}).json()
    tok_a = client.post("/api/auth/login",
                        json={"email":"alice@orionbank.com","pin":"8421"}).json()["access_token"]
    tok_b = client.post("/api/auth/login",
                        json={"email":"bob@orionbank.com","pin":"7351"}).json()["access_token"]
    # Bob deposits 9999
    client.post("/api/transactions/deposit", json={"amount": 9999},
                headers={"Authorization": f"Bearer {tok_b}"})
    # Alice's analytics should show 0 transactions
    r = client.get("/api/analytics/summary",
                   headers={"Authorization": f"Bearer {tok_a}"})
    body = r.json()
    assert body["transaction_count"] == 0
    assert body["kpi"]["total_income"] == 0.0


def test_invalid_days_returns_422(client, registered_user):
    r = client.get("/api/analytics/summary?days=0",
                   headers=registered_user["headers"])
    assert r.status_code == 422  # ge=1


def test_days_capped_at_3650(client, registered_user):
    r = client.get("/api/analytics/summary?days=5000",
                   headers=registered_user["headers"])
    assert r.status_code == 422  # le=3650


# ── Page route ───────────────────────────────────────────────────
def test_analytics_page_renders(client, registered_user):
    r = client.get("/analytics", headers=registered_user["headers"],
                   follow_redirects=False)
    assert r.status_code == 200
    assert "Analytics" in r.text
    assert "balanceChart" in r.text
    assert "monthlyChart" in r.text
    assert "categoryChart" in r.text
