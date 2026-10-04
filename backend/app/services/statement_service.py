"""Statement PDF generator using reportlab."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.user import User
from app.services.transaction_service import TransactionService

log = get_logger(__name__)


class StatementService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.tx_service = TransactionService(db)

    def build_pdf(
        self,
        user: User,
        *,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> bytes:
        transactions = self.tx_service.list_history(
            user, skip=0, limit=500, start_date=start_date, end_date=end_date
        )

        buf = bytearray()
        # Use a writeable BytesIO
        from io import BytesIO

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            title=f"Orion Bank Statement - {user.account_number}",
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "TitleCustom",
            parent=styles["Title"],
            textColor=colors.HexColor("#0a1220"),
            fontSize=22,
            spaceAfter=4,
        )
        sub_style = ParagraphStyle(
            "SubCustom",
            parent=styles["Normal"],
            textColor=colors.HexColor("#a9853f"),
            fontSize=10,
            spaceAfter=18,
        )
        normal_style = styles["Normal"]
        small_style = ParagraphStyle(
            "Small",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#666666"),
        )

        story = []
        story.append(Paragraph("Orion Banking Inc.", title_style))
        story.append(Paragraph("Account Statement", sub_style))

        story.append(
            Paragraph(
                f"<b>Account holder:</b> {user.full_name}<br/>"
                f"<b>Account number:</b> {user.account_number}<br/>"
                f"<b>Statement date:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}<br/>"
                f"<b>Current balance:</b> {float(user.balance):,.2f}",
                normal_style,
            )
        )
        story.append(Spacer(1, 14 * mm))

        if not transactions:
            story.append(Paragraph("<i>No transactions in this period.</i>", normal_style))
        else:
            header = ["Date", "Reference", "Type", "Direction", "Counterparty", "Amount"]
            data = [header]
            for tx in transactions:
                direction = "outgoing" if tx.from_account_id == user.id else "incoming"
                counterparty = (
                    tx.receiver.full_name if direction == "outgoing" and tx.receiver
                    else tx.sender.full_name if direction == "incoming" and tx.sender
                    else "—"
                )
                sign = "-" if direction == "outgoing" else "+"
                data.append(
                    [
                        tx.created_at.strftime("%Y-%m-%d %H:%M"),
                        tx.reference,
                        tx.type.value,
                        direction,
                        counterparty,
                        f"{sign} {float(tx.amount):,.2f}",
                    ]
                )

            table = Table(data, colWidths=[28*mm, 26*mm, 22*mm, 22*mm, 38*mm, 26*mm])
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0a1220")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#e8b85c")),
                        ("FONTSIZE", (0, 0), (-1, 0), 9),
                        ("FONTSIZE", (0, 1), (-1, -1), 8),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (5, 0), (5, -1), "RIGHT"),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(table)

        story.append(Spacer(1, 12 * mm))
        story.append(
            Paragraph(
                "This statement was generated automatically by Orion Banking Inc. "
                "If you spot any discrepancy, please contact support within 30 days.",
                small_style,
            )
        )

        doc.build(story)
        return buffer.getvalue()
