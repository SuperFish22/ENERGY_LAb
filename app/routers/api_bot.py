"""Закрытый API для n8n (ЧТЗ-5). Авторизация: заголовок Authorization: Bearer <BOT_API_TOKEN>.

Пользователь бота определяется парой (channel, user_id), где channel — telegram или vk.
"""
import hmac
import time
from collections import defaultdict
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import export
from app import models as m
from app.config import settings
from app.db import get_db
from app.notify import notify

router = APIRouter(prefix="/api/bot", tags=["Бот (n8n)"])
Channel = Literal["telegram", "vk"]
_rate: dict[str, list[float]] = defaultdict(list)


def bot_auth(authorization: str = Header("")) -> None:
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, settings.bot_api_token):
        raise HTTPException(401, "Неверный токен бота")


def _find(db: Session, channel: str, uid: str) -> m.User | None:
    col = m.User.telegram_id if channel == "telegram" else m.User.vk_id
    return db.scalar(select(m.User).where(col == uid, m.User.is_active.is_(True)))


def _need(db: Session, channel: str, uid: str) -> m.User:
    u = _find(db, channel, uid)
    if not u:
        raise HTTPException(404, "Аккаунт не привязан. В профиле кабинета получите код и отправьте боту /link КОД")
    return u


def _rate_ok(key: str, limit: int = 5, window: int = 600) -> bool:
    now = time.time()
    _rate[key] = [t for t in _rate[key] if now - t < window]
    if len(_rate[key]) >= limit:
        return False
    _rate[key].append(now)
    return True


class Who(BaseModel):
    channel: Channel
    user_id: str = Field(min_length=1, max_length=40)


class LinkIn(Who):
    code: str = Field(min_length=6, max_length=6)


class QuestionIn(Who):
    name: str | None = Field(default=None, max_length=150)
    category: str = Field(default="Другое", max_length=30)
    text: str = Field(min_length=3, max_length=1000)


class SosIn(Who):
    name: str | None = Field(default=None, max_length=150)
    text: str | None = Field(default=None, max_length=1000)
    location: str | None = Field(default=None, max_length=200)


class DiscussionIn(Who):
    department_code: str
    title: str = Field(min_length=3, max_length=200)
    text: str | None = Field(default=None, max_length=4000)


class ReplyIn(Who):
    text: str = Field(min_length=1, max_length=4000)


class TaskStatusIn(Who):
    status: Literal["todo", "in_progress", "done"]


@router.post("/link", dependencies=[Depends(bot_auth)])
def link(data: LinkIn, db: Session = Depends(get_db)):
    lc = db.scalar(select(m.LinkCode).where(m.LinkCode.code == data.code, m.LinkCode.expires_at > datetime.now()))
    if not lc:
        raise HTTPException(400, "Код неверный или устарел. Получите новый в профиле кабинета")
    other = _find(db, data.channel, data.user_id)
    if other and other.id != lc.user_id:
        raise HTTPException(409, "Этот аккаунт мессенджера уже привязан к другому пользователю")
    user = db.get(m.User, lc.user_id)
    if data.channel == "telegram":
        user.telegram_id = data.user_id
    else:
        user.vk_id = data.user_id
    user.notify_channel = data.channel
    db.delete(lc)
    db.commit()
    return {"ok": True, "full_name": user.full_name}


@router.post("/unlink", dependencies=[Depends(bot_auth)])
def unlink(data: Who, db: Session = Depends(get_db)):
    u = _need(db, data.channel, data.user_id)
    if data.channel == "telegram":
        u.telegram_id = None
    else:
        u.vk_id = None
    db.commit()
    return {"ok": True}


@router.get("/me", dependencies=[Depends(bot_auth)])
def me(channel: Channel, user_id: str, db: Session = Depends(get_db)):
    u = _find(db, channel, user_id)
    if not u:
        return {"linked": False}
    return {"linked": True, "full_name": u.full_name, "roles": [m.ROLE_NAMES.get(r, r) for r in u.role_codes],
            "department": u.expert.department.name if u.expert else None}


@router.get("/tasks", dependencies=[Depends(bot_auth)])
def my_tasks(channel: Channel, user_id: str, db: Session = Depends(get_db)):
    u = _need(db, channel, user_id)
    items = db.scalars(select(m.Task).where(m.Task.assignee_id == u.id, m.Task.status != "done")
                       .order_by(m.Task.due_date.is_(None), m.Task.due_date)).all()
    return {"tasks": [{"id": t.id, "title": t.title, "status": t.status, "status_name": t.status_name,
                       "due_date": t.due_date.isoformat() if t.due_date else None,
                       "overdue": bool(t.due_date and t.due_date < date.today()),
                       "event": t.event.title if t.event else None,
                       "url": f"{settings.base_url}/cabinet/tasks"} for t in items]}


@router.post("/tasks/{task_id}/status", dependencies=[Depends(bot_auth)])
def task_status(task_id: int, data: TaskStatusIn, db: Session = Depends(get_db)):
    u = _need(db, data.channel, data.user_id)
    t = db.get(m.Task, task_id)
    if not t or t.assignee_id != u.id:
        raise HTTPException(404, "Задача не найдена среди ваших")
    t.status = data.status
    db.commit()
    return {"ok": True, "status_name": t.status_name}


@router.get("/departments", dependencies=[Depends(bot_auth)])
def departments(db: Session = Depends(get_db)):
    return {"departments": [{"code": d.code, "name": d.name} for d in db.scalars(select(m.Department))]}


@router.get("/discussions", dependencies=[Depends(bot_auth)])
def discussions(channel: Channel, user_id: str, department_code: str | None = None, db: Session = Depends(get_db)):
    u = _need(db, channel, user_id)
    code = department_code or (u.expert.department.code if u.expert else None)
    stmt = select(m.Discussion).where(m.Discussion.status == "open").order_by(m.Discussion.id.desc()).limit(10)
    if code:
        stmt = stmt.join(m.Department).where(m.Department.code == code)
    return {"department": code, "discussions": [
        {"id": d.id, "title": d.title, "department": d.department.name, "messages": len(d.messages),
         "url": f"{settings.base_url}/cabinet/discussions/{d.id}"} for d in db.scalars(stmt)]}


@router.post("/discussions", dependencies=[Depends(bot_auth)])
def discussion_create(data: DiscussionIn, db: Session = Depends(get_db)):
    u = _need(db, data.channel, data.user_id)
    dept = db.scalar(select(m.Department).where(m.Department.code == data.department_code))
    if not dept:
        raise HTTPException(400, "Неизвестный отдел")
    if not _rate_ok(f"disc:{data.channel}:{data.user_id}"):
        raise HTTPException(429, "Не больше 5 вопросов за 10 минут")
    d = m.Discussion(department_id=dept.id, title=data.title.strip(), author_id=u.id, source=data.channel)
    db.add(d)
    db.flush()
    if data.text:
        db.add(m.Message(discussion_id=d.id, author_id=u.id, text=data.text.strip(), source=data.channel))
    for ex in db.scalars(select(m.Expert).where(m.Expert.department_id == dept.id)):
        if ex.user_id != u.id:
            notify(db, ex.user, f"Вопрос на обсуждение ({dept.name}): {d.title}", f"/cabinet/discussions/{d.id}")
    db.commit()
    return {"ok": True, "id": d.id, "url": f"{settings.base_url}/cabinet/discussions/{d.id}"}


@router.post("/discussions/{disc_id}/messages", dependencies=[Depends(bot_auth)])
def discussion_reply(disc_id: int, data: ReplyIn, db: Session = Depends(get_db)):
    u = _need(db, data.channel, data.user_id)
    d = db.get(m.Discussion, disc_id)
    if not d or d.status != "open":
        raise HTTPException(404, "Обсуждение не найдено или закрыто")
    db.add(m.Message(discussion_id=d.id, author_id=u.id, text=data.text.strip(), source=data.channel))
    if d.author_id and d.author_id != u.id:
        notify(db, d.author, f"Ответ в обсуждении «{d.title}»", f"/cabinet/discussions/{d.id}")
    db.commit()
    return {"ok": True}


@router.post("/questions", dependencies=[Depends(bot_auth)])
def question(data: QuestionIn, db: Session = Depends(get_db)):
    if not _rate_ok(f"q:{data.channel}:{data.user_id}"):
        raise HTTPException(429, "Не больше 5 вопросов за 10 минут")
    q = m.Question(text=data.text.strip(), category=data.category, author_name=data.name, channel=data.channel,
                   channel_user_id=data.user_id)
    db.add(q)
    db.commit()
    return {"ok": True, "id": q.id}


@router.post("/sos", dependencies=[Depends(bot_auth)])
def sos(data: SosIn, db: Session = Depends(get_db)):
    """SOS не публикуется; возвращает список чатов дежурных, чтобы n8n разослал сразу в оба канала."""
    q = m.Question(text=" | ".join(x for x in (data.text, data.location) if x) or "SOS без описания",
                   category="SOS", status="sos", author_name=data.name, channel=data.channel,
                   channel_user_id=data.user_id)
    db.add(q)
    heads = db.scalars(select(m.User).join(m.UserRole).join(m.Role).where(m.Role.code == "head",
                                                                         m.User.is_active.is_(True))).all()
    db.commit()
    targets = [{"channel": "telegram", "chat_id": h.telegram_id} for h in heads if h.telegram_id]
    targets += [{"channel": "vk", "chat_id": h.vk_id} for h in heads if h.vk_id]
    phones = [h.phone for h in heads if h.phone]
    return {"ok": True, "id": q.id, "duty": targets, "duty_phones": phones,
            "reply": "Если есть угроза жизни или здоровью — звоните 112. Дежурные уже получили сообщение."}


@router.get("/events", dependencies=[Depends(bot_auth)])
def events(db: Session = Depends(get_db)):
    evs = db.scalars(select(m.Event).where(m.Event.status == "on_sale").order_by(m.Event.planned_date).limit(5)).all()
    return {"events": [{"code": e.code, "title": e.title,
                        "date": e.planned_date.isoformat() if e.planned_date else None,
                        "price": float(e.ticket_price or 0), "age": e.age_rating,
                        "url": f"{settings.base_url}/e/{e.code}"} for e in evs]}


@router.get("/notifications", dependencies=[Depends(bot_auth)])
def pending(limit: int = 50, db: Session = Depends(get_db)):
    items = db.scalars(select(m.Notification).where(m.Notification.sent_at.is_(None))
                       .order_by(m.Notification.id).limit(min(limit, 200))).all()
    return {"items": [{"id": n.id, "channel": n.channel, "chat_id": n.chat_id,
                       "text": n.text + (f"\n{n.link}" if n.link else "")} for n in items]}


@router.post("/notifications/{nid}/sent", dependencies=[Depends(bot_auth)])
def mark_sent(nid: int, db: Session = Depends(get_db)):
    n = db.get(m.Notification, nid)
    if not n:
        raise HTTPException(404)
    n.sent_at = datetime.now()
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ выгрузка в Google Диск (М-09)
@router.get("/export/registry", dependencies=[Depends(bot_auth)])
def export_registry(db: Session = Depends(get_db)):
    """Строки реестра мероприятий; n8n делает appendOrUpdate в Google Таблицу по колонке CODE."""
    return {"columns": export.REGISTRY_COLUMNS, "rows": export.registry(db)}


@router.get("/export/events/{code}", dependencies=[Depends(bot_auth)])
def export_event(code: str, db: Session = Depends(get_db)):
    """Метки {{KEY}} для копии шаблона Google Docs (заключение, паспорт проекта, отчёт)."""
    ev = db.scalar(select(m.Event).where(m.Event.code == code))
    if not ev:
        raise HTTPException(404, "Мероприятие не найдено")
    return {"placeholders": export.event_placeholders(db, ev), **export.event_tables(ev)}
