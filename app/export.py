"""Выгрузка данных для шаблонов Google Диска и дублирования (модуль М-09).

Сама система в Google не ходит: персональные данные остаются на российском сервере.
n8n на внешнем сервере забирает отсюда обезличенный набор полей и подставляет его в шаблон
(Google Docs — замена меток {{TITLE}} и т. п.; Google Sheets — строки реестра).
Гостей, e-mail и телефоны выгрузка не содержит.
"""
import csv
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.config import settings


def _f(x, nd=2):
    return None if x is None else round(float(x), nd)


def last_forecast(db: Session, ev: m.Event) -> m.Forecast | None:
    return db.scalar(select(m.Forecast).where(m.Forecast.event_id == ev.id).order_by(m.Forecast.id.desc()))


def event_placeholders(db: Session, ev: m.Event) -> dict:
    """Плоский словарь меток шаблона. Ключи совпадают с метками {{KEY}} в документе-шаблоне."""
    fc = last_forecast(db, ev)
    res = ev.result
    dec = db.scalar(select(m.Decision).where(m.Decision.event_id == ev.id).order_by(m.Decision.id.desc()))
    return {
        "CODE": ev.code, "TITLE": ev.title, "FORMAT": ev.format.name if ev.format else "",
        "STATUS": ev.status_name, "STAGE": ev.stage_name,
        "DATE": ev.planned_date.strftime("%d.%m.%Y") if ev.planned_date else "",
        "TIME": ev.start_time or "", "VENUE": ev.venue.name if ev.venue else "",
        "AGE": ev.age_rating, "PRICE": _f(ev.ticket_price), "BUDGET_PLAN": _f(ev.planned_budget),
        "CAPACITY": ev.capacity, "AUDIENCE": ev.target_audience or "", "DESCRIPTION": ev.description or "",
        "AUTHOR": ev.author.full_name if ev.author else "",
        "STATIONS_COUNT": len(ev.stations),
        "STATIONS_COST": _f(sum(float(s.cost or 0) for s in ev.stations)),
        "SCORE": _f(fc.expert_score) if fc else None, "KENDALL_W": _f(fc.kendall_w) if fc else None,
        "ATTENDANCE": fc.attendance if fc else None,
        "ATTENDANCE_RANGE": f"{fc.attendance_low}–{fc.attendance_high}" if fc and fc.attendance_low is not None else "",
        "TICKETS_FORECAST": fc.tickets_sold if fc else None, "REVENUE_FORECAST": _f(fc.revenue) if fc else None,
        "BUDGET_FORECAST": _f(fc.budget) if fc else None, "RATING_FORECAST": _f(fc.avg_rating) if fc else None,
        "RISK": _f(fc.failure_risk) if fc else None, "RECOMMENDATION": fc.recommendation if fc else "",
        "DECISION": m.EVENT_STATUSES.get(dec.decision, (dec.decision,))[0] if dec else "",
        "DECISION_COMMENT": (dec.comment or "") if dec else "",
        "GUESTS_FACT": res.guests_count if res else None, "TICKETS_FACT": res.tickets_sold if res else None,
        "REVENUE_FACT": _f(res.revenue) if res else None, "COST_FACT": _f(res.actual_cost) if res else None,
        "RATING_FACT": _f(res.avg_rating) if res else None,
        "URL": f"{settings.base_url}/cabinet/projects/{ev.id}",
    }


def event_tables(ev: m.Event) -> dict:
    return {"stations": [{"no": s.order_no, "title": s.title, "duration_min": s.duration_min,
                          "cost": _f(s.cost), "responsible": s.responsible.full_name if s.responsible else ""}
                         for s in ev.stations]}


REGISTRY_COLUMNS = ["CODE", "TITLE", "FORMAT", "STATUS", "DATE", "VENUE", "PRICE", "BUDGET_PLAN", "CAPACITY",
                    "SCORE", "ATTENDANCE", "BUDGET_FORECAST", "RISK", "RECOMMENDATION", "GUESTS_FACT",
                    "REVENUE_FACT", "COST_FACT", "RATING_FACT"]


def registry(db: Session) -> list[dict]:
    """Реестр всех мероприятий для дублирования в Google Таблицу (ключ строки — CODE)."""
    evs = db.scalars(select(m.Event).order_by(m.Event.code)).all()
    return [{k: event_placeholders(db, ev)[k] for k in REGISTRY_COLUMNS} for ev in evs]


def to_csv(rows: list[dict], columns: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, delimiter=";", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return "﻿" + buf.getvalue()          # BOM — чтобы Excel открыл кириллицу
