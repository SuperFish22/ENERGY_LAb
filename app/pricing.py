"""Как рассчитывается стоимость тусовки (калькулятор на главной и оценка в заявке).

Стоимость = (материалы на гостя × гости + работа команды × часы + доп. услуги) × (1 + доля на развитие Lab).
Материалы на гостя по группе формата считаются по «разборам полёта»: фактические затраты / пришедшие гости.
Если проведённых мероприятий группы меньше PRICING["min_history"], берётся норматив из настроек.
"""
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.config import PRICING


def per_guest_rates(db: Session, cfg: dict | None = None) -> dict[str, dict]:
    """{группа формата: {"rate": ₽ на гостя, "source": "history"|"norm", "n": число мероприятий}}."""
    cfg = cfg or PRICING
    rows = db.execute(select(m.EventFormat.group_name, m.EventResult.actual_cost, m.EventResult.guests_count)
                      .join(m.Event, m.Event.format_id == m.EventFormat.id)
                      .join(m.EventResult, m.EventResult.event_id == m.Event.id)
                      .where(m.Event.status == "analyzed", m.EventResult.guests_count > 0)).all()
    by_group: dict[str, list[float]] = {}
    for group, cost, guests in rows:
        by_group.setdefault(group, []).append(float(cost) / guests)
    out = {}
    for group, norm in cfg["base_per_guest"].items():
        hist = by_group.get(group, [])
        if len(hist) >= cfg["min_history"]:
            out[group] = {"rate": round(mean(hist)), "source": "history", "n": len(hist)}
        else:
            out[group] = {"rate": norm, "source": "norm", "n": len(hist)}
    return out


def estimate(rates: dict, group: str, guests: int, hours: float | None = None,
             options: list[str] | None = None, cfg: dict | None = None) -> dict:
    """Разбивка стоимости по статьям и итог."""
    cfg = cfg or PRICING
    hours = hours or cfg["hours_default"]
    rate = rates.get(group, {"rate": max(cfg["base_per_guest"].values())})["rate"]
    billable = max(guests, cfg["min_guests"])
    lines = [("Реквизит и материалы", rate * billable), ("Ведущие и актёры", cfg["team_per_hour"] * hours)]
    for key in options or []:
        if key in cfg["options"]:
            name, price = cfg["options"][key]
            lines.append((name, price))
    subtotal = sum(v for _, v in lines)
    lines.append(("Развитие Lab", subtotal * cfg["margin"]))
    total = round(subtotal * (1 + cfg["margin"]), -2)
    return {"lines": [(n, round(v)) for n, v in lines], "total": total,
            "per_guest": round(total / max(guests, 1), -1)}
