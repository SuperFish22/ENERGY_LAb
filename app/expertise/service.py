"""Сервисный слой: читает данные из БД, вызывает чистые функции, сохраняет результат."""
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.config import METHOD
from app.expertise import competence, delphi, forecast, risk, scoring


def latest_round(db: Session, event_id: int) -> m.ExpertiseRound | None:
    return db.scalar(select(m.ExpertiseRound).where(m.ExpertiseRound.event_id == event_id)
                     .order_by(m.ExpertiseRound.round_no.desc()))


def _criteria_maps(db: Session):
    crits = db.scalars(select(m.Criterion)).all()
    depts = db.scalars(select(m.Department)).all()
    return ({c.id: (c.department_id, c.weight) for c in crits}, {d.id: d.weight for d in depts},
            {d.id: d for d in depts})


def summary(db: Session, event: m.Event, rnd: m.ExpertiseRound | None = None) -> dict:
    """Сводка экспертизы последнего (или заданного) тура: S проекта и станций, W, риски."""
    rnd = rnd or latest_round(db, event.id)
    criteria, dept_w, depts = _criteria_maps(db)
    out = {"round": rnd, "S": None, "departments": {}, "stations": [], "W": None, "W_by_dept": {},
           "Q": None, "has_red": False, "missing_departments": [], "progress": []}
    if not rnd:
        return out
    evals = db.scalars(select(m.Evaluation).where(m.Evaluation.round_id == rnd.id,
                                                  m.Evaluation.submitted.is_(True))).all()
    experts = {e.id: e for e in db.scalars(select(m.Expert)).all()}
    comp = {eid: e.competence for eid, e in experts.items()}
    scores = [scoring.Score(e.expert_id, e.criterion_id, e.score, e.station_id) for e in evals]
    proj = scoring.object_score(scores, criteria, dept_w, comp, None)
    out.update(S=proj["S"], departments={depts[d].name: v for d, v in proj["departments"].items()},
               missing_departments=[depts[d].name for d in proj["missing_departments"]])
    # станции: баллы + риски
    risks = db.scalars(select(m.RiskAssessment).where(m.RiskAssessment.round_id == rnd.id)).all()
    levels = []
    for st in event.stations:
        st_scores = scoring.object_score(scores, criteria, dept_w, comp, st.id)["S"]
        rs = [r for r in risks if r.station_id == st.id]
        if rs:
            cw = [comp.get(r.expert_id, 0.7) for r in rs]
            p = scoring.weighted_mean([r.probability for r in rs], cw)
            i = scoring.weighted_mean([r.impact for r in rs], cw)
            lvl = risk.level(p, i)
            zn = risk.zone(lvl, METHOD["risk_zones"])
            levels.append(lvl)
        else:
            p = i = lvl = None
            zn = None
        out["stations"].append({"station": st, "S": st_scores, "P": p, "I": i, "R": lvl, "zone": zn,
                                "zone_name": risk.ZONE_NAMES.get(zn, "—")})
    out["has_red"] = any(s["zone"] == "red" for s in out["stations"])
    out["Q"] = risk.event_risk(levels, METHOD["kappa"]) if levels else None
    # согласованность: ранги станций по итоговому баллу каждого эксперта
    expert_ids = sorted({e.expert_id for e in evals})
    station_ids = [s.id for s in event.stations]

    def matrix_for(dept_id=None):
        rows = []
        for eid in expert_ids:
            if dept_id and experts[eid].department_id != dept_id:
                continue
            row = []
            for sid in station_ids:
                v = scoring.expert_total(scores, criteria, dept_w, eid, sid)
                row.append(v)
            if all(v is not None for v in row):
                rows.append(row)
        return rows
    out["W"] = delphi.kendall_w(matrix_for()) if station_ids else None
    for d in depts.values():
        w = delphi.kendall_w(matrix_for(d.id)) if station_ids else None
        if w is not None:
            out["W_by_dept"][d.name] = w
    # заполненность (кто отправил)
    assigned = db.scalars(select(m.Expert).join(m.EventExpert, m.EventExpert.expert_id == m.Expert.id)
                          .where(m.EventExpert.event_id == event.id)).all()
    sent = set(expert_ids)
    out["progress"] = [{"expert": e, "sent": e.id in sent} for e in assigned]
    return out


def round_medians(db: Session, rnd: m.ExpertiseRound) -> dict:
    """Медиана и IQR по каждому (критерий, станция) — показываются во втором туре."""
    evals = db.scalars(select(m.Evaluation).where(m.Evaluation.round_id == rnd.id,
                                                  m.Evaluation.submitted.is_(True))).all()
    groups = defaultdict(list)
    for e in evals:
        groups[(e.criterion_id, e.station_id)].append(e.score)
    return {k: delphi.median_iqr(v) for k, v in groups.items()}


def _features(ev: m.Event, score: float | None) -> forecast.EventFeatures:
    res = ev.result
    return forecast.EventFeatures(
        id=ev.id, title=ev.title, format_code=ev.format.code if ev.format else "00",
        price=float(ev.ticket_price or 0), capacity=int(ev.capacity or (ev.venue.capacity if ev.venue else 0) or 0),
        month=ev.planned_date.month if ev.planned_date else 1, score=score,
        guests=res.guests_count if res else None, tickets=res.tickets_sold if res else None,
        planned_budget=float(ev.planned_budget or 0), actual_cost=float(res.actual_cost) if res else None,
        rating=res.avg_rating if res else None)


def build_forecast(db: Session, event: m.Event) -> m.Forecast:
    """Полный расчёт A+Б+В+Г и сохранение в forecasts (EXP-11 – EXP-14)."""
    summ = summary(db, event)
    history = db.scalars(select(m.Event).where(m.Event.status == "analyzed", m.Event.id != event.id)).all()
    hist_f = []
    for h in history:
        last = db.scalar(select(m.Forecast).where(m.Forecast.event_id == h.id).order_by(m.Forecast.id.desc()))
        hist_f.append(_features(h, last.expert_score if last else None))
    target = _features(event, summ["S"])
    pred = forecast.predict(target, hist_f, METHOD["feature_weights"], METHOD["k_neighbors"],
                            [float(s.cost or 0) for s in event.stations])
    rounds_done = summ["round"].round_no if summ["round"] else 0
    rec, reasons = forecast.recommend(summ["S"], summ["has_red"], summ["W"], rounds_done, METHOD["max_rounds"],
                                      pred.get("budget"), pred.get("revenue"))
    if not pred.get("analogs"):
        reasons = reasons + ["Нет проведённых мероприятий-аналогов: количественный прогноз не строится"]
    fc = m.Forecast(event_id=event.id, expert_score=summ["S"], kendall_w=summ["W"],
                    attendance=pred.get("attendance"), attendance_low=pred.get("attendance_low"),
                    attendance_high=pred.get("attendance_high"), tickets_sold=pred.get("tickets_sold"),
                    revenue=pred.get("revenue"), budget=pred.get("budget"), avg_rating=pred.get("avg_rating"),
                    failure_risk=summ["Q"], recommendation=rec, reasons=reasons, analogs=pred.get("analogs"),
                    params={k: (list(v) if isinstance(v, tuple) else v) for k, v in METHOD.items()})
    db.add(fc)
    db.commit()
    return fc


def update_competence(db: Session, event: m.Event) -> list[tuple[str, float, float]]:
    """После ввода факта: пересчёт компетентности каждого эксперта, оценившего проект (EXP-16)."""
    if not event.result or event.result.avg_rating is None:
        return []
    rnd = latest_round(db, event.id)
    if not rnd:
        return []
    criteria, dept_w, _ = _criteria_maps(db)
    evals = db.scalars(select(m.Evaluation).where(m.Evaluation.round_id == rnd.id,
                                                  m.Evaluation.submitted.is_(True))).all()
    scores = [scoring.Score(e.expert_id, e.criterion_id, e.score, e.station_id) for e in evals]
    changes = []
    for eid in sorted({e.expert_id for e in evals}):
        s_e = scoring.expert_total(scores, criteria, dept_w, eid, None)
        if s_e is None:
            continue
        ex = db.get(m.Expert, eid)
        new = competence.update(ex.competence, s_e, event.result.avg_rating, METHOD["eta"],
                                METHOD["competence_bounds"])
        db.add(m.CompetenceHistory(expert_id=eid, event_id=event.id, old_value=ex.competence, new_value=new,
                                   reason=f"Факт мероприятия {event.code}"))
        changes.append((ex.user.full_name, ex.competence, new))
        ex.competence = new
    db.commit()
    return changes


def close_round(db: Session, rnd: m.ExpertiseRound, event: m.Event) -> float | None:
    rnd.closed_at = datetime.now()
    db.commit()
    w = summary(db, event, rnd)["W"]
    rnd.kendall_w = w
    db.commit()
    return w
