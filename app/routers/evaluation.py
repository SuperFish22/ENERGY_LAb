"""Раздел «Оценка» (spec 005): экспертиза, прогноз и решение, итоговая оценка — отдельно от карточки проекта.

Карточка проекта отвечает на вопрос «что готовим», раздел «Оценка» — «насколько это хорошо и стоит ли запускать».
Права те же, что у проекта; формулы и параметры методики не меняются (METHOD в config.py).
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models as m
from app.config import METHOD
from app.db import get_db
from app.deps import current_user, render
from app.expertise import service
from app.routers.cabinet import EVAL_TABS, _event, project_page

router = APIRouter(prefix="/cabinet/evaluation")

# Этапы оценки по статусу проекта: (ключ, название, статусы)
STAGES = [
    ("expertise", "Экспертиза", ("review",)),
    ("decision", "Прогноз и решение", ("evaluated",)),
    ("approved", "Утверждены", ("approved", "on_sale")),
    ("review", "Итоговая оценка", ("held", "analyzed")),
]
EVAL_STATUSES = tuple(s for _, _, sts in STAGES for s in sts) + ("rework", "rejected")


def _visible(db: Session, user: m.User):
    stmt = select(m.Event).where(m.Event.status.in_(EVAL_STATUSES))
    if not user.has_role("head"):
        mine = [m.Event.author_id == user.id, m.Event.status.in_(("held", "analyzed"))]
        if user.expert:
            mine.append(m.Event.id.in_(select(m.EventExpert.event_id)
                                       .where(m.EventExpert.expert_id == user.expert.id)))
        stmt = stmt.where(or_(*mine))
    return stmt


@router.get("")
def overview(request: Request, stage: str = "", db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    stmt = _visible(db, user).order_by(m.Event.planned_date.desc().nulls_last(), m.Event.id.desc())
    wanted = next((sts for k, _, sts in STAGES if k == stage), None)
    if wanted:
        stmt = stmt.where(m.Event.status.in_(wanted))
    rows, waiting = [], []
    for ev in db.scalars(stmt.limit(100)):
        summ = service.summary(db, ev)
        rnd = summ["round"]
        fc = db.scalar(select(m.Forecast).where(m.Forecast.event_id == ev.id).order_by(m.Forecast.id.desc()))
        sent = sum(1 for p in summ["progress"] if p["sent"])
        row = {"ev": ev, "round": rnd, "S": summ["S"], "has_red": summ["has_red"], "sent": sent,
               "assigned": len(summ["progress"]), "forecast": fc,
               "mine_open": bool(user.expert and rnd and rnd.is_open and any(
                   p["expert"].id == user.expert.id and not p["sent"] for p in summ["progress"]))}
        rows.append(row)
        if row["mine_open"]:
            waiting.append(row)
    return render(request, "cabinet/evaluation.html", {
        "user": user, "rows": rows, "waiting": waiting, "stage": stage, "stages": STAGES, "nav": "evaluation"})


@router.get("/how")
def how(request: Request, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    """Интерактивный разбор: как устроены критерии, шкала, веса, методы А–Г и зоны риска."""
    depts = db.scalars(select(m.Department).order_by(m.Department.weight.desc(), m.Department.id)).all()
    crits = {d.id: db.scalars(select(m.Criterion).where(m.Criterion.department_id == d.id)
                              .order_by(m.Criterion.code)).all() for d in depts}
    total_w = sum(d.weight for d in depts) or 1
    return render(request, "cabinet/evaluation_how.html", {
        "user": user, "depts": depts, "crits": crits, "alpha": {d.id: d.weight / total_w for d in depts},
        "method": METHOD, "nav": "evaluation"})


@router.get("/{event_id}")
def evaluation_page(event_id: int, request: Request, tab: str = "expertise", db: Session = Depends(get_db),
                    user: m.User = Depends(current_user)):
    ev = _event(db, event_id, user)
    return project_page(request, db, user, ev, tab if tab in EVAL_TABS else "expertise", area="eval")
