"""Экспертиза и прогноз (ЧТЗ-3, EXP-01 – EXP-15)."""
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.config import METHOD
from app.db import get_db
from app.deps import csrf, current_user, flash, render, require
from app.expertise import delphi, risk, service
from app.notify import notify
from app.security import audit

router = APIRouter(prefix="/cabinet/projects/{event_id}")


def _ev(db: Session, event_id: int) -> m.Event:
    ev = db.get(m.Event, event_id)
    if not ev:
        raise HTTPException(404, "Проект не найден")
    return ev


@router.post("/experts", dependencies=[Depends(csrf)])
async def assign_experts(event_id: int, request: Request, db: Session = Depends(get_db),
                         user: m.User = Depends(require("head"))):
    ev = _ev(db, event_id)
    ids = {int(x) for x in (await request.form()).getlist("expert_id")}
    for ee in db.scalars(select(m.EventExpert).where(m.EventExpert.event_id == ev.id)):
        if ee.expert_id not in ids:
            db.delete(ee)
    current = {ee.expert_id for ee in db.scalars(select(m.EventExpert).where(m.EventExpert.event_id == ev.id))}
    for eid in ids - current:
        ex = db.get(m.Expert, eid)
        if ex and ex.user_id != ev.author_id:  # автор не оценивает свой проект (EXP-01)
            db.add(m.EventExpert(event_id=ev.id, expert_id=eid))
    db.commit()
    flash(request, "Состав экспертов сохранён")
    return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=expertise", 303)


@router.post("/rounds", dependencies=[Depends(csrf)])
def open_round(event_id: int, request: Request, deadline: str = Form(""), db: Session = Depends(get_db),
               user: m.User = Depends(require("head"))):
    ev = _ev(db, event_id)
    if ev.status != "review":
        raise HTTPException(400, "Тур открывается только для проекта «На экспертизе»")
    last = service.latest_round(db, ev.id)
    if last and last.is_open:
        flash(request, "Предыдущий тур ещё открыт", "error")
        return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=expertise", 303)
    no = (last.round_no + 1) if last else 1
    if no > METHOD["max_rounds"]:
        flash(request, f"Не более {METHOD['max_rounds']} туров на проект", "error")
        return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=expertise", 303)
    rnd = m.ExpertiseRound(event_id=ev.id, round_no=no, deadline=date.fromisoformat(deadline) if deadline else None)
    db.add(rnd)
    db.flush()
    if last:  # второй тур: переносим оценки первого как черновик, эксперт видит медианы
        for e in db.scalars(select(m.Evaluation).where(m.Evaluation.round_id == last.id)):
            db.add(m.Evaluation(round_id=rnd.id, expert_id=e.expert_id, criterion_id=e.criterion_id,
                                station_id=e.station_id, score=e.score, comment=e.comment, submitted=False))
        for r in db.scalars(select(m.RiskAssessment).where(m.RiskAssessment.round_id == last.id)):
            db.add(m.RiskAssessment(round_id=rnd.id, station_id=r.station_id, expert_id=r.expert_id,
                                    probability=r.probability, impact=r.impact, comment=r.comment))
    for ee in db.scalars(select(m.EventExpert).where(m.EventExpert.event_id == ev.id)):
        ex = db.get(m.Expert, ee.expert_id)
        notify(db, ex.user, f"Открыт тур {no} экспертизы «{ev.title}»"
               + (f", срок до {rnd.deadline:%d.%m}" if rnd.deadline else ""), f"/cabinet/projects/{ev.id}/evaluate")
    audit(db, user.id, "round_open", ev.code, str(no))
    db.commit()
    flash(request, f"Тур {no} открыт, эксперты получили уведомления")
    return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=expertise", 303)


@router.post("/rounds/close", dependencies=[Depends(csrf)])
def close_round(event_id: int, request: Request, db: Session = Depends(get_db),
                user: m.User = Depends(require("head"))):
    ev = _ev(db, event_id)
    rnd = service.latest_round(db, ev.id)
    if not rnd or not rnd.is_open:
        raise HTTPException(400, "Нет открытого тура")
    w = service.close_round(db, rnd, ev)
    if delphi.needs_second_round(w, rnd.round_no, METHOD["w_threshold"], METHOD["max_rounds"]):
        flash(request, f"Тур закрыт. Согласованность W = {w:.2f} ниже порога {METHOD['w_threshold']}: "
                       f"рекомендуем открыть второй тур Дельфи", "warn")
    else:
        flash(request, "Тур закрыт" + (f", W = {w:.2f}" if w is not None else ""))
    return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=expertise", 303)


@router.get("/evaluate")
def evaluate_form(event_id: int, request: Request, station: int | None = None, db: Session = Depends(get_db),
                  user: m.User = Depends(current_user)):
    ev = _ev(db, event_id)
    ex = user.expert
    if not ex or not db.get(m.EventExpert, (ev.id, ex.id)):
        raise HTTPException(403, "Вы не назначены экспертом этого проекта")
    rnd = service.latest_round(db, ev.id)
    if not rnd or not rnd.is_open:
        return render(request, "public/message.html", {"user": user, "title": "Тур закрыт",
                                                       "text": "Сейчас по проекту нет открытого тура экспертизы."})
    crits = ex.department.criteria
    targets = [None] + [s.id for s in ev.stations]
    cur = station if station in targets else None
    mine = {(e.criterion_id, e.station_id): e for e in db.scalars(select(m.Evaluation).where(
        m.Evaluation.round_id == rnd.id, m.Evaluation.expert_id == ex.id))}
    risks = {r.station_id: r for r in db.scalars(select(m.RiskAssessment).where(
        m.RiskAssessment.round_id == rnd.id, m.RiskAssessment.expert_id == ex.id))}
    medians = {}
    if rnd.round_no > 1:
        prev = db.scalar(select(m.ExpertiseRound).where(m.ExpertiseRound.event_id == ev.id,
                                                        m.ExpertiseRound.round_no == rnd.round_no - 1))
        medians = service.round_medians(db, prev)
    done = {t: all((c.id, t) in mine and mine[(c.id, t)].submitted for c in crits) for t in targets}
    st_obj = next((s for s in ev.stations if s.id == cur), None)
    return render(request, "cabinet/evaluate.html", {
        "user": user, "ev": ev, "rnd": rnd, "crits": crits, "cur": cur, "station": st_obj, "mine": mine,
        "risk": risks.get(cur), "medians": medians, "done": done, "zones": METHOD["risk_zones"]})


@router.post("/evaluate", dependencies=[Depends(csrf)])
async def evaluate_save(event_id: int, request: Request, db: Session = Depends(get_db),
                        user: m.User = Depends(current_user)):
    ev = _ev(db, event_id)
    ex = user.expert
    if not ex or not db.get(m.EventExpert, (ev.id, ex.id)):
        raise HTTPException(403, "Вы не назначены экспертом этого проекта")
    rnd = service.latest_round(db, ev.id)
    if not rnd or not rnd.is_open:
        raise HTTPException(400, "Тур закрыт")
    form = await request.form()
    station_id = int(form["station_id"]) if form.get("station_id") else None
    if station_id and station_id not in {s.id for s in ev.stations}:
        raise HTTPException(400, "Станция не относится к проекту")
    submit = form.get("action") == "submit"
    own = {c.id for c in ex.department.criteria}
    errors = []
    prev_scores = {}
    if rnd.round_no > 1:
        prev = db.scalar(select(m.ExpertiseRound).where(m.ExpertiseRound.event_id == ev.id,
                                                        m.ExpertiseRound.round_no == rnd.round_no - 1))
        prev_scores = {(e.criterion_id, e.station_id): e.score for e in db.scalars(select(m.Evaluation).where(
            m.Evaluation.round_id == prev.id, m.Evaluation.expert_id == ex.id))}
    for key, val in form.items():
        if not key.startswith("score_") or not val:
            continue
        cid = int(key[6:])
        if cid not in own:
            raise HTTPException(403, "Можно оценивать только критерии своего отдела")
        score = int(val)
        if not 1 <= score <= 5:
            errors.append("Балл от 1 до 5")
            continue
        comment = (form.get(f"comment_{cid}") or "").strip()
        if score <= 2 and not comment:
            errors.append("При балле 1 или 2 напишите комментарий")
        p = prev_scores.get((cid, station_id))
        if p is not None and abs(p - score) > 1 and not comment:
            errors.append("Балл изменён больше чем на 1 — укажите причину в комментарии")
        e = db.scalar(select(m.Evaluation).where(m.Evaluation.round_id == rnd.id, m.Evaluation.expert_id == ex.id,
                                                 m.Evaluation.criterion_id == cid,
                                                 m.Evaluation.station_id.is_(None) if station_id is None
                                                 else m.Evaluation.station_id == station_id))
        if not e:
            e = m.Evaluation(round_id=rnd.id, expert_id=ex.id, criterion_id=cid, station_id=station_id)
            db.add(e)
        e.score, e.comment, e.submitted = score, comment or None, submit or e.submitted
    if station_id and form.get("probability") and form.get("impact"):
        p, i = int(form["probability"]), int(form["impact"])
        if 1 <= p <= 5 and 1 <= i <= 5:
            r = db.scalar(select(m.RiskAssessment).where(m.RiskAssessment.round_id == rnd.id,
                                                         m.RiskAssessment.expert_id == ex.id,
                                                         m.RiskAssessment.station_id == station_id))
            if not r:
                r = m.RiskAssessment(round_id=rnd.id, expert_id=ex.id, station_id=station_id, probability=p, impact=i)
                db.add(r)
            r.probability, r.impact = p, i
            r.comment = (form.get("risk_comment") or "").strip() or None
    if errors:
        db.rollback()
        flash(request, "; ".join(dict.fromkeys(errors)), "error")
    else:
        db.commit()
        flash(request, "Оценка отправлена" if submit else "Черновик сохранён")
    q = f"?station={station_id}" if station_id else ""
    return RedirectResponse(f"/cabinet/projects/{ev.id}/evaluate{q}", 303)


@router.post("/forecast", dependencies=[Depends(csrf)])
def make_forecast(event_id: int, request: Request, db: Session = Depends(get_db),
                  user: m.User = Depends(require("head"))):
    ev = _ev(db, event_id)
    fc = service.build_forecast(db, ev)
    if ev.status == "review":
        rnd = service.latest_round(db, ev.id)
        if rnd and not rnd.is_open:
            ev.status = "evaluated"
            db.commit()
    flash(request, f"Прогноз рассчитан: {fc.recommendation}")
    return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=forecast", 303)


@router.get("/conclusion")
def conclusion(event_id: int, request: Request, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    ev = _ev(db, event_id)
    if not (user.has_role("head") or ev.author_id == user.id):
        raise HTTPException(403)
    fc = db.scalar(select(m.Forecast).where(m.Forecast.event_id == ev.id).order_by(m.Forecast.id.desc()))
    return render(request, "cabinet/conclusion.html", {"user": user, "ev": ev, "fc": fc,
                                                       "summ": service.summary(db, ev), "zones": risk.ZONE_NAMES})
