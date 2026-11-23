"""Уведомления (ЧТЗ-5, BOT-05; spec 003).

Каждое уведомление — два канала:
* сайт: запись в `inbox` — колокольчик в кабинете, всегда, независимо от настроек мессенджера;
* мессенджер: запись в очередь `notifications`, её забирает n8n через /api/bot/notifications и отправляет
  в Telegram (с кнопками под сообщением) или VK. Только если мессенджер привязан и не отключён в профиле.
Того, кто сам совершил действие, не уведомляем — это решает вызывающий код (actor).
"""
from __future__ import annotations

import json

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import models as m
from app.config import settings

KIND_BY_LINK = (("/cabinet/tasks", "task"), ("/cabinet/projects", "project"), ("/cabinet/discussions", "discussion"),
                ("/cabinet/requests", "request"), ("/cabinet/admin/questions", "request"),
                ("/cabinet/support", "support"))
ICON = {"task": "📋", "project": "🚀", "discussion": "💬", "request": "📨", "support": "🛟", "system": "🔔"}


def _kind(link: str | None) -> str:
    return next((k for prefix, k in KIND_BY_LINK if link and link.startswith(prefix)), "system")


def tg_keyboard(buttons: list[tuple[str, str]] | None, url: str | None) -> str | None:
    """Кнопки под сообщением Telegram: действия (callback «task:id:статус») и «Открыть на сайте».
    Кнопка-ссылка — только для https: Telegram не принимает ссылки на localhost."""
    rows = [[{"text": t, "callback_data": data}] for t, data in (buttons or [])]
    if url and url.startswith("https://"):
        rows.append([{"text": "Открыть на сайте", "url": url}])
    return json.dumps({"inline_keyboard": rows}, ensure_ascii=False) if rows else None


def notify(db: Session, user: m.User | None, text: str, link: str | None = None, *, kind: str | None = None,
           task: m.Task | None = None, actor: m.User | None = None,
           buttons: list[tuple[str, str]] | None = None) -> None:
    if user is None or (actor is not None and actor.id == user.id):
        return
    kind = kind or _kind(link)
    db.add(m.InboxItem(user_id=user.id, kind=kind, text=text, link=link, task_id=task.id if task else None,
                       actor_id=actor.id if actor else None))
    if user.notify_channel in ("none", "email"):      # пользователь отключил уведомления в мессенджер
        return
    url = f"{settings.base_url}{link}" if link else None
    if user.notify_channel == "vk" and user.vk_id:
        channel, chat = "vk", user.vk_id
    elif user.telegram_id:
        channel, chat = "telegram", user.telegram_id
    elif user.vk_id:
        channel, chat = "vk", user.vk_id
    else:
        return
    db.add(m.Notification(user_id=user.id, channel=channel, chat_id=chat, text=f"{ICON.get(kind, '🔔')} {text}",
                          link=url, reply_markup=tg_keyboard(buttons, url) if channel == "telegram" else None))


def notify_heads(db: Session, text: str, link: str | None = None, *, actor: m.User | None = None) -> None:
    heads = db.scalars(select(m.User).join(m.UserRole).join(m.Role).where(m.Role.code == "head")).all()
    for h in heads:
        notify(db, h, text, link, actor=actor)


# ------------------------------------------------------------------ колокольчик на сайте
def unread_count(db: Session, user: m.User) -> int:
    return db.scalar(select(func.count(m.InboxItem.id)).where(m.InboxItem.user_id == user.id,
                                                              m.InboxItem.read_at.is_(None))) or 0


def mark_read(db: Session, user: m.User, item_id: int | None = None) -> int:
    """Отметить прочитанным одно уведомление или все. Возвращает число отмеченных."""
    from datetime import datetime
    stmt = update(m.InboxItem).where(m.InboxItem.user_id == user.id, m.InboxItem.read_at.is_(None))
    if item_id is not None:
        stmt = stmt.where(m.InboxItem.id == item_id)
    return db.execute(stmt.values(read_at=datetime.now())).rowcount or 0


def mark_read_task(db: Session, user: m.User, task_id: int) -> int:
    """Пользователь открыл задачу — все его непрочитанные уведомления по ней прочитаны."""
    from datetime import datetime
    return db.execute(update(m.InboxItem).where(m.InboxItem.user_id == user.id, m.InboxItem.task_id == task_id,
                                                m.InboxItem.read_at.is_(None)).values(read_at=datetime.now())
                      ).rowcount or 0
