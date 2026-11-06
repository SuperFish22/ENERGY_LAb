"""Постановка уведомлений в очередь. n8n забирает их через /api/bot/notifications (ЧТЗ-5, BOT-05)."""
from sqlalchemy.orm import Session

from app import models as m
from app.config import settings


def notify(db: Session, user: m.User | None, text: str, link: str | None = None) -> None:
    if user is None:
        return
    url = f"{settings.base_url}{link}" if link else None
    channels = []
    if user.notify_channel in ("none", "email"):      # пользователь отключил уведомления в мессенджер
        return
    if user.notify_channel == "vk" and user.vk_id:
        channels.append(("vk", user.vk_id))
    elif user.telegram_id:
        channels.append(("telegram", user.telegram_id))
    elif user.vk_id:
        channels.append(("vk", user.vk_id))
    for ch, chat in channels:
        db.add(m.Notification(user_id=user.id, channel=ch, chat_id=chat, text=text, link=url))


def notify_heads(db: Session, text: str, link: str | None = None) -> None:
    from sqlalchemy import select
    heads = db.scalars(select(m.User).join(m.UserRole).join(m.Role).where(m.Role.code == "head")).all()
    for h in heads:
        notify(db, h, text, link)
