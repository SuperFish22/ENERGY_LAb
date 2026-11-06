"""Плановое обслуживание (запускается cron вместе с резервным копированием).

python -m app.maintenance  — удалить e-mail и имена покупателей через 30 дней после мероприятия (М-07, 152-ФЗ:
данные не хранятся дольше, чем нужно для цели — сверки анкет), очистить отправленные уведомления старше 30 дней
и просроченные коды привязки.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models as m
from app.db import SessionLocal

KEEP_DAYS = 30


def purge(db: Session, today: date | None = None) -> dict:
    today = today or date.today()
    border = today - timedelta(days=KEEP_DAYS)
    old_events = select(m.Event.id).where(m.Event.planned_date.is_not(None), m.Event.planned_date < border)
    tickets = db.scalars(select(m.Ticket).where(m.Ticket.event_id.in_(old_events),
                                                (m.Ticket.email.is_not(None)) | (m.Ticket.buyer_name.is_not(None))))
    n_tickets = 0
    for t in tickets:
        t.email = t.buyer_name = None
        n_tickets += 1
    now = datetime.combine(today, datetime.min.time())
    stale = now - timedelta(days=KEEP_DAYS)
    n_notes = db.execute(delete(m.Notification).where(m.Notification.sent_at.is_not(None),
                                                      m.Notification.sent_at < stale)).rowcount
    n_codes = db.execute(delete(m.LinkCode).where(m.LinkCode.expires_at < datetime.now())).rowcount
    db.commit()
    return {"tickets_anonymized": n_tickets, "notifications_deleted": n_notes, "link_codes_deleted": n_codes}


if __name__ == "__main__":
    with SessionLocal() as s:
        print(purge(s))
