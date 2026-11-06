"""Личный кабинет (ЧТЗ-4): обзор, проекты, станции, статусы, факт, импорт продаж, задачи, обсуждения, профиль."""
import csv
import io
import os
import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import export
from app import models as m
from app.config import settings
from app.db import get_db
from app.deps import csrf, current_user, flash, render
from app.expertise import service
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
def projects(request: Request, q: str = "", status: str = "", db: Session = Depends(get_db),
             user: m.User = Depends(current_user)):
    stmt = select(m.Event).order_by(m.Event.planned_date.desc().nulls_last(), m.Event.id.desc())
    if not user.has_role("head"):
        stmt = stmt.where(or_(m.Event.author_id == user.id, m.Event.status.in_(("on_sale", "held", "analyzed"))))
    if q:
        stmt = stmt.where(or_(m.Event.title.ilike(f"%{q}%"), m.Event.code.ilike(f"%{q}%")))
    if status:
        stmt = stmt.where(m.Event.status == status)
    events = db.scalars(stmt).all()
    latest = {}
    for ev in events:
        latest[ev.id] = db.scalar(select(m.Forecast).where(m.Forecast.event_id == ev.id).order_by(m.Forecast.id.desc()))
    return render(request, "cabinet/projects.html", {"user": user, "events": events, "latest": latest, "q": q,
                                                     "status": status, "statuses": m.EVENT_STATUSES})


def _ref(db: Session):
    return {"formats": db.scalars(select(m.EventFormat).order_by(m.EventFormat.code)).all(),
            "venues": db.scalars(select(m.Venue).order_by(m.Venue.name)).all(),
            "ages": ["0+", "6+", "12+", "16+", "18+"]}


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
    flash(request, f"Проект {ev.code} создан. Добавьте станции и отправьте на экспертизу")
    return RedirectResponse(f"/cabinet/projects/{ev.id}", 303)


@router.get("/projects/{event_id}")
def project_view(event_id: int, request: Request, tab: str = "overview", db: Session = Depends(get_db),
                 user: m.User = Depends(current_user)):
    ev = _event(db, event_id, user)
    summ = service.summary(db, ev)
    fc = db.scalar(select(m.Forecast).where(m.Forecast.event_id == ev.id).order_by(m.Forecast.id.desc()))
    can_see_results = user.has_role("head") or ev.author_id == user.id or (summ["round"] and not summ["round"].is_open)
    experts = db.scalars(select(m.Expert)).all()
    assigned = {ee.expert_id for ee in db.scalars(select(m.EventExpert).where(m.EventExpert.event_id == ev.id))}
    tasks = db.scalars(select(m.Task).where(m.Task.event_id == ev.id).order_by(m.Task.status, m.Task.due_date)).all()
    tickets = db.scalars(select(m.Ticket).where(m.Ticket.event_id == ev.id)).all()
    fbs = db.scalars(select(m.Feedback).where(m.Feedback.event_id == ev.id, m.Feedback.excluded.is_(False))).all()
    st_fb = {}
    for st in ev.stations:
        vals = db.scalars(select(m.FeedbackStation.rating).where(m.FeedbackStation.station_id == st.id)).all()
        st_fb[st.id] = sum(vals) / len(vals) if vals else None
    decisions = db.scalars(select(m.Decision).where(m.Decision.event_id == ev.id).order_by(m.Decision.id.desc())).all()
    users = db.scalars(select(m.User).where(m.User.is_active.is_(True)).order_by(m.User.full_name)).all()
    my_round_open = bool(user.expert and user.expert.id in assigned and summ["round"] and summ["round"].is_open)
    transitions = {k: v for k, v in m.TRANSITIONS.get(ev.status, {}).items()
                   if (v == "head" and user.has_role("head")) or (v == "author" and (ev.author_id == user.id
                                                                                   or user.has_role("head")))}
    return render(request, "cabinet/project.html", {
        "user": user, "ev": ev, "tab": tab, "summ": summ, "fc": fc, "can_see_results": can_see_results,
        "experts": experts, "assigned": assigned, "tasks": tasks, "tickets": tickets, "feedbacks": fbs,
        "st_fb": st_fb, "decisions": decisions, "users": users, "my_round_open": my_round_open,
        "transitions": transitions, "statuses": m.EVENT_STATUSES, "departments": db.scalars(select(m.Department)).all(),
        "can_edit": user.has_role("head") or (ev.author_id == user.id and ev.status in ("draft", "rework")),
        **_ref(db)})


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
    if to == "review" and not ev.stations:
        flash(request, "Добавьте хотя бы одну станцию перед отправкой на экспертизу", "error")
        return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=stations", 303)
    if to == "rework" and not comment.strip():
        flash(request, "Напишите, что нужно доработать", "error")
        return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=forecast", 303)
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


# ------------------------------------------------------------------ станции
@router.post("/projects/{event_id}/stations", dependencies=[Depends(csrf)])
def station_add(event_id: int, request: Request, title: str = Form(...), duration_min: int = Form(15),
                cost: float = Form(0), description: str = Form(""), responsible_id: str = Form(""),
                db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    ev = _event(db, event_id, user, write=True)
    db.add(m.Station(event_id=ev.id, order_no=len(ev.stations) + 1, title=title.strip()[:150],
                     duration_min=max(1, duration_min), cost=max(0, cost), description=description or None,
                     responsible_id=int(responsible_id) if responsible_id else None))
    db.commit()
    return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=stations", 303)


@router.post("/projects/{event_id}/stations/{station_id}", dependencies=[Depends(csrf)])
def station_edit(event_id: int, station_id: int, request: Request, action: str = Form("save"),
                 title: str = Form(""), duration_min: int = Form(15), cost: float = Form(0),
                 description: str = Form(""), responsible_id: str = Form(""),
                 db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    ev = _event(db, event_id, user, write=True)
    st = db.get(m.Station, station_id)
    if not st or st.event_id != ev.id:
        raise HTTPException(404)
    sts = list(ev.stations)
    idx = sts.index(st)
    if action == "delete":
        db.delete(st)
        db.flush()
        for i, s in enumerate([s for s in sts if s.id != st.id], 1):
            s.order_no = i
    elif action in ("up", "down"):
        j = idx - 1 if action == "up" else idx + 1
        if 0 <= j < len(sts):
            sts[idx].order_no, sts[j].order_no = sts[j].order_no, sts[idx].order_no
    else:
        st.title = title.strip()[:150] or st.title
        st.duration_min, st.cost = max(1, duration_min), max(0, cost)
        st.description = description or None
        st.responsible_id = int(responsible_id) if responsible_id else None
    db.commit()
    return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=stations", 303)


# ------------------------------------------------------------------ факт и продажи
@router.post("/projects/{event_id}/result", dependencies=[Depends(csrf)])
def result_save(event_id: int, request: Request, guests_count: int = Form(...), tickets_sold: int = Form(...),
                revenue: float = Form(...), actual_cost: float = Form(...), avg_rating: str = Form(""),
                finalize: str = Form(""), db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    if not user.has_role("head"):
        raise HTTPException(403, "Факт вносит руководитель")
    ev = _event(db, event_id, user)
    res = ev.result or m.EventResult(event_id=ev.id)
    res.guests_count, res.tickets_sold, res.revenue, res.actual_cost = guests_count, tickets_sold, revenue, actual_cost
    res.avg_rating = float(avg_rating.replace(",", ".")) if avg_rating.strip() else None
    db.add(res)
    db.commit()
    msg = "Фактические показатели сохранены"
    if finalize and ev.status == "held":
        ev.status = "analyzed"
        db.commit()
        db.refresh(ev)
        changes = service.update_competence(db, ev)
        msg += f". Разбор полёта завершён, компетентность обновлена у {len(changes)} экспертов"
    flash(request, msg)
    return RedirectResponse(f"/cabinet/projects/{ev.id}?tab=fact", 303)


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
@router.get("/tasks")
def tasks(request: Request, scope: str = "mine", db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    stmt = select(m.Task).order_by(m.Task.status, m.Task.due_date.is_(None), m.Task.due_date)
    if scope == "mine" or not user.has_role("head"):
        stmt = stmt.where(or_(m.Task.assignee_id == user.id, m.Task.author_id == user.id))
    items = db.scalars(stmt).all()
    ctx = {"user": user, "tasks": items, "scope": scope, "statuses": m.TASK_STATUSES,
           "events": db.scalars(select(m.Event).where(m.Event.status.notin_(("analyzed", "rejected")))).all(),
           "departments": db.scalars(select(m.Department)).all(),
           "users": db.scalars(select(m.User).where(m.User.is_active.is_(True)).order_by(m.User.full_name)).all()}
    return render(request, "cabinet/tasks.html", ctx)


@router.post("/tasks", dependencies=[Depends(csrf)])
def task_create(request: Request, title: str = Form(...), assignee_id: str = Form(""), event_id: str = Form(""),
                department_id: str = Form(""), due_date: str = Form(""), description: str = Form(""),
                back: str = Form("/cabinet/tasks"), db: Session = Depends(get_db),
                user: m.User = Depends(current_user)):
    t = m.Task(title=title.strip()[:200], author_id=user.id, description=description or None,
               assignee_id=int(assignee_id) if assignee_id else user.id,
               event_id=int(event_id) if event_id else None,
               department_id=int(department_id) if department_id else None,
               due_date=date.fromisoformat(due_date) if due_date else None)
    db.add(t)
    db.flush()
    if t.assignee_id != user.id:
        notify(db, db.get(m.User, t.assignee_id), f"Новая задача: {t.title}"
               + (f" (до {t.due_date:%d.%m})" if t.due_date else ""), "/cabinet/tasks")
    db.commit()
    flash(request, "Задача создана")
    return RedirectResponse(back if back.startswith("/cabinet") else "/cabinet/tasks", 303)


@router.post("/tasks/{task_id}/status", dependencies=[Depends(csrf)])
def task_status(task_id: int, request: Request, status: str = Form(...), back: str = Form("/cabinet/tasks"),
                db: Session = Depends(get_db), user: m.User = Depends(current_user)):
    t = db.get(m.Task, task_id)
    if not t or status not in m.TASK_STATUSES:
        raise HTTPException(404)
    if not (t.assignee_id == user.id or t.author_id == user.id or user.has_role("head")):
        raise HTTPException(403)
    t.status = status
    db.commit()
    return RedirectResponse(back if back.startswith("/cabinet") else "/cabinet/tasks", 303)


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
