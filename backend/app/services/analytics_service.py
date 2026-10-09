"""Analytics service — aggregate transaction data for the analytics dashboard.

Returns ready-to-plot data:
  - Daily closing balance time series (line chart)
  - Income vs expenses per month (stacked bar)
  - Spending by category (doughnut)
  - Top counterparties by volume (horizontal bar)
  - Summary KPIs (totals, net change, avg)
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.repositories.transaction_repo import TransactionRepository

log = get_logger(__name__)


def _to_decimal(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def _strip_tz(d: datetime) -> datetime:
    """SQLite returns naive datetimes — strip tzinfo for consistent comparisons."""
    return d.replace(tzinfo=None) if d.tzinfo is not None else d


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class AnalyticsService:
    """Compute analytics for the authenticated user's transactions."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.tx_repo = TransactionRepository(db)

    def summary(self, user: User, *, days: Optional[int] = 90) -> dict:
        """Return all analytics data for the user within the given time window.

        `days=None` means "all time".
        """
        end = _now_utc()
        start: Optional[datetime] = None
        if days is not None:
            start = end - timedelta(days=days)

        # Fetch transactions in range (cap at 2000 to keep memory reasonable)
        txs = self.tx_repo.list_for_user(
            user.id, skip=0, limit=2000, start_date=start, end_date=end,
        )

        return {
            "range_days": days,
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat(),
            "transaction_count": len(txs),
            "kpi": self._compute_kpis(user, txs),
            "balance_series": self._balance_series(user, txs, start, end),
            "monthly_income_vs_expense": self._monthly_breakdown(txs, user.id),
            "by_category": self._by_category(txs, user.id),
            "top_counterparties": self._top_counterparties(txs, user.id, limit=8),
        }

    # ── KPIs ──────────────────────────────────────────────────────
    def _compute_kpis(self, user: User, txs: list[Transaction]) -> dict:
        total_in = Decimal("0")
        total_out = Decimal("0")
        count_in = 0
        count_out = 0

        for tx in txs:
            amount = _to_decimal(tx.amount)
            if tx.to_account_id == user.id:
                total_in += amount
                count_in += 1
            elif tx.from_account_id == user.id:
                total_out += amount
                count_out += 1

        net = total_in - total_out
        tx_count = count_in + count_out
        avg = (total_in + total_out) / tx_count if tx_count > 0 else Decimal("0")

        return {
            "total_income": float(total_in),
            "total_expenses": float(total_out),
            "net_change": float(net),
            "transaction_count_in": count_in,
            "transaction_count_out": count_out,
            "avg_transaction_size": float(avg),
            "current_balance": float(user.balance),
        }

    # ── Daily balance series ──────────────────────────────────────
    def _balance_series(
        self,
        user: User,
        txs: list[Transaction],
        start: Optional[datetime],
        end: datetime,
    ) -> list[dict]:
        """Daily closing-balance time series, oldest first.

        Reconstructs daily balances by walking transactions chronologically,
        starting from the balance at start_date (current balance minus net
        change in the window).
        """
        end_naive = _strip_tz(end)

        if not txs:
            anchor = _strip_tz(start) if start else end_naive
            return [
                {"date": anchor.date().isoformat(), "balance": float(user.balance)},
                {"date": end_naive.date().isoformat(), "balance": float(user.balance)},
            ]

        # Compute starting balance = current balance - net change in window
        window_net = Decimal("0")
        for tx in txs:
            amount = _to_decimal(tx.amount)
            if tx.to_account_id == user.id:
                window_net += amount
            elif tx.from_account_id == user.id:
                window_net -= amount
        starting_balance = _to_decimal(user.balance) - window_net

        # Sort oldest first
        sorted_txs = sorted(txs, key=lambda t: t.created_at)
        running = starting_balance

        # Group by day
        daily: dict[str, Decimal] = {}

        # Seed the series with the starting balance on the first day of the window
        first_tx_date = _strip_tz(sorted_txs[0].created_at)
        first_day = first_tx_date.date().isoformat()
        daily[first_day] = running

        for tx in sorted_txs:
            amount = _to_decimal(tx.amount)
            if tx.to_account_id == user.id:
                running += amount
            elif tx.from_account_id == user.id:
                running -= amount
            day_key = _strip_tz(tx.created_at).date().isoformat()
            daily[day_key] = running

        # Make sure the end date has a final point (in case today has no transactions)
        end_key = end_naive.date().isoformat()
        if end_key not in daily:
            daily[end_key] = running  # = current balance

        # Return sorted list (oldest first)
        return [
            {"date": k, "balance": float(v)}
            for k, v in sorted(daily.items())
        ]

    # ── Monthly income vs expense ─────────────────────────────────
    def _monthly_breakdown(self, txs: list[Transaction], user_id: int) -> list[dict]:
        """Income + expense per calendar month (YYYY-MM), oldest first."""
        per_month: dict[str, dict] = defaultdict(
            lambda: {"income": Decimal("0"), "expense": Decimal("0")}
        )
        for tx in txs:
            d = _strip_tz(tx.created_at)
            month_key = d.strftime("%Y-%m")
            amount = _to_decimal(tx.amount)
            if tx.to_account_id == user_id:
                per_month[month_key]["income"] += amount
            elif tx.from_account_id == user_id:
                per_month[month_key]["expense"] += amount

        return [
            {
                "month": k,
                "income": float(v["income"]),
                "expense": float(v["expense"]),
            }
            for k, v in sorted(per_month.items())
        ]

    # ── By category ────────────────────────────────────────────────
    def _by_category(self, txs: list[Transaction], user_id: int) -> list[dict]:
        """Sum of outgoing money (withdrawals + outgoing transfers) by category, descending."""
        per_cat: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for tx in txs:
            if tx.from_account_id == user_id:
                amount = _to_decimal(tx.amount)
                cat = tx.category.value if hasattr(tx.category, "value") else str(tx.category)
                per_cat[cat] += amount
        return [
            {"category": k, "amount": float(v)}
            for k, v in sorted(per_cat.items(), key=lambda x: -x[1])
        ]

    # ── Top counterparties ────────────────────────────────────────
    def _top_counterparties(
        self, txs: list[Transaction], user_id: int, *, limit: int = 8
    ) -> list[dict]:
        """Top people you've sent to / received from, by total volume."""
        per_party: dict[int, dict] = defaultdict(
            lambda: {
                "name": None,
                "total_in": Decimal("0"),
                "total_out": Decimal("0"),
                "count": 0,
            }
        )
        for tx in txs:
            if tx.type != TransactionType.transfer:
                continue
            if tx.from_account_id == user_id and tx.to_account_id is not None:
                p = tx.receiver
                if p is None:
                    continue
                per_party[p.id]["name"] = p.full_name
                per_party[p.id]["total_out"] += _to_decimal(tx.amount)
                per_party[p.id]["count"] += 1
            elif tx.to_account_id == user_id and tx.from_account_id is not None:
                p = tx.sender
                if p is None:
                    continue
                per_party[p.id]["name"] = p.full_name
                per_party[p.id]["total_in"] += _to_decimal(tx.amount)
                per_party[p.id]["count"] += 1

        rows = []
        for _party_id, data in per_party.items():
            total_volume = data["total_in"] + data["total_out"]
            rows.append({
                "name": data["name"] or "Unknown",
                "total_in": float(data["total_in"]),
                "total_out": float(data["total_out"]),
                "total_volume": float(total_volume),
                "transaction_count": data["count"],
            })
        rows.sort(key=lambda r: -r["total_volume"])
        return rows[:limit]
