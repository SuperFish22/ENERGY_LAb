"""Вход, выход, регистрация по приглашению (CAB-01, CAB-02)."""
import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.config import settings
from app.db import get_db
from app.deps import csrf, flash, render
from app.security import audit, hash_password, limiter, verify_password

router = APIRouter()
invites = URLSafeTimedSerializer(settings.secret_key, salt="invite")


@router.get("/login")
def login_form(request: Request, next: str = "/cabinet"):
    return render(request, "public/login.html", {"next": next})


@router.post("/login", dependencies=[Depends(csrf)])
def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("/cabinet"),
          db: Session = Depends(get_db)):
    key = email.strip().lower()
    if limiter.blocked(key):
        return render(request, "public/login.html", {"error": "Слишком много попыток. Попробуйте через 15 минут",
                                                     "next": next}, 429)
    user = db.scalar(select(m.User).where(m.User.email == key))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        limiter.fail(key)
        audit(db, user.id if user else None, "login_failed", "user", key)
        db.commit()
        return render(request, "public/login.html", {"error": "Неверный e-mail или пароль", "next": next}, 401)
    limiter.reset(key)
    request.session.clear()
    request.session["uid"] = user.id
    request.session["csrf"] = secrets.token_urlsafe(24)
    audit(db, user.id, "login", "user", str(user.id))
    db.commit()
    return RedirectResponse(next if next.startswith("/") else "/cabinet", 303)


@router.post("/logout", dependencies=[Depends(csrf)])
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", 303)


def make_invite(email: str, roles: list[str], dept: str | None = None) -> str:
    return invites.dumps({"email": email, "roles": roles, "dept": dept})


@router.get("/invite/{token}")
def invite_form(token: str, request: Request):
    try:
        data = invites.loads(token, max_age=7 * 24 * 3600)
    except (BadSignature, SignatureExpired):
        return render(request, "public/message.html", {"title": "Приглашение недействительно",
                                                       "text": "Ссылка устарела или повреждена. Попросите руководителя "
                                                               "Lab прислать новую."}, 400)
    return render(request, "public/register.html", {"token": token, "email": data["email"]})


@router.post("/invite/{token}", dependencies=[Depends(csrf)])
def invite_accept(token: str, request: Request, full_name: str = Form(...), password: str = Form(...),
                  consent: str = Form(""), db: Session = Depends(get_db)):
    try:
        data = invites.loads(token, max_age=7 * 24 * 3600)
    except (BadSignature, SignatureExpired):
        return RedirectResponse(f"/invite/{token}", 303)
    if len(password) < 8 or not consent or len(full_name.strip()) < 2:
        return render(request, "public/register.html", {"token": token, "email": data["email"],
                                                        "error": "Укажите имя, пароль от 8 символов и дайте согласие "
                                                                 "на обработку персональных данных"}, 400)
    if db.scalar(select(m.User).where(m.User.email == data["email"])):
        flash(request, "Этот e-mail уже зарегистрирован. Войдите с паролем")
        return RedirectResponse("/login", 303)
    user = m.User(full_name=full_name.strip(), email=data["email"], password_hash=hash_password(password))
    user.roles = list(db.scalars(select(m.Role).where(m.Role.code.in_(data["roles"]))))
    db.add(user)
    db.flush()
    if data.get("dept"):
        d = db.scalar(select(m.Department).where(m.Department.code == data["dept"]))
        if d:
            db.add(m.Expert(user_id=user.id, department_id=d.id, competence=0.7))
    audit(db, user.id, "register", "user", data["email"])
    db.commit()
    request.session.clear()
    request.session["uid"] = user.id
    return RedirectResponse("/cabinet", 303)
