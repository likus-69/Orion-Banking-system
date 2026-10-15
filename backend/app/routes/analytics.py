"""Analytics API routes — aggregated transaction insights for the user's own data."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.user import User
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
def get_summary(
    days: int | None = Query(
        90,
        ge=1,
        le=3650,
        description="Number of days to look back. Omit or send 'all' for all-time.",
    ),
    all_time: bool = Query(False, description="Set to true for all-time view."),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregated analytics for the authenticated user.

    Returns:
      - kpi: total income, total expenses, net change, avg tx size, current balance
      - balance_series: daily closing balance time series (line chart)
      - monthly_income_vs_expense: per-month breakdown (stacked bar)
      - by_category: outgoing money grouped by transaction category (doughnut)
      - top_counterparties: top 8 people by transfer volume (horizontal bar)
    """
    service = AnalyticsService(db)
    range_days = None if all_time else days
    return service.summary(current_user, days=range_days)
