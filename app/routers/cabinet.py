"""Личный кабинет (ЧТЗ-4): обзор, проекты, станции, статусы, факт, импорт продаж, задачи, обсуждения, профиль."""
import csv
import io
import os
import secrets
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import attachments, export, media, scenario, tasks_board
from app import models as m
from app import notify as notify_mod
from app.config import METHOD, settings
from app.db import get_db
from app.deps import csrf, current_user, flash, render
from app.expertise import review, service
from app.notify import notify, notify_heads
from app.security import audit

router = APIRouter(prefix="/cabinet")


def _event(db: Session, event_id: int, user: m.User, write: bool = False) -> m.Event:
    ev = db.get(m.Event, event_id)
    if not ev:
        raise HTTPException(404, "Проект не найден")
    is_head = user.has_role("head")
    is_author = ev.author_id == user.id
    assigned = user.expert and db.get(m.EventExpert, (ev.id, user.expert.id))
    if not (is_head or is_author or assigned or ev.status in ("on_sale", "held", "analyzed")):
        raise HTTPException(403, "Этот проект вам недоступен")
    if write and not (is_head or (is_author and ev.status in ("draft", "rework"))):
        raise HTTPException(403, "Проект можно менять только в статусах «Черновик» и «Доработка»")
    return ev


def _next_code(db: Session, year: int) -> str:
    n = db.scalar(select(func.count()).select_from(m.Event).where(m.Event.code.like(f"LAB-{year}-%"))) or 0
    while True:
        n += 1
        code = f"LAB-{year}-{n:02d}"
        if not db.scalar(select(m.Event).where(m.Event.code == code)):
            return code


# ------------------------------------------------------------------ обзор
@router.get("")
def dashboard(request: Request, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    tasks = db.scalars(select(m.Task).where(m.Task.assignee_id == user.id, m.Task.status != "done")
                       .order_by(m.Task.due_date.is_(None), m.Task.due_date)).all()
    to_rate = []
    if user.expert:
        for ee in db.scalars(select(m.EventExpert).where(m.EventExpert.expert_id == user.expert.id)):
            ev = db.get(m.Event, ee.event_id)
            rnd = service.latest_round(db, ev.id)
            if rnd and rnd.is_open:
                sent = db.scalar(select(m.Evaluation).where(m.Evaluation.round_id == rnd.id,
                                                            m.Evaluation.expert_id == user.expert.id,
                                                            m.Evaluation.submitted.is_(True)))
                to_rate.append({"ev": ev, "round": rnd, "sent": bool(sent)})
    dept_id = user.expert.department_id if user.expert else None
    disc = db.scalars(select(m.Discussion).where(m.Discussion.status == "open",
                                                 or_(m.Discussion.department_id == dept_id,
                                                     m.Discussion.author_id == user.id))
                      .order_by(m.Discussion.id.desc()).limit(5)).all()
    mine = db.scalars(select(m.Event).where(m.Event.author_id == user.id).order_by(m.Event.id.desc())).all()
    next_launch = db.scalar(select(m.Event).where(m.Event.status == "on_sale").order_by(m.Event.planned_date))
    return render(request, "cabinet/dashboard.html", {"user": user, "tasks": tasks, "to_rate": to_rate,
                                                      "discussions": disc, "mine": mine, "next_launch": next_launch})


# ------------------------------------------------------------------ проекты
@router.get("/projects")
def projects(request: Request, q: str = "", status: str = "", mine: int = 0, db: Session = Depends(get_db),
             user: m.User = Depends(current_user)):
    stmt = select(m.Event).order_by(m.Event.planned_date.desc().nulls_last(), m.Event.id.desc())
    if not user.has_role("head"):
        stmt = stmt.where(or_(m.Event.author_id == user.id, m.Event.status.in_(("on_sale", "held", "analyzed"))))
    if q:
        stmt = stmt.where(or_(m.Event.title.ilike(f"%{q}%"), m.Event.code.ilike(f"%{q}%")))
    wanted = [x for x in status.split(",") if x in m.EVENT_STATUSES]
    if wanted:
        stmt = stmt.where(m.Event.status.in_(wanted))
    if mine:
        stmt = stmt.where(m.Event.author_id == user.id)
    events = db.scalars(stmt).all()
    latest = {}
    for ev in events:
        latest[ev.id] = db.scalar(select(m.Forecast).where(m.Forecast.event_id == ev.id).order_by(m.Forecast.id.desc()))
    return render(request, "cabinet/projects.html", {"user": user, "events": events, "latest": latest, "q": q,
                                                     "status": status, "mine": mine,
                                                     "statuses": m.EVENT_STATUSES})


def _ref(db: Session):
    return {"formats": db.scalars(select(m.EventFormat).order_by(m.EventFormat.code)).all(),
            "venues": db.scalars(select(m.Venue).order_by(m.Venue.name)).all(),
            "ages": ["0+", "6+", "12+", "16+", "18+"]}


# ------------------------------------------------------------------ быстрое внесение прошедшей тусовки
def _num(v, default=None, lo=0.0, hi=1e9):
    try:
        x = float(str(v).replace(" ", "").replace("\u00a0", "").replace(",", "."))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, x))


@router.get("/archive/new")
def past_new(request: Request, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    if not user.has_role("head"):
        raise HTTPException(403, "Вносить прошедшие тусовки могут руководители")
    return render(request, "cabinet/past_form.html", {"user": user, "f": request.session.pop("past_form", None) or {},
                                                       "today": date.today().isoformat(), "nav": "projects",
                                                       **_ref(db)})


@router.post("/archive/new", dependencies=[Depends(csrf)])
async def past_create(request: Request, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    """Прошедшее мероприятие одной формой: сразу «Проанализирован», с фактом и фото —
    попадает в фотоальбом главной, в прогноз по аналогам и в калькулятор стоимости."""
    if not user.has_role("head"):
        raise HTTPException(403)
    form = await request.form()
    g = lambda k: (form.get(k) or "").strip() if isinstance(form.get(k) or "", str) else ""  # noqa: E731
    errors = []
    title = g("title")[:200]
    fmt = db.get(m.EventFormat, int(g("format_id"))) if g("format_id").isdigit() else None
    try:
        day = date.fromisoformat(g("planned_date"))
    except ValueError:
        day = None
    guests = _num(g("guests_count"))
    if len(title) < 3:
        errors.append("Название — от 3 символов")
    if not fmt:
        errors.append("Выберите формат")
    if not day or day > date.today():
        errors.append("Дата должна быть сегодня или в прошлом")
    if guests is None or guests < 1:
        errors.append("Сколько пришло гостей?")
    if errors:
        request.session["past_form"] = {k: g(k) for k in ("title", "format_id", "planned_date", "start_time",
                                                           "venue_id", "capacity", "ticket_price", "guests_count",
                                                           "tickets_sold", "revenue", "actual_cost",
                                                           "age_rating", "description")}
        flash(request, ". ".join(errors), "error")
        return RedirectResponse("/cabinet/archive/new", 303)
    price = _num(g("ticket_price"), 0)
    sold = int(_num(g("tickets_sold"), guests))
    cost = _num(g("actual_cost"), 0)
    venue = db.get(m.Venue, int(g("venue_id"))) if g("venue_id").isdigit() else None
    capacity = int(_num(g("capacity"), 0)) or (venue.capacity if venue and venue.capacity else int(guests))
    ev = m.Event(code=_next_code(db, day.year), title=title, format_id=fmt.id, venue_id=venue.id if venue else None,
                 author_id=user.id, status="analyzed", planned_date=day, start_time=g("start_time")[:5] or None,
                 ticket_price=price, planned_budget=cost, capacity=capacity,
                 age_rating=g("age_rating") if g("age_rating") in ("0+", "6+", "12+", "16+", "18+") else "16+",
                 description=g("description")[:5000] or None)
    db.add(ev)
    db.flush()
    db.add(m.EventResult(event_id=ev.id, guests_count=int(guests), tickets_sold=sold,
                         revenue=_num(g("revenue"), price * sold), actual_cost=cost))
    added = skipped = 0
    for upload in form.getlist("files"):
        if not getattr(upload, "filename", ""):
            continue
        path = await media.save_image(upload, f"events/{ev.id}")
        if path:
            db.add(m.EventPhoto(event_id=ev.id, file=path, order_no=added, is_cover=added == 0, uploaded_by=user.id))
            added += 1
        else:
            skipped += 1
    audit(db, user.id, "past_event", "event", ev.code)
    db.commit()
    msg = (f"{ev.code} «{ev.title}» добавлено в альбом прошедших тусовок. Фото: {added}. "
           "Осталось поставить оценку гостей: «Оценка» → «Итоговая оценка»")
    if skipped:
        msg += f". Пропущено {skipped}: нужны JPG, PNG или WebP до 8 МБ"
    flash(request, msg, "warn" if skipped else "ok")
    return RedirectResponse(f"/cabinet/evaluation/{ev.id}?tab=review", 303)


@router.get("/projects/new")
def project_new(request: Request, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    if not user.has_role("member", "head"):
        raise HTTPException(403, "Создавать проекты могут участники и руководители Lab")
    return render(request, "cabinet/project_form.html", {"user": user, "ev": None, **_ref(db)})


def _apply_form(ev: m.Event, form) -> list[str]:
    errors = []
    ev.title = (form.get("title") or "").strip()[:200]
    if len(ev.title) < 3:
        errors.append("Название — не короче 3 символов")
    try:
        ev.format_id = int(form.get("format_id"))
    except (TypeError, ValueError):
        errors.append("Выберите формат")
    ev.venue_id = int(form["venue_id"]) if form.get("venue_id") else None
    try:
        ev.planned_date = date.fromisoformat(form["planned_date"]) if form.get("planned_date") else None
    except ValueError:
        errors.append("Дата в формате ГГГГ-ММ-ДД")
    ev.start_time = (form.get("start_time") or "")[:5] or None
    ev.age_rating = form.get("age_rating") or ""
    if ev.age_rating not in ("0+", "6+", "12+", "16+", "18+"):
        errors.append("Укажите возрастную категорию (436-ФЗ)")
    for f in ("ticket_price", "planned_budget"):
        try:
            setattr(ev, f, float((form.get(f) or "0").replace(",", ".")))
        except ValueError:
            errors.append("Цена и бюджет — числа")
    try:
        ev.capacity = int(form["capacity"]) if form.get("capacity") else None
    except ValueError:
        errors.append("Вместимость — целое число")
    ev.target_audience = (form.get("target_audience") or "")[:255] or None
    ev.description = form.get("description") or None
    ev.timepad_event_id = (form.get("timepad_event_id") or "").strip() or None
    ev.timepad_url = (form.get("timepad_url") or "").strip() or None
    return errors


@router.post("/projects/new", dependencies=[Depends(csrf)])
async def project_create(request: Request, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    if not user.has_role("member", "head"):
        raise HTTPException(403)
    form = await request.form()
    ev = m.Event(author_id=user.id, status="draft", code="")
    errors = _apply_form(ev, form)
    if errors:
        return render(request, "cabinet/project_form.html", {"user": user, "ev": ev, "errors": errors, **_ref(db)}, 400)
    ev.code = _next_code(db, (ev.planned_date or date.today()).year)
    db.add(ev)
    audit(db, user.id, "event_create", "event", ev.code)
    db.commit()
    flash(request, f"Проект {ev.code} создан. Соберите сценарий по времени и отправьте на экспертизу")
    return RedirectResponse(f"/cabinet/projects/{ev.id}", 303)


# Оценка вынесена из карточки проекта в отдельный раздел «Оценка» (spec 005): /cabinet/evaluation/{id}
EVAL_TABS = {"expertise": "Экспертиза", "forecast": "Прогноз и решение", "review": "Итоговая оценка"}


@router.get("/projects/{event_id}")
def project_view(event_id: int, request: Request, tab: str = "overview", db: Session = Depends(get_db),
                 user: m.User = Depends(current_user)):
    ev = _event(db, event_id, user)
    if tab == "stations":                      # старые ссылки: «Станции» стали «Сценарием»
        tab = "scenario"
    if tab in EVAL_TABS:                       # старые ссылки на вкладки оценки
        return RedirectResponse(f"/cabinet/evaluation/{ev.id}?tab={tab}", 303)
    return project_page(request, db, user, ev, tab, area="project")


def project_page(request: Request, db: Session, user: m.User, ev: m.Event, tab: str, area: str):
    """Карточка проекта (area=project) и страница его оценки (area=eval) — один шаблон, разные вкладки."""
    summ = service.summary(db, ev)
    fc = db.scalar(select(m.Forecast).where(m.Forecast.event_id == ev.id).order_by(m.Forecast.id.desc()))
    can_see_results = user.has_role("head") or ev.author_id == user.id or (summ["round"] and not summ["round"].is_open)
    experts = db.scalars(select(m.Expert)).all()
    assigned = {ee.expert_id for ee in db.scalars(select(m.EventExpert).where(m.EventExpert.event_id == ev.id))}
    tasks = db.scalars(select(m.Task).where(m.Task.event_id == ev.id).order_by(m.Task.status, m.Task.due_date)).all()
    tickets = db.scalars(select(m.Ticket).where(m.Ticket.event_id == ev.id)).all()
    fbs = db.scalars(select(m.Feedback).where(m.Feedback.event_id == ev.id, m.Feedback.excluded.is_(False))).all()
    st_fb = {}
    for st in ev.rated_stations:
        vals = db.scalars(select(m.FeedbackStation.rating).where(m.FeedbackStation.station_id == st.id)).all()
        st_fb[st.id] = sum(vals) / len(vals) if vals else None
    decisions = db.scalars(select(m.Decision).where(m.Decision.event_id == ev.id).order_by(m.Decision.id.desc())).all()
    users = db.scalars(select(m.User).where(m.User.is_active.is_(True)).order_by(m.User.full_name)).all()
    my_round_open = bool(user.expert and user.expert.id in assigned and summ["round"] and summ["round"].is_open)
    transitions = {k: v for k, v in m.TRANSITIONS.get(ev.status, {}).items()
                   if (v == "head" and user.has_role("head")) or (v == "author" and (ev.author_id == user.id
                                                                                   or user.has_role("head")))}
    rv = review.build(db, ev) if tab == "review" and ev.status in ("held", "analyzed") else None
    return render(request, "cabinet/project.html", {
        "user": user, "ev": ev, "tab": tab, "summ": summ, "fc": fc, "can_see_results": can_see_results, "rv": rv,
        "experts": experts, "assigned": assigned, "tasks": tasks, "tickets": tickets, "feedbacks": fbs,
        "st_fb": st_fb, "decisions": decisions, "users": users, "my_round_open": my_round_open,
        "transitions": transitions, "statuses": m.EVENT_STATUSES, "departments": db.scalars(select(m.Department)).all(),
        "can_edit": user.has_role("head") or (ev.author_id == user.id and ev.status in ("draft", "rework")),
        "can_docs": attachments.can_see_event_docs(db, user, ev), "doc_categories": m.DOC_CATEGORIES,
        "file_accept": attachments.ACCEPT, "area": area, "eval_tabs": EVAL_TABS, **_ref(db)})


@router.post("/projects/{event_id}", dependencies=[Depends(csrf)])
async def project_update(event_id: int, request: Request, db: Session = Depends(get_db),
                         user: m.User = Depends(current_user)):
    ev = _event(db, event_id, user, write=True)
    errors = _apply_form(ev, await request.form())
    if errors:
        db.rollback()
        flash(request, "; ".join(errors), "error")
    else:
        db.commit()
        flash(request, "Изменения сохранены")
    return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=edit", 303)


@router.post("/projects/{event_id}/status", dependencies=[Depends(csrf)])
def project_status(event_id: int, request: Request, to: str = Form(...), comment: str = Form(""),
                   db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    ev = _event(db, event_id, user)
    who = m.TRANSITIONS.get(ev.status, {}).get(to)
    allowed = who == "head" and user.has_role("head") or who == "author" and (ev.author_id == user.id
                                                                              or user.has_role("head"))
    if not allowed:
        raise HTTPException(403, "Такой переход статуса вам недоступен")
    if to == "review" and not ev.rated_stations:
        flash(request, "Добавьте в сценарий хотя бы один блок с отметкой «оценивать» — его будут оценивать эксперты",
              "error")
        return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=scenario", 303)
    if to == "rework" and not comment.strip():
        flash(request, "Напишите, что нужно доработать", "error")
        return RedirectResponse(f"/cabinet/evaluation/{ev.id}?tab=forecast", 303)
    if to in ("approved", "rework", "rejected"):
        db.add(m.Decision(event_id=ev.id, decision=to, comment=comment.strip() or None, decided_by=user.id))
        notify(db, ev.author, f"Решение по проекту «{ev.title}»: {m.EVENT_STATUSES[to][0]}. {comment}".strip(),
               f"/cabinet/projects/{ev.id}")
    if to == "review":
        notify_heads(db, f"Проект «{ev.title}» отправлен на экспертизу", f"/cabinet/projects/{ev.id}")
    old = ev.status
    ev.status = to
    audit(db, user.id, "event_status", ev.code, f"{old} → {to}")
    db.commit()
    flash(request, f"Статус: {ev.status_name}")
    return RedirectResponse(f"/cabinet/projects/{ev.id}", 303)


# ------------------------------------------------------------------ сценарий (spec 002)
SCN = "?tab=scenario"


def _int_in(v, default=0, lo=0, hi=10_000):
    try:
        return max(lo, min(hi, int(float(str(v).replace(",", ".")))))
    except (TypeError, ValueError):
        return default


def _siblings(ev: m.Event, parent_id: int | None) -> list[m.Station]:
    return sorted([b for b in ev.stations if b.parent_id == parent_id], key=lambda b: (b.order_no, b.id))


@router.post("/projects/{event_id}/stations", dependencies=[Depends(csrf)])
async def station_add(event_id: int, request: Request, db: Session = Depends(get_db),
                      user: m.User = Depends(current_user)):
    """Добавить блок сценария, карусель или станцию в карусель (parent_id)."""
    ev = _event(db, event_id, user, write=True)
    f = await request.form()
    title = (f.get("title") or "").strip()[:150]
    if not title:
        flash(request, "Назовите блок", "error")
        return RedirectResponse(f"/cabinet/projects/{ev.id}{SCN}", 303)
    parent = None
    if (f.get("parent_id") or "").isdigit():
        parent = db.get(m.Station, int(f["parent_id"]))
        if not parent or parent.event_id != ev.id or parent.kind != "carousel":
            raise HTTPException(404)
    kind = "station" if parent else (f.get("kind") if f.get("kind") in ("block", "service", "carousel") else "block")
    rated = f.get("rated") == "1" if f.get("rated_field") else scenario.RATED_BY_DEFAULT[kind]
    b = m.Station(event_id=ev.id, parent_id=parent.id if parent else None, kind=kind, title=title,
                  order_no=len(_siblings(ev, parent.id if parent else None)) + 1,
                  duration_min=_int_in(f.get("duration_min"), 15, 1, 600),
                  cost=_int_in(f.get("cost"), 0, 0, 10_000_000),
                  description=(f.get("description") or "").strip() or None, rated=rated and kind != "carousel",
                  responsible_id=int(f["responsible_id"]) if (f.get("responsible_id") or "").isdigit() else None)
    if kind == "carousel":
        b.groups = _int_in(f.get("groups"), 4, 1, 50)
        b.transition_min = _int_in(f.get("transition_min"), 2, 0, 60)
    db.add(b)
    db.commit()
    return RedirectResponse(f"/cabinet/projects/{ev.id}{SCN}#b{b.id}", 303)


@router.post("/projects/{event_id}/stations/{station_id}", dependencies=[Depends(csrf)])
async def station_edit(event_id: int, station_id: int, request: Request, db: Session = Depends(get_db),
                       user: m.User = Depends(current_user)):
    ev = _event(db, event_id, user, write=True)
    st = db.get(m.Station, station_id)
    if not st or st.event_id != ev.id:
        raise HTTPException(404)
    f = await request.form()
    action = f.get("action") or "save"
    sibs = _siblings(ev, st.parent_id)
    idx = sibs.index(st)
    if action == "delete":
        for kid in [b for b in ev.stations if b.parent_id == st.id]:   # станции карусели — вместе с ней
            db.delete(kid)
        db.flush()                                                      # сначала станции, потом сама карусель
        db.delete(st)
        db.flush()
        for i, s in enumerate([s for s in sibs if s.id != st.id], 1):
            s.order_no = i
    elif action in ("up", "down"):
        j = idx - 1 if action == "up" else idx + 1
        if 0 <= j < len(sibs):
            for i, s in enumerate(sibs, 1):
                s.order_no = i
            sibs[idx].order_no, sibs[j].order_no = sibs[j].order_no, sibs[idx].order_no
    else:
        st.title = (f.get("title") or "").strip()[:150] or st.title
        st.duration_min = _int_in(f.get("duration_min"), st.duration_min, 1, 600)
        st.cost = _int_in(f.get("cost"), 0, 0, 10_000_000)
        st.description = (f.get("description") or "").strip() or None
        st.responsible_id = int(f["responsible_id"]) if (f.get("responsible_id") or "").isdigit() else None
        if st.kind in ("block", "service") and f.get("kind") in ("block", "service"):
            st.kind = f.get("kind")
        st.rated = f.get("rated") == "1" and st.kind != "carousel"
        if st.kind == "carousel":
            st.groups = _int_in(f.get("groups"), st.groups or 4, 1, 50)
            st.transition_min = _int_in(f.get("transition_min"), st.transition_min or 0, 0, 60)
    db.commit()
    return RedirectResponse(f"/cabinet/projects/{ev.id}{SCN}", 303)


@router.post("/projects/{event_id}/timing", dependencies=[Depends(csrf)])
async def scenario_timing(event_id: int, request: Request, db: Session = Depends(get_db),
                          user: m.User = Depends(current_user)):
    """Слот площадки (план) и фактическая длительность блоков после мероприятия."""
    ev = _event(db, event_id, user, write=True)
    f = await request.form()
    if "slot_min" in f:
        ev.slot_min = _int_in(f.get("slot_min"), 0, 0, 24 * 60) or None
    for b in ev.stations:
        key = f"fact_{b.id}"
        if key in f and b.parent_id is None:
            b.fact_min = _int_in(f.get(key), 0, 0, 24 * 60) if (f.get(key) or "").strip() else None
    db.commit()
    flash(request, "Тайминг сохранён")
    return RedirectResponse(f"/cabinet/projects/{ev.id}{SCN}", 303)


# ------------------------------------------------------------------ факт и продажи
@router.post("/projects/{event_id}/result", dependencies=[Depends(csrf)])
def result_save(event_id: int, request: Request, guests_count: int = Form(...), tickets_sold: int = Form(...),
                revenue: float = Form(...), actual_cost: float = Form(...),
                db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    """Количественный факт (вкладка «Билеты и факт»). Оценка и завершение — во вкладке «Итоговая оценка»."""
    if not user.has_role("head"):
        raise HTTPException(403, "Факт вносит руководитель")
    ev = _event(db, event_id, user)
    res = ev.result or m.EventResult(event_id=ev.id)
    res.guests_count, res.tickets_sold, res.revenue, res.actual_cost = guests_count, tickets_sold, revenue, actual_cost
    db.add(res)
    db.commit()
    flash(request, "Фактические показатели сохранены. Следующий шаг — «Оценка» → «Итоговая оценка»")
    return RedirectResponse(f"/cabinet/evaluation/{ev.id}?tab=review", 303)


@router.post("/projects/{event_id}/review", dependencies=[Depends(csrf)])
def review_save(event_id: int, request: Request, avg_rating: str = Form(""), lessons: str = Form(""),
                finalize: str = Form(""), db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    """Итоговая оценка: оценка гостей, выводы и завершение разбора полёта (статус «Проанализирован»,
    пересчёт компетентности экспертов — один раз на мероприятие)."""
    if not user.has_role("head"):
        raise HTTPException(403, "Итоговую оценку проводит руководитель")
    ev = _event(db, event_id, user)
    page = f"/cabinet/evaluation/{ev.id}?tab=review"
    if ev.status not in ("held", "analyzed"):
        flash(request, "Итоговая оценка доступна после того, как мероприятие проведено", "error")
        return RedirectResponse(page, 303)
    if not ev.result:
        flash(request, "Сначала внесите гостей, выручку и затраты во вкладке «Билеты и факт»", "error")
        return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=fact", 303)
    rating = _num(avg_rating, None, 1, METHOD["scale_max"]) if avg_rating.strip() else None
    ev.result.avg_rating = rating
    ev.result.lessons = lessons.strip()[:5000] or None
    msg = "Итоговая оценка сохранена"
    if finalize:
        if rating is None:
            db.commit()
            flash(request, "Чтобы завершить разбор полёта, укажите оценку гостей", "error")
            return RedirectResponse(page, 303)
        ev.result.reviewed_at = datetime.now()
        if ev.status == "held":
            ev.status = "analyzed"
        audit(db, user.id, "final_review", "event", ev.code)
        db.commit()
        db.refresh(ev)
        already = db.scalar(select(m.CompetenceHistory).where(m.CompetenceHistory.event_id == ev.id))
        changes = [] if already else service.update_competence(db, ev)
        msg = "Разбор полёта завершён. Мероприятие учтено в прогнозах"
        if changes:
            msg += f", компетентность обновлена у {len(changes)} экспертов"
    else:
        db.commit()
    flash(request, msg)
    return RedirectResponse(page, 303)


# ------------------------------------------------------------------ выгрузка (М-09)
@router.get("/projects/{event_id}/export.{fmt}")
def project_export(event_id: int, fmt: str, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    """Карточка проекта для шаблона Google Диска: JSON (метки + станции) или CSV (метки)."""
    ev = _event(db, event_id, user)
    data = export.event_placeholders(db, ev)
    name = f"{ev.code}"
    if fmt == "json":
        return JSONResponse({"placeholders": data, **export.event_tables(ev)},
                            headers={"Content-Disposition": f'attachment; filename="{name}.json"'})
    if fmt == "csv":
        rows = [{"key": k, "value": "" if v is None else v} for k, v in data.items()]
        return Response(export.to_csv(rows, ["key", "value"]), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    raise HTTPException(404)


@router.get("/registry.csv")
def registry_csv(db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    if not user.has_role("head"):
        raise HTTPException(403)
    return Response(export.to_csv(export.registry(db), export.REGISTRY_COLUMNS), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="energy-lab-registry.csv"'})


@router.post("/projects/{event_id}/tickets/import", dependencies=[Depends(csrf)])
async def tickets_import(event_id: int, request: Request, file: UploadFile, db: Session = Depends(get_db),
                         user: m.User = Depends(current_user)):
    """Загрузка выгрузки заказов Timepad (CSV). Колонки ищутся по названию; повторы не дублируются (LAB-05)."""
    if not user.has_role("head"):
        raise HTTPException(403)
    ev = _event(db, event_id, user)
    data = await file.read()
    try:
        raw = data.decode("utf-8-sig")
    except UnicodeDecodeError:          # Excel в Windows сохраняет CSV в cp1251
        raw = data.decode("cp1251", errors="replace")
    sample = raw[:2000]
    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample else csv.excel
    rows = list(csv.DictReader(io.StringIO(raw), dialect=dialect))

    def pick(row, *names):
        for k, v in row.items():
            if k and any(n in k.lower() for n in names):
                return (v or "").strip()
        return ""
    added = updated = 0
    for row in rows:
        oid = pick(row, "номер", "order", "id заказа", "id")
        if not oid:
            continue
        status_raw = pick(row, "статус", "status").lower()
        status = "refunded" if ("возврат" in status_raw or "refund" in status_raw or "отмен" in status_raw) else "paid"
        price_raw = pick(row, "сумма", "цена", "price", "стоимость").replace(" ", "").replace(",", ".")
        try:
            price = float(price_raw) if price_raw else float(ev.ticket_price or 0)
        except ValueError:
            price = float(ev.ticket_price or 0)
        t = db.scalar(select(m.Ticket).where(m.Ticket.external_order_id == f"{ev.id}:{oid}"))
        if t:
            t.status = status
            updated += 1
        else:
            db.add(m.Ticket(event_id=ev.id, external_order_id=f"{ev.id}:{oid}", price=price, status=status,
                            buyer_name=pick(row, "имя", "фио", "name") or None,
                            email=(pick(row, "e-mail", "email", "почта") or "").lower() or None,
                            purchased_at=datetime.now()))
            added += 1
    db.commit()
    flash(request, f"Импорт продаж: добавлено {added}, обновлено {updated}")
    return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=fact", 303)


# ------------------------------------------------------------------ задачи
def _int(v: str) -> int | None:
    return int(v) if v and v.isdigit() else None


@router.get("/tasks")
def tasks(request: Request, view: str = "board", scope: str = "mine", event: str = "", dept_id: str = "",
          assignee: str = "", flag: str = "", db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    is_head = user.has_role("head")
    if scope == "all" and not is_head:
        scope = "mine"
    if scope == "dept" and not user.expert:
        scope = "mine"
    stmt = select(m.Task)
    if scope == "mine":
        stmt = stmt.where(or_(m.Task.assignee_id == user.id, m.Task.author_id == user.id))
    elif scope == "dept":
        dept_users = select(m.Expert.user_id).where(m.Expert.department_id == user.expert.department_id)
        stmt = stmt.where(or_(m.Task.department_id == user.expert.department_id, m.Task.assignee_id.in_(dept_users)))
    filters = {"event": _int(event), "dept_id": _int(dept_id), "assignee": _int(assignee),
               "flag": flag if flag in ("overdue", "nodue", "archive") else ""}
    if filters["event"]:
        stmt = stmt.where(m.Task.event_id == filters["event"])
    if filters["dept_id"]:
        stmt = stmt.where(m.Task.department_id == filters["dept_id"])
    if filters["assignee"]:
        stmt = stmt.where(m.Task.assignee_id == filters["assignee"])
    if filters["flag"] == "overdue":
        stmt = stmt.where(m.Task.due_date < date.today(), m.Task.status != "done")
    elif filters["flag"] == "nodue":
        stmt = stmt.where(m.Task.due_date.is_(None))
    items = db.scalars(stmt.order_by(m.Task.position, m.Task.id)).all()
    border = datetime.now() - timedelta(days=tasks_board.DONE_VISIBLE_DAYS)
    columns = {k: [] for k in tasks_board.COLUMNS}
    archived = 0
    for t in items:
        if t.status == "done" and filters["flag"] != "archive" and (t.done_at or t.created_at) < border:
            archived += 1
            continue
        columns.setdefault(t.status, []).append(t)
    columns["done"].sort(key=lambda t: t.done_at or t.created_at, reverse=True)
    if view not in ("board", "list"):
        view = "board"
    query = {k: v for k, v in (("scope", scope), ("event", event), ("dept_id", dept_id),
                                ("assignee", assignee), ("flag", flag)) if v}
    def qurl(**kw) -> str:
        """Ссылка на эту же страницу с изменёнными параметрами (пустое значение — убрать параметр)."""
        q = {**query, "view": view, **kw}
        return "/cabinet/tasks?" + urlencode({k: v for k, v in q.items() if v and not (k == "view" and v == "board")})

    ctx = {"user": user, "view": view, "scope": scope, "filters": filters, "columns": columns, "archived": archived,
           "qurl": qurl,
           "tasks": [t for col in columns.values() for t in col], "statuses": m.TASK_STATUSES,
           "priorities": m.TASK_PRIORITIES, "query": query,
           "back": "/cabinet/tasks" + ("?" + str(request.url.query) if request.url.query else ""),
           "events": db.scalars(select(m.Event).where(m.Event.status.notin_(("analyzed", "rejected")))).all(),
           "departments": db.scalars(select(m.Department)).all(),
           "users": db.scalars(select(m.User).where(m.User.is_active.is_(True)).order_by(m.User.full_name)).all()}
    return render(request, "cabinet/tasks.html", ctx)


@router.post("/tasks/{task_id}/move", dependencies=[Depends(csrf)])
def task_move(task_id: int, request: Request, status: str = Form(...), before_id: str = Form(""),
              comment: str = Form(""), expected: str = Form(""), back: str = Form("/cabinet/tasks"),
              db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    """Перенос карточки на доске (ЧТЗ М06-13). JSON для скрипта доски, переадресация — для обычной формы."""
    t = db.get(m.Task, task_id)
    if not t:
        raise HTTPException(404)
    res = tasks_board.move(db, user, t, status, before_id=_int(before_id), comment=comment, expected=expected or None)
    wants_json = "application/json" in request.headers.get("accept", "")
    if not res.ok:
        db.rollback()
        code = 409 if res.conflict else (403 if res.error == tasks_board.NO_RIGHTS else 422)
        if wants_json:
            return JSONResponse({"error": res.error, "status": t.status}, status_code=code)
        if code == 403:
            raise HTTPException(403, res.error)
        flash(request, res.error, "error")
    else:
        db.commit()
        if wants_json:
            return JSONResponse({"ok": True, "status": t.status, "status_name": t.status_name,
                                 "position": t.position, "note": res.note})
        flash(request, res.note or f"«{t.title}» → {t.status_name}")
    return RedirectResponse(back if back.startswith("/cabinet") else "/cabinet/tasks", 303)


@router.post("/tasks", dependencies=[Depends(csrf)])
def task_create(request: Request, title: str = Form(...), assignee_id: str = Form(""), event_id: str = Form(""),
                department_id: str = Form(""), due_date: str = Form(""), description: str = Form(""),
                priority: str = Form("normal"), back: str = Form("/cabinet/tasks"), db: Session = Depends(get_db),
                user: m.User = Depends(current_user)):
    t = m.Task(title=title.strip()[:200], author_id=user.id, description=description or None,
               assignee_id=int(assignee_id) if assignee_id else user.id,
               event_id=int(event_id) if event_id else None,
               department_id=int(department_id) if department_id else None,
               due_date=date.fromisoformat(due_date) if due_date else None,
               position=tasks_board.new_position(db), priority="high" if priority == "high" else "normal")
    db.add(t)
    db.flush()
    db.refresh(t)
    notify(db, t.assignee, f"{user.full_name} поставил(а) вам задачу «{t.title}»"
           + (f", срок {t.due_date:%d.%m}" if t.due_date else "") + (" — срочно" if t.priority == "high" else ""),
           tasks_board.link(t), task=t, actor=user, buttons=tasks_board.buttons(t, tasks_board.WORK_BUTTONS))
    db.commit()
    flash(request, "Задача создана")
    return RedirectResponse(back if back.startswith("/cabinet") else "/cabinet/tasks", 303)


def _task_visible(user: m.User, t: m.Task) -> bool:
    return any(tasks_board.roles_for(user, t)) or bool(
        user.expert and t.department_id and user.expert.department_id == t.department_id)


@router.get("/tasks/{task_id}")
def task_view(task_id: int, request: Request, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    """Карточка задачи: описание, изменение, смена колонки, история (spec 003, ЧТЗ М06-19)."""
    t = db.get(m.Task, task_id)
    if not t or not _task_visible(user, t):
        raise HTTPException(404)
    if notify_mod.mark_read_task(db, user, t.id):     # открыл задачу — её уведомления прочитаны
        db.commit()
    history = db.scalars(select(m.TaskEvent).where(m.TaskEvent.task_id == t.id).order_by(m.TaskEvent.id.desc())).all()
    return render(request, "cabinet/task.html", {
        "user": user, "nav": "tasks", "t": t, "history": history, "can_edit": tasks_board.can_edit(user, t),
        "can_move": any(tasks_board.roles_for(user, t)), "statuses": m.TASK_STATUSES,
        "priorities": m.TASK_PRIORITIES, "history_names": tasks_board.HISTORY_NAMES,
        "back": f"/cabinet/tasks/{t.id}", "file_accept": attachments.ACCEPT,
        "events": db.scalars(select(m.Event).where(m.Event.status.notin_(("analyzed", "rejected")))).all(),
        "users": db.scalars(select(m.User).where(m.User.is_active.is_(True)).order_by(m.User.full_name)).all()})


@router.post("/tasks/{task_id}/edit", dependencies=[Depends(csrf)])
def task_edit(task_id: int, request: Request, title: str = Form(...), description: str = Form(""),
              assignee_id: str = Form(""), event_id: str = Form(""), due_date: str = Form(""),
              priority: str = Form("normal"), db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    t = db.get(m.Task, task_id)
    if not t or not _task_visible(user, t):
        raise HTTPException(404)
    if not tasks_board.can_edit(user, t):
        raise HTTPException(403, "Изменять задачу может автор или руководитель")
    try:
        due = date.fromisoformat(due_date) if due_date else None
    except ValueError:
        due = t.due_date
    changed = tasks_board.update(db, user, t, {
        "title": title.strip()[:200] or t.title, "description": description.strip() or None,
        "assignee_id": _int(assignee_id) or t.assignee_id, "event_id": _int(event_id),
        "due_date": due, "priority": "high" if priority == "high" else "normal"})
    db.commit()
    flash(request, "Задача обновлена, участники получили уведомление" if changed else "Изменений нет")
    return RedirectResponse(f"/cabinet/tasks/{t.id}", 303)


@router.post("/tasks/{task_id}/status", dependencies=[Depends(csrf)])
def task_status(task_id: int, request: Request, status: str = Form(...), comment: str = Form(""),
                back: str = Form("/cabinet/tasks"), db: Session = Depends(get_db),
                user: m.User = Depends(current_user)):
    """Старый адрес смены статуса (формы обзора и проекта) — тот же перенос, что на доске."""
    return task_move(task_id, request, status=status, before_id="", comment=comment, expected="", back=back,
                     db=db, user=user)


# ------------------------------------------------------------------ уведомления на сайте (spec 003)
@router.get("/notifications")
def notifications(request: Request, show: str = "all", db: Session = Depends(get_db),
                  user: m.User = Depends(current_user)):
    stmt = select(m.InboxItem).where(m.InboxItem.user_id == user.id)
    if show == "unread":
        stmt = stmt.where(m.InboxItem.read_at.is_(None))
    items = db.scalars(stmt.order_by(m.InboxItem.id.desc()).limit(200)).all()
    return render(request, "cabinet/notifications.html", {"user": user, "nav": "notifications", "items": items,
                                                          "show": "unread" if show == "unread" else "all",
                                                          "kinds": m.INBOX_KINDS})


@router.get("/notifications/feed")
def notifications_feed(after: int = 0, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    """Для колокольчика: число непрочитанных и новые уведомления после id `after` (опрос раз в 30 секунд)."""
    new = db.scalars(select(m.InboxItem).where(m.InboxItem.user_id == user.id, m.InboxItem.id > after,
                                               m.InboxItem.read_at.is_(None))
                     .order_by(m.InboxItem.id.desc()).limit(5)).all()
    last = db.scalar(select(func.max(m.InboxItem.id)).where(m.InboxItem.user_id == user.id)) or 0
    return JSONResponse({"unread": notify_mod.unread_count(db, user), "last": last,
                         "items": [{"id": n.id, "text": n.text, "kind": n.kind,
                                    "url": f"/cabinet/notifications/{n.id}"} for n in reversed(new)]},
                        headers={"Cache-Control": "no-store"})


@router.get("/notifications/{item_id}")
def notification_open(item_id: int, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    """Переход по уведомлению: отметить прочитанным и открыть то, о чём оно."""
    n = db.get(m.InboxItem, item_id)
    if not n or n.user_id != user.id:
        raise HTTPException(404)
    notify_mod.mark_read(db, user, n.id)
    db.commit()
    return RedirectResponse(n.link if n.link and n.link.startswith("/cabinet") else "/cabinet/notifications", 303)


@router.post("/notifications/read", dependencies=[Depends(csrf)])
def notifications_read(request: Request, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    count = notify_mod.mark_read(db, user)
    db.commit()
    flash(request, f"Прочитано: {count}" if count else "Новых уведомлений нет")
    return RedirectResponse("/cabinet/notifications", 303)


# ------------------------------------------------------------------ обсуждения по отделам
@router.get("/discussions")
def discussions(request: Request, dept: str = "", db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    depts = db.scalars(select(m.Department)).all()
    if not dept and user.expert:
        dept = user.expert.department.code
    stmt = select(m.Discussion).order_by(m.Discussion.status, m.Discussion.id.desc())
    current = next((d for d in depts if d.code == dept), None)
    if current:
        stmt = stmt.where(m.Discussion.department_id == current.id)
    return render(request, "cabinet/discussions.html", {"user": user, "items": db.scalars(stmt).all(),
                                                        "departments": depts, "current": current,
                                                        "events": db.scalars(select(m.Event)).all()})


@router.post("/discussions", dependencies=[Depends(csrf)])
def discussion_create(request: Request, department_id: int = Form(...), title: str = Form(...),
                      text: str = Form(""), event_id: str = Form(""), db: Session = Depends(get_db),
                      user: m.User = Depends(current_user)):
    d = m.Discussion(department_id=department_id, title=title.strip()[:200], author_id=user.id,
                     event_id=int(event_id) if event_id else None)
    db.add(d)
    db.flush()
    if text.strip():
        db.add(m.Message(discussion_id=d.id, author_id=user.id, text=text.strip()))
    for ex in db.scalars(select(m.Expert).where(m.Expert.department_id == department_id)):
        if ex.user_id != user.id:
            notify(db, ex.user, f"Новый вопрос в отделе: {d.title}", f"/cabinet/discussions/{d.id}")
    db.commit()
    return RedirectResponse(f"/cabinet/discussions/{d.id}", 303)


@router.get("/discussions/{disc_id}")
def discussion_view(disc_id: int, request: Request, db: Session = Depends(get_db),
                    user: m.User = Depends(current_user)):
    d = db.get(m.Discussion, disc_id)
    if not d:
        raise HTTPException(404)
    return render(request, "cabinet/discussion.html", {"user": user, "d": d})


@router.post("/discussions/{disc_id}", dependencies=[Depends(csrf)])
def discussion_reply(disc_id: int, request: Request, text: str = Form(""), action: str = Form("reply"),
                     db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    d = db.get(m.Discussion, disc_id)
    if not d:
        raise HTTPException(404)
    if action in ("close", "reopen"):
        if not (d.author_id == user.id or user.has_role("head")):
            raise HTTPException(403)
        d.status = "closed" if action == "close" else "open"
    elif text.strip():
        db.add(m.Message(discussion_id=d.id, author_id=user.id, text=text.strip()[:4000]))
        if d.author_id and d.author_id != user.id:
            notify(db, d.author, f"Ответ в обсуждении «{d.title}»", f"/cabinet/discussions/{d.id}")
    db.commit()
    return RedirectResponse(f"/cabinet/discussions/{d.id}", 303)


# ------------------------------------------------------------------ профиль и привязка бота
@router.get("/profile")
def profile(request: Request, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    code = db.scalar(select(m.LinkCode).where(m.LinkCode.user_id == user.id, m.LinkCode.expires_at > datetime.now()))
    return render(request, "cabinet/profile.html", {"user": user, "code": code})


@router.post("/profile", dependencies=[Depends(csrf)])
def profile_save(request: Request, full_name: str = Form(...), phone: str = Form(""),
                 notify_channel: str = Form("telegram"), db: Session = Depends(get_db),
                 user: m.User = Depends(current_user)):
    user.full_name = full_name.strip()[:150] or user.full_name
    user.phone = phone.strip()[:20] or None
    user.notify_channel = notify_channel if notify_channel in ("telegram", "vk", "none") else "telegram"
    db.commit()
    flash(request, "Профиль сохранён")
    return RedirectResponse("/cabinet/profile", 303)


@router.post("/profile/unlink", dependencies=[Depends(csrf)])
def profile_unlink(request: Request, channel: str = Form(...), db: Session = Depends(get_db),
                   user: m.User = Depends(current_user)):
    if channel == "telegram":
        user.telegram_id = None
    elif channel == "vk":
        user.vk_id = None
    audit(db, user.id, "unlink", channel)
    db.commit()
    flash(request, "Мессенджер отвязан")
    return RedirectResponse("/cabinet/profile", 303)


@router.post("/profile/link-code", dependencies=[Depends(csrf)])
def link_code(request: Request, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    for old in db.scalars(select(m.LinkCode).where(m.LinkCode.user_id == user.id)):
        db.delete(old)
    db.add(m.LinkCode(user_id=user.id, code=f"{secrets.randbelow(10 ** 6):06d}",
                      expires_at=datetime.now() + timedelta(minutes=10)))
    db.commit()
    return RedirectResponse("/cabinet/profile", 303)


# ------------------------------------------------------------------ заявки покупателей на тусовки
@router.get("/requests")
def requests_list(request: Request, status: str = "", db: Session = Depends(get_db),
                  user: m.User = Depends(current_user)):
    if not user.has_role("head"):
        raise HTTPException(403)
    stmt = select(m.PartyRequest).order_by(m.PartyRequest.status != "new", m.PartyRequest.id.desc())
    if status in m.REQUEST_STATUSES:
        stmt = stmt.where(m.PartyRequest.status == status)
    heads = db.scalars(select(m.User).join(m.UserRole).join(m.Role).where(m.Role.code == "head")).all()
    return render(request, "cabinet/requests.html", {"user": user, "items": db.scalars(stmt).all(),
                                                     "statuses": m.REQUEST_STATUSES, "status": status,
                                                     "heads": heads, "nav": "requests"})


@router.post("/requests/{rid}", dependencies=[Depends(csrf)])
def request_update(rid: int, request: Request, status: str = Form(...), note: str = Form(""),
                   manager_id: str = Form(""), db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    if not user.has_role("head"):
        raise HTTPException(403)
    pr = db.get(m.PartyRequest, rid)
    if not pr or status not in m.REQUEST_STATUSES:
        raise HTTPException(404)
    pr.status, pr.note = status, note.strip() or None
    pr.manager_id = int(manager_id) if manager_id.isdigit() else None
    audit(db, user.id, "party_request", f"#{pr.id}", status)
    db.commit()
    flash(request, f"Заявка №{pr.id}: {m.REQUEST_STATUSES[status]}")
    return RedirectResponse("/cabinet/requests", 303)


# ------------------------------------------------------------------ фотоальбом мероприятия
PHOTO_TYPES = {b"\xff\xd8\xff": ".jpg", b"\x89PNG": ".png", b"RIFF": ".webp"}
PHOTO_MAX = 8 * 1024 * 1024


# ------------------------------------------------------------------ документы и вложения (spec 004)
async def _attach(request: Request, db: Session, user: m.User, *, event_id=None, task_id=None,
                  allow_category=True) -> tuple[m.Attachment | None, str | None]:
    """Разобрать форму «файл или ссылка», сохранить вложение. Возвращает (вложение, текст ошибки)."""
    f = await request.form()
    mode = f.get("mode") or ("link" if (f.get("url") or "").strip() else "file")
    title = (f.get("title") or "").strip()[:200]
    category = f.get("category") if allow_category and f.get("category") in m.DOC_CATEGORIES else "other"
    att = m.Attachment(event_id=event_id, task_id=task_id, category=category, uploaded_by=user.id)
    if mode == "link":
        parsed = attachments.parse_link(f.get("url") or "")
        if isinstance(parsed, str):
            return None, parsed
        att.kind, (att.url, att.provider) = "link", parsed
        att.title = title or attachments.title_from_link(att.url, att.provider)
    else:
        sub = f"events/{event_id}" if event_id and not task_id else f"tasks/{task_id}"
        saved = await attachments.save_upload(f.get("file"), sub)
        if isinstance(saved, str):
            return None, saved
        att.kind, (att.file, att.original_name, att.size) = "file", saved
        att.title = title or att.original_name
    db.add(att)
    db.flush()
    return att, None


@router.post("/projects/{event_id}/docs", dependencies=[Depends(csrf)])
async def doc_add(event_id: int, request: Request, db: Session = Depends(get_db),
                  user: m.User = Depends(current_user)):
    ev = _event(db, event_id, user)
    if not attachments.can_see_event_docs(db, user, ev):
        raise HTTPException(403, "Документы проекта видят его участники и руководители")
    att, err = await _attach(request, db, user, event_id=ev.id)
    if err:
        flash(request, err, "error")
    else:
        audit(db, user.id, "doc_add", f"event:{ev.id}", att.title)
        if ev.author_id != user.id:
            notify(db, ev.author, f"{user.full_name} добавил(а) документ в проект «{ev.title}»: {att.title}",
                   f"/cabinet/projects/{ev.id}?tab=docs", actor=user)
        db.commit()
        flash(request, "Документ добавлен" if att.kind == "file" else "Ссылка прикреплена")
    return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=docs", 303)


@router.post("/projects/{event_id}/docs/{aid}/delete", dependencies=[Depends(csrf)])
def doc_delete(event_id: int, aid: int, request: Request, db: Session = Depends(get_db),
               user: m.User = Depends(current_user)):
    ev = _event(db, event_id, user)
    att = db.get(m.Attachment, aid)
    if not att or att.event_id != ev.id or att.task_id:
        raise HTTPException(404)
    if not attachments.can_delete(user, att, ev.author_id):
        raise HTTPException(403, "Удалить может тот, кто добавил, автор проекта или руководитель")
    attachments.remove_file(att)
    db.delete(att)
    audit(db, user.id, "doc_delete", f"event:{ev.id}", att.title)
    db.commit()
    flash(request, "Удалено")
    return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=docs", 303)


@router.post("/tasks/{task_id}/files", dependencies=[Depends(csrf)])
async def task_file_add(task_id: int, request: Request, db: Session = Depends(get_db),
                        user: m.User = Depends(current_user)):
    t = db.get(m.Task, task_id)
    if not t or not _task_visible(user, t):
        raise HTTPException(404)
    if not any(tasks_board.roles_for(user, t)):
        raise HTTPException(403, "Прикреплять файлы может исполнитель, автор или руководитель")
    att, err = await _attach(request, db, user, event_id=t.event_id, task_id=t.id, allow_category=False)
    if err:
        flash(request, err, "error")
    else:
        tasks_board.log(db, t, user, "file", None, att.title[:50])
        what = "файл" if att.kind == "file" else "ссылку"
        for who in {t.assignee, t.author} - {None}:
            notify(db, who, f"{user.full_name} прикрепил(а) {what} к задаче «{t.title}»: {att.title}",
                   tasks_board.link(t), task=t, actor=user)
        db.commit()
        flash(request, "Файл прикреплён" if att.kind == "file" else "Ссылка прикреплена")
    return RedirectResponse(f"/cabinet/tasks/{t.id}#files", 303)


@router.post("/tasks/{task_id}/files/{aid}/delete", dependencies=[Depends(csrf)])
def task_file_delete(task_id: int, aid: int, request: Request, db: Session = Depends(get_db),
                     user: m.User = Depends(current_user)):
    t = db.get(m.Task, task_id)
    att = db.get(m.Attachment, aid)
    if not t or not att or att.task_id != t.id or not _task_visible(user, t):
        raise HTTPException(404)
    if not attachments.can_delete(user, att, t.author_id):
        raise HTTPException(403, "Удалить может тот, кто прикрепил, автор задачи или руководитель")
    attachments.remove_file(att)
    tasks_board.log(db, t, user, "file", att.title[:50], None)
    db.delete(att)
    db.commit()
    flash(request, "Вложение удалено")
    return RedirectResponse(f"/cabinet/tasks/{t.id}#files", 303)


@router.get("/files/{aid}")
def file_download(aid: int, db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    """Скачать документ или вложение — только тем, кому видна задача или документы проекта."""
    att = db.get(m.Attachment, aid)
    if not att:
        raise HTTPException(404)
    if att.task_id:
        t = db.get(m.Task, att.task_id)
        ok = t is not None and _task_visible(user, t)
    else:
        ev = db.get(m.Event, att.event_id) if att.event_id else None
        ok = ev is not None and attachments.can_see_event_docs(db, user, ev)
    if not ok:
        raise HTTPException(404)
    if att.kind == "link":
        return RedirectResponse(att.url, 303)
    path = attachments.full_path(att)
    if not path:
        raise HTTPException(404, "Файл не найден на сервере")
    return FileResponse(path, filename=att.original_name or "file", content_disposition_type="attachment",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.post("/projects/{event_id}/album", dependencies=[Depends(csrf)])
def album_link(event_id: int, request: Request, album_url: str = Form(""), db: Session = Depends(get_db),
               user: m.User = Depends(current_user)):
    """Ссылка на полный фотоальбом на Яндекс Диске или Google Диске (кнопка на странице «Как это было»)."""
    ev = _event(db, event_id, user)
    if not (user.has_role("head") or ev.author_id == user.id):
        raise HTTPException(403)
    if not album_url.strip():
        ev.album_url = None
        flash(request, "Ссылка на альбом убрана")
    else:
        parsed = attachments.parse_link(album_url)
        if isinstance(parsed, str):
            flash(request, parsed, "error")
            return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=photos", 303)
        ev.album_url = parsed[0]
        flash(request, "Ссылка на полный альбом сохранена — она появится на странице мероприятия")
    db.commit()
    return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=photos", 303)


@router.post("/projects/{event_id}/photos", dependencies=[Depends(csrf)])
async def photos_upload(event_id: int, request: Request, db: Session = Depends(get_db),
                        user: m.User = Depends(current_user)):
    ev = _event(db, event_id, user)
    if not (user.has_role("head") or ev.author_id == user.id):
        raise HTTPException(403)
    form = await request.form()
    caption = (form.get("caption") or "").strip()[:200] or None
    folder = os.path.join(settings.media_dir, "events", str(ev.id))
    os.makedirs(folder, exist_ok=True)
    added, skipped = 0, 0
    start = len(ev.photos)
    for f in form.getlist("files"):
        if not hasattr(f, "read"):
            continue
        data = await f.read(PHOTO_MAX + 1)
        ext = next((e for sig, e in PHOTO_TYPES.items() if data.startswith(sig)), None)
        if not ext or len(data) > PHOTO_MAX or (ext == ".webp" and data[8:12] != b"WEBP"):
            skipped += 1
            continue
        name = f"{secrets.token_hex(8)}{ext}"
        with open(os.path.join(folder, name), "wb") as out:
            out.write(data)
        db.add(m.EventPhoto(event_id=ev.id, file=f"events/{ev.id}/{name}", caption=caption,
                            order_no=start + added, is_cover=not ev.photos and added == 0, uploaded_by=user.id))
        added += 1
    db.commit()
    msg = f"Загружено фото: {added}"
    if skipped:
        msg += f". Пропущено {skipped}: нужны JPG, PNG или WebP до 8 МБ"
    flash(request, msg, "warn" if skipped else "ok")
    return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=photos", 303)


@router.post("/projects/{event_id}/photos/{pid}", dependencies=[Depends(csrf)])
def photo_action(event_id: int, pid: int, request: Request, action: str = Form(...), caption: str = Form(""),
                 db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    ev = _event(db, event_id, user)
    if not (user.has_role("head") or ev.author_id == user.id):
        raise HTTPException(403)
    ph = db.get(m.EventPhoto, pid)
    if not ph or ph.event_id != ev.id:
        raise HTTPException(404)
    if action == "cover":
        for p in ev.photos:
            p.is_cover = p.id == ph.id
    elif action == "caption":
        ph.caption = caption.strip()[:200] or None
    elif action == "delete":
        path = os.path.join(settings.media_dir, ph.file)
        if os.path.isfile(path) and ph.file.startswith("events/"):
            os.remove(path)
        db.delete(ph)
    db.commit()
    return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=photos", 303)
