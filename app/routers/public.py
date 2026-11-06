"""Публичный сайт Energy Lab (ЧТЗ-2): главная, афиша, карточка мероприятия, анкета гостя, доска вопросов."""
import hashlib
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app import pricing, site
from app.db import get_db
from app.deps import csrf, current_user_optional, flash, render
from app.notify import notify_heads

router = APIRouter()
PUBLIC_STATUSES = ("on_sale",)


OCCASIONS = ["День рождения", "Выпускной", "Корпоратив", "Студенческая тусовка", "Детский праздник", "Другое"]
AGE_GROUPS = ["6–11", "12–15", "16–17", "18+", "смешанная"]


def _stats(db: Session) -> dict:
    done = db.scalars(select(m.Event).where(m.Event.status == "analyzed")).all()
    results = [e.result for e in done if e.result]
    rated = [r.avg_rating for r in results if r.avg_rating]
    return {"launches": len(done), "guests": sum(r.guests_count for r in results),
            "rating": sum(rated) / len(rated) if rated else None}


@router.get("/")
def home(request: Request, db: Session = Depends(get_db), user=Depends(current_user_optional)):
    upcoming = db.scalars(select(m.Event).where(m.Event.status.in_(PUBLIC_STATUSES))
                          .order_by(m.Event.planned_date)).all()
    # «Какие события будут»: в продаже + утверждённые, продажи которых ещё не открыты
    soon = db.scalars(select(m.Event).where(m.Event.status.in_(("approved", "on_sale")),
                                            m.Event.planned_date >= date.today())
                      .order_by(m.Event.planned_date).limit(12)).all()
    months: dict[str, list] = {}
    for ev in soon:
        months.setdefault(ev.planned_date.strftime("%Y-%m"), []).append(ev)
    past = db.scalars(select(m.Event).where(m.Event.status.in_(("held", "analyzed")))
                      .order_by(m.Event.planned_date.desc()).limit(6)).all()
    formats = db.scalars(select(m.EventFormat).where(~m.EventFormat.code.endswith("0"))).all()
    depts = db.scalars(select(m.Department).order_by(m.Department.weight.desc(), m.Department.id)).all()
    crew = dict(db.execute(select(m.Expert.department_id, func.count()).join(m.User)
                           .where(m.User.is_active.is_(True)).group_by(m.Expert.department_id)).all())
    cfg = site.pricing(db)
    rates = pricing.per_guest_rates(db, cfg)
    groups = sorted({f.group_name for f in formats})
    team = db.scalars(select(m.TeamMember).where(m.TeamMember.is_public.is_(True), m.TeamMember.consent.is_(True))
                      .order_by(m.TeamMember.order_no, m.TeamMember.id)).all()
    return render(request, "public/home.html", {
        "user": user, "next_launch": upcoming[0] if upcoming else None, "upcoming": upcoming[:6],
        "months": months, "past": past, "formats": formats, "groups": groups, "departments": depts, "crew": crew,
        "stats": _stats(db), "rates": rates, "pricing": cfg, "occasions": OCCASIONS, "age_groups": AGE_GROUPS,
        "sample": pricing.estimate(rates, "Квестовые" if "Квестовые" in groups else (groups or [""])[0], 20,
                                   options=list(cfg["options"])[:1], cfg=cfg),
        "team": team, "texts": site.texts(db),
        "rf": request.session.pop("request_form", None) or {}})


@router.post("/request", dependencies=[Depends(csrf)])
async def party_request(request: Request, db: Session = Depends(get_db)):
    """Заявка на создание тусовки: сохраняется в БД в РФ, руководители получают уведомление без контактов."""
    form = await request.form()
    g = lambda k: (form.get(k) or "").strip()  # noqa: E731
    errors = []
    name, contact, text = g("name")[:150], g("contact")[:150], g("message")[:2000]
    try:
        guests = int(g("guests") or 0)
    except ValueError:
        guests = 0
    if not name:
        errors.append("Как к вам обращаться?")
    if len(contact) < 5:
        errors.append("Оставьте телефон, e-mail или ник в мессенджере, чтобы мы связались с вами")
    if not 1 <= guests <= 1000:
        errors.append("Сколько будет гостей? От 1 до 1000")
    if g("consent") != "1":
        errors.append("Нужно согласие на обработку данных — без него мы не можем вам перезвонить")
    if g("website"):                       # ловушка для ботов: скрытое поле должно быть пустым
        return RedirectResponse("/#request", 303)
    if errors:
        flash(request, ". ".join(errors), "error")
        request.session["request_form"] = {k: g(k) for k in ("name", "contact", "occasion", "format_id", "wish_date",
                                                              "guests", "age_group", "budget", "message")}
        return RedirectResponse("/#request", 303)
    fmt = db.get(m.EventFormat, int(g("format_id"))) if g("format_id").isdigit() else None
    try:
        wish = date.fromisoformat(g("wish_date")) if g("wish_date") else None
    except ValueError:
        wish = None
    try:
        budget = float(g("budget").replace(" ", "").replace(",", ".")) if g("budget") else None
    except ValueError:
        budget = None
    cfg = site.pricing(db)
    est = pricing.estimate(pricing.per_guest_rates(db, cfg), fmt.group_name if fmt else "Развлекательные", guests,
                           cfg=cfg)
    pr = m.PartyRequest(name=name, contact=contact, occasion=(g("occasion") or "Другое")[:60],
                        format_id=fmt.id if fmt else None, wish_date=wish, guests=guests,
                        age_group=g("age_group")[:20] or None, budget=budget, estimate=est["total"],
                        message=text or None)
    db.add(pr)
    db.flush()
    notify_heads(db, f"Новая заявка на тусовку №{pr.id}: {pr.occasion}, {guests} гостей", "/cabinet/requests")
    db.commit()
    request.session.pop("request_form", None)
    flash(request, f"Заявка №{pr.id} принята. Продюсер свяжется с вами в течение двух рабочих дней")
    return RedirectResponse("/#request", 303)


@router.get("/archive")
def archive(request: Request, db: Session = Depends(get_db), user=Depends(current_user_optional)):
    past = db.scalars(select(m.Event).where(m.Event.status.in_(("held", "analyzed")))
                      .order_by(m.Event.planned_date.desc())).all()
    return render(request, "public/archive.html", {"user": user, "past": past, "stats": _stats(db)})


@router.get("/afisha")
def afisha(request: Request, group: str | None = None, db: Session = Depends(get_db),
           user=Depends(current_user_optional)):
    q = select(m.Event).where(m.Event.status.in_(PUBLIC_STATUSES)).order_by(m.Event.planned_date)
    events = db.scalars(q).all()
    groups = sorted({e.format.group_name for e in events})
    if group:
        events = [e for e in events if e.format.group_name == group]
    return render(request, "public/afisha.html", {"user": user, "events": events, "groups": groups, "group": group})


def _public_event(db: Session, code: str, allow_past=False) -> m.Event:
    ev = db.scalar(select(m.Event).where(m.Event.code == code))
    allowed = PUBLIC_STATUSES + (("held", "analyzed") if allow_past else ())
    if not ev or ev.status not in allowed:
        raise HTTPException(404, "Мероприятие не найдено")
    return ev


@router.get("/e/{code}")
def event_page(code: str, request: Request, db: Session = Depends(get_db), user=Depends(current_user_optional)):
    ev = _public_event(db, code, allow_past=True)
    return render(request, "public/event.html", {"user": user, "ev": ev})


def _feedback_open(ev: m.Event) -> bool:
    return bool(ev.planned_date) and ev.planned_date <= date.today() <= ev.planned_date + timedelta(days=7)


@router.get("/e/{code}/feedback")
def feedback_form(code: str, request: Request, db: Session = Depends(get_db)):
    ev = _public_event(db, code, allow_past=True)
    return render(request, "public/feedback.html", {"ev": ev, "is_open": _feedback_open(ev) or ev.status == "on_sale"})


@router.post("/e/{code}/feedback", dependencies=[Depends(csrf)])
async def feedback_send(code: str, request: Request, db: Session = Depends(get_db)):
    ev = _public_event(db, code, allow_past=True)
    form = await request.form()
    try:
        rating = int(form.get("rating", 0))
    except ValueError:
        rating = 0
    if not 1 <= rating <= 5:
        flash(request, "Поставьте оценку мероприятию от 1 до 5", "error")
        return RedirectResponse(f"/e/{code}/feedback", 303)
    ip = request.client.host if request.client else ""
    client_hash = hashlib.sha256(f"{ev.id}:{ip}:{request.headers.get('user-agent', '')}".encode()).hexdigest()
    if request.cookies.get(f"fb_{ev.id}") or db.scalar(select(m.Feedback).where(m.Feedback.client_hash == client_hash)):
        flash(request, "С этого устройства анкета уже отправлена. Спасибо!", "error")
        return RedirectResponse(f"/e/{code}", 303)
    email = (form.get("email") or "").strip().lower()
    ticket = db.scalar(select(m.Ticket).where(m.Ticket.event_id == ev.id, m.Ticket.email == email)) if email else None
    if ticket and db.scalar(select(m.Feedback).where(m.Feedback.ticket_id == ticket.id)):
        flash(request, "По этому билету анкета уже есть", "error")
        return RedirectResponse(f"/e/{code}", 303)
    nps = form.get("nps")
    fb = m.Feedback(event_id=ev.id, ticket_id=ticket.id if ticket else None, rating=rating,
                    nps=int(nps) if nps not in (None, "") else None, comment=(form.get("comment") or "")[:2000],
                    is_anonymous=ticket is None, client_hash=client_hash)
    db.add(fb)
    db.flush()
    for st in ev.stations:
        v = form.get(f"st_{st.id}")
        if v and v.isdigit() and 1 <= int(v) <= 5:
            db.add(m.FeedbackStation(feedback_id=fb.id, station_id=st.id, rating=int(v)))
    db.commit()
    resp = RedirectResponse(f"/e/{code}?thanks=1", 303)
    resp.set_cookie(f"fb_{ev.id}", "1", max_age=60 * 60 * 24 * 30, httponly=True, samesite="lax")
    return resp


@router.get("/board")
def board(request: Request, db: Session = Depends(get_db), user=Depends(current_user_optional)):
    qs = db.scalars(select(m.Question).where(m.Question.status.in_(("approved", "answered")))
                    .order_by(m.Question.id.desc()).limit(100)).all()
    return render(request, "public/board.html", {"user": user, "questions": qs})


@router.post("/board", dependencies=[Depends(csrf)])
def board_ask(request: Request, text: str = Form(...), name: str = Form(""), category: str = Form("Другое"),
              back: str = Form("/board"), db: Session = Depends(get_db)):
    text = text.strip()
    if not 3 <= len(text) <= 1000:
        flash(request, "Вопрос должен быть от 3 до 1000 символов", "error")
    else:
        db.add(m.Question(text=text, author_name=name.strip()[:150] or None, category=category[:30], channel="web"))
        db.commit()
        flash(request, "Сигнал принят. Команда прочитает его и ответит на доске"
              if category == "Идея мероприятия" else "Вопрос отправлен на проверку. Ответ появится на доске")
    return RedirectResponse(back if back in ("/board", "/#idea") else "/board", 303)


@router.get("/privacy")
def privacy(request: Request, user=Depends(current_user_optional)):
    return render(request, "public/privacy.html", {"user": user})
