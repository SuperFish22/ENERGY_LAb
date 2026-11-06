"""Администрирование (ЧТЗ-4, CAB-03, CAB-09 – CAB-11, CAB-13) и модерация вопросов доски."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import media, site
from app import models as m
from app.config import settings
from app.db import get_db
from app.deps import csrf, flash, render, require
from app.expertise.scoring import normalize
from app.routers.auth import make_invite
from app.security import audit

router = APIRouter(prefix="/cabinet/admin")


@router.get("/users")
def users(request: Request, db: Session = Depends(get_db), user: m.User = Depends(require("head"))):
    return render(request, "cabinet/admin_users.html", {
        "user": user, "users": db.scalars(select(m.User).order_by(m.User.full_name)).all(),
        "roles": db.scalars(select(m.Role)).all(), "departments": db.scalars(select(m.Department)).all(),
        "invite": request.session.pop("invite", None)})


@router.post("/invite", dependencies=[Depends(csrf)])
async def invite(request: Request, db: Session = Depends(get_db), user: m.User = Depends(require("head"))):
    form = await request.form()
    email = (form.get("email") or "").strip().lower()
    roles = form.getlist("role") or ["member"]
    if "head" in roles and not user.has_role("head"):
        raise HTTPException(403)
    token = make_invite(email, roles, form.get("dept") or None)
    request.session["invite"] = f"{settings.base_url}/invite/{token}"
    audit(db, user.id, "invite", "user", email)
    db.commit()
    return RedirectResponse("/cabinet/admin/users", 303)


@router.post("/users/{uid}", dependencies=[Depends(csrf)])
async def user_update(uid: int, request: Request, db: Session = Depends(get_db),
                      user: m.User = Depends(require("head"))):
    target = db.get(m.User, uid)
    if not target:
        raise HTTPException(404)
    form = await request.form()
    codes = set(form.getlist("role"))
    heads = db.scalars(select(m.User).join(m.UserRole).join(m.Role).where(m.Role.code == "head")).all()
    if target.has_role("head") and "head" not in codes and len(heads) == 1:
        flash(request, "Нельзя снять роль с последнего руководителя", "error")
        return RedirectResponse("/cabinet/admin/users", 303)
    target.roles = list(db.scalars(select(m.Role).where(m.Role.code.in_(codes))))
    target.is_active = form.get("is_active") == "1"
    dept = form.get("dept")
    if dept:
        d = db.scalar(select(m.Department).where(m.Department.code == dept))
        comp = float((form.get("competence") or "0.7").replace(",", "."))
        comp = max(0.5, min(1.0, comp))
        if target.expert:
            if abs(target.expert.competence - comp) > 1e-9:
                db.add(m.CompetenceHistory(expert_id=target.expert.id, old_value=target.expert.competence,
                                           new_value=comp, reason=form.get("reason") or "Ручная правка руководителем"))
            target.expert.department_id, target.expert.competence = d.id, comp
        else:
            db.add(m.Expert(user_id=target.id, department_id=d.id, competence=comp))
    audit(db, user.id, "user_update", "user", f"{target.email}: {sorted(codes)}")
    db.commit()
    flash(request, f"Сохранено: {target.full_name}")
    return RedirectResponse("/cabinet/admin/users", 303)


@router.get("/criteria")
def criteria(request: Request, db: Session = Depends(get_db), user: m.User = Depends(require("head"))):
    depts = db.scalars(select(m.Department)).all()
    venues = db.scalars(select(m.Venue)).all()
    return render(request, "cabinet/admin_criteria.html", {"user": user, "departments": depts, "venues": venues})


@router.post("/criteria", dependencies=[Depends(csrf)])
async def criteria_save(request: Request, db: Session = Depends(get_db), user: m.User = Depends(require("head"))):
    form = await request.form()
    depts = db.scalars(select(m.Department)).all()
    alpha = normalize({d.id: float((form.get(f"dept_{d.id}") or d.weight).__str__().replace(",", ".")) for d in depts})
    for d in depts:
        d.weight = round(alpha[d.id], 4)
        w = normalize({c.id: float(str(form.get(f"crit_{c.id}") or c.weight).replace(",", ".")) for c in d.criteria})
        for c in d.criteria:
            c.weight = round(w[c.id], 4)
            c.name = (form.get(f"name_{c.id}") or c.name)[:150]
    audit(db, user.id, "criteria_update", "criteria")
    db.commit()
    flash(request, "Веса нормированы и сохранены. Новые веса применятся при следующем расчёте прогноза")
    return RedirectResponse("/cabinet/admin/criteria", 303)


@router.post("/venues", dependencies=[Depends(csrf)])
def venue_add(request: Request, name: str = Form(...), address: str = Form(""), capacity: int = Form(0),
              db: Session = Depends(get_db), user: m.User = Depends(require("head"))):
    db.add(m.Venue(name=name.strip()[:150], address=address or None, capacity=capacity or None))
    db.commit()
    return RedirectResponse("/cabinet/admin/criteria", 303)


@router.get("/questions")
def questions(request: Request, db: Session = Depends(get_db), user: m.User = Depends(require("head"))):
    qs = db.scalars(select(m.Question).order_by(m.Question.status != "sos", m.Question.status != "pending",
                                                m.Question.id.desc()).limit(200)).all()
    return render(request, "cabinet/admin_questions.html", {"user": user, "questions": qs})


@router.post("/questions/{qid}", dependencies=[Depends(csrf)])
def question_moderate(qid: int, request: Request, action: str = Form(...), answer: str = Form(""),
                      db: Session = Depends(get_db), user: m.User = Depends(require("head"))):
    q = db.get(m.Question, qid)
    if not q:
        raise HTTPException(404)
    if action == "approve":
        q.status = "approved"
    elif action == "answer" and answer.strip():
        q.status, q.answer = "answered", answer.strip()
    elif action == "reject":
        q.status = "rejected"
    q.moderated_by = user.id
    if q.channel in ("telegram", "vk") and q.channel_user_id and q.status in ("approved", "answered", "rejected"):
        text = {"approved": "Ваш вопрос опубликован на доске.", "rejected": "Ваш вопрос отклонён модератором.",
                "answered": f"Ответ на ваш вопрос: {q.answer}"}[q.status]
        db.add(m.Notification(channel=q.channel, chat_id=q.channel_user_id, text=text))
    db.commit()
    return RedirectResponse("/cabinet/admin/questions", 303)


# ------------------------------------------------------------------ настройки главной страницы
@router.get("/site")
def site_settings(request: Request, db: Session = Depends(get_db), user: m.User = Depends(require("head"))):
    team = db.scalars(select(m.TeamMember).order_by(m.TeamMember.order_no, m.TeamMember.id)).all()
    return render(request, "cabinet/admin_site.html", {
        "user": user, "team": team, "departments": db.scalars(select(m.Department)).all(),
        "users": db.scalars(select(m.User).where(m.User.is_active.is_(True)).order_by(m.User.full_name)).all(),
        "texts": site.texts(db), "labels": site.TEXT_LABELS, "pricing": site.pricing(db), "nav": "site"})


def _member_fields(member: m.TeamMember, form) -> None:
    member.full_name = (form.get("full_name") or member.full_name or "").strip()[:150]
    member.role = (form.get("role") or "").strip()[:120] or "Команда Energy Lab"
    member.bio = (form.get("bio") or "").strip()[:400] or None
    dept = form.get("department_id") or ""
    member.department_id = int(dept) if dept.isdigit() else None
    uid = form.get("user_id") or ""
    member.user_id = int(uid) if uid.isdigit() else None
    member.is_public = form.get("is_public") == "1"
    member.consent = form.get("consent") == "1"


@router.post("/site/team", dependencies=[Depends(csrf)])
async def team_add(request: Request, db: Session = Depends(get_db), user: m.User = Depends(require("head"))):
    form = await request.form()
    if not (form.get("full_name") or "").strip():
        flash(request, "Укажите имя", "error")
        return RedirectResponse("/cabinet/admin/site#team", 303)
    last = db.scalar(select(func.max(m.TeamMember.order_no))) or 0
    member = m.TeamMember(order_no=last + 1)
    _member_fields(member, form)
    member.photo = await media.save_image(form.get("photo") if form.get("photo") else None, "team")
    if form.get("photo") and getattr(form.get("photo"), "filename", "") and not member.photo:
        flash(request, "Фото не сохранено: нужен JPG, PNG или WebP до 8 МБ", "warn")
    db.add(member)
    audit(db, user.id, "team_add", "team", member.full_name)
    db.commit()
    return RedirectResponse("/cabinet/admin/site#team", 303)


@router.post("/site/team/{mid}", dependencies=[Depends(csrf)])
async def team_update(mid: int, request: Request, db: Session = Depends(get_db),
                      user: m.User = Depends(require("head"))):
    member = db.get(m.TeamMember, mid)
    if not member:
        raise HTTPException(404)
    form = await request.form()
    action = form.get("action") or "save"
    team = db.scalars(select(m.TeamMember).order_by(m.TeamMember.order_no, m.TeamMember.id)).all()
    if action in ("up", "down"):
        i = team.index(member)
        j = i - 1 if action == "up" else i + 1
        if 0 <= j < len(team):
            team[i], team[j] = team[j], team[i]
        for k, t in enumerate(team):
            t.order_no = k
    elif action == "delete":
        media.remove(member.photo)
        db.delete(member)
    elif action == "drop_photo":
        media.remove(member.photo)
        member.photo = None
    else:
        _member_fields(member, form)
        upload = form.get("photo")
        if upload is not None and getattr(upload, "filename", ""):
            path = await media.save_image(upload, "team")
            if path:
                media.remove(member.photo)
                member.photo = path
            else:
                flash(request, "Фото не сохранено: нужен JPG, PNG или WebP до 8 МБ", "warn")
    audit(db, user.id, f"team_{action}", "team", member.full_name)
    db.commit()
    return RedirectResponse("/cabinet/admin/site#team", 303)


@router.post("/site/texts", dependencies=[Depends(csrf)])
async def texts_save(request: Request, db: Session = Depends(get_db), user: m.User = Depends(require("head"))):
    form = await request.form()
    site.save_texts(db, {k: form.get(k) or "" for k in site.TEXTS_DEFAULT})
    audit(db, user.id, "site_texts", "site")
    db.commit()
    flash(request, "Тексты главной сохранены")
    return RedirectResponse("/cabinet/admin/site#texts", 303)


def _num(v, default, lo, hi):
    try:
        x = float(str(v).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, x))


@router.post("/site/pricing", dependencies=[Depends(csrf)])
async def pricing_save(request: Request, db: Session = Depends(get_db), user: m.User = Depends(require("head"))):
    form = await request.form()
    cur = site.pricing(db)
    data = {
        "team_per_hour": round(_num(form.get("team_per_hour"), cur["team_per_hour"], 0, 100000)),
        "hours_default": _num(form.get("hours_default"), cur["hours_default"], 1, 12),
        "min_guests": int(_num(form.get("min_guests"), cur["min_guests"], 1, 500)),
        "margin": _num(form.get("margin"), cur["margin"] * 100, 0, 100) / 100,
        "min_history": int(_num(form.get("min_history"), cur["min_history"], 1, 50)),
        "base_per_guest": {g: round(_num(form.get(f"base_{i}"), v, 0, 100000))
                           for i, (g, v) in enumerate(cur["base_per_guest"].items())},
        "options": {},
    }
    names, prices = form.getlist("opt_name"), form.getlist("opt_price")
    for k, (name, price) in enumerate(zip(names, prices, strict=False)):
        name = (name or "").strip()[:60]
        if name:
            data["options"][f"o{k}"] = [name, round(_num(price, 0, 0, 1000000))]
    site.save_pricing(db, data)
    audit(db, user.id, "site_pricing", "site")
    db.commit()
    flash(request, "Калькулятор стоимости обновлён — новые цены уже на главной")
    return RedirectResponse("/cabinet/admin/site#pricing", 303)
