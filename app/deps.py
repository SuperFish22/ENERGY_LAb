"""Зависимости FastAPI: текущий пользователь, проверка ролей, CSRF, шаблоны."""
from datetime import date

from fastapi import Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import models as m
from app.config import settings
from app.db import get_db
from app.security import check_csrf, csrf_token

templates = Jinja2Templates(directory="app/templates")


def _money(v) -> str:
    if v is None:
        return "—"
    return f"{float(v):,.0f}".replace(",", " ") + " ₽"


def _num(v, digits=2) -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}".replace(".", ",")


def _date(v) -> str:
    return v.strftime("%d.%m.%Y") if v else "—"


MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]


def _date_long(v) -> str:
    return f"{v.day} {MONTHS[v.month - 1]}" if v else "дата уточняется"


def _days_left(v) -> int | None:
    return (v - date.today()).days if v else None


templates.env.filters.update(money=_money, num=_num, ru_date=_date, date_long=_date_long, days_left=_days_left)
templates.env.globals.update(app_name=settings.app_name, ROLE_NAMES=m.ROLE_NAMES)


class LoginRequired(Exception):
    pass


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> m.User | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    user = db.get(m.User, uid)
    if not user or not user.is_active:
        request.session.clear()
        return None
    return user


def current_user(user: m.User | None = Depends(current_user_optional)) -> m.User:
    if user is None:
        raise LoginRequired()
    return user


def require(*roles: str):
    def dep(user: m.User = Depends(current_user)) -> m.User:
        if not user.has_role(*roles):
            raise HTTPException(status_code=403, detail="Недостаточно прав для этого действия")
        return user
    return dep


def csrf(request: Request, csrf_token_: str = Form("", alias="csrf_token")) -> None:
    if not check_csrf(request.session, csrf_token_):
        raise HTTPException(status_code=400, detail="Форма устарела. Обновите страницу и отправьте ещё раз")


def render(request: Request, name: str, ctx: dict | None = None, status_code: int = 200):
    ctx = dict(ctx or {})
    ctx.setdefault("request", request)
    ctx["csrf_token"] = csrf_token(request.session)
    ctx.setdefault("flash", request.session.pop("flash", None))
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def flash(request: Request, text: str, kind: str = "ok") -> None:
    request.session["flash"] = {"text": text, "kind": kind}
