"""Statement PDF export."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from io import BytesIO

from app.deps import get_current_user, get_db
from app.models.user import User
from app.services.statement_service import StatementService

router = APIRouter(prefix="/api/statements", tags=["statements"])


@router.get("/export.pdf")
def export_statement(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    service = StatementService(db)
    pdf_bytes = service.build_pdf(
        current_user,
        start_date=start_date,
        end_date=end_date,
    )
    filename = f"orion-statement-{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
