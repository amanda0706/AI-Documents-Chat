from __future__ import annotations

from datetime import date

from .models import DeadlineItem, DocumentDetail


def build_deadlines(documents: list[DocumentDetail]) -> list[DeadlineItem]:
    today = date.today()
    items: list[DeadlineItem] = []
    for document in documents:
        for kind, raw_date in (("expiry", document.expiry_date), ("renewal", document.renewal_date)):
            if not raw_date:
                continue
            try:
                due_date = date.fromisoformat(raw_date)
            except ValueError:
                continue
            days_remaining = (due_date - today).days
            if 0 <= days_remaining <= 60:
                items.append(
                    DeadlineItem(
                        document_id=document.id,
                        filename=document.filename,
                        kind=kind,
                        due_date=raw_date,
                        days_remaining=days_remaining,
                    )
                )
    return sorted(items, key=lambda item: item.days_remaining)
