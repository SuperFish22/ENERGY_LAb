"""Вопросы и ответы (FAQ) и переписка поддержки (spec 005).

Поддержка — для внешних людей: покупатели и гости пишут боту, не привязывая аккаунт. Каждое их сообщение
попадает в диалог на сайте и уходит операторам (роль «Поддержка»; если таких нет — руководителям) в мессенджер
с меткой #диалогN. Оператор отвечает либо на сайте («Поддержка» в кабинете), либо прямо в своём Telegram —
ответом (reply) на это сообщение. Человеку ответ приходит от имени бота, личный аккаунт оператора не виден.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import models as m
from app.notify import notify

TAG = "#диалог"
OPERATOR_ROLES = ("support", "head")
CLIENT_PREFIX = "💬 Поддержка Energy Lab:\n"
WORD = re.compile(r"[0-9a-zа-яё]{3,}", re.I)
STOP = {"как", "что", "где", "когда", "можно", "есть", "для", "это", "или", "так", "мне", "вас", "нас", "ваш",
        "какой", "какая", "какие", "сколько", "ли", "будет", "the", "and"}


# ------------------------------------------------------------------ FAQ
def faq_items(db: Session, published_only: bool = True) -> list[m.FaqItem]:
    stmt = select(m.FaqItem).order_by(m.FaqItem.order_no, m.FaqItem.id)
    if published_only:
        stmt = stmt.where(m.FaqItem.is_published.is_(True))
    return list(db.scalars(stmt))


def faq_by_topic(items: list[m.FaqItem]) -> list[tuple[str, list[m.FaqItem]]]:
    groups: dict[str, list[m.FaqItem]] = {}
    for it in items:
        groups.setdefault(it.topic or "Общие вопросы", []).append(it)
    return list(groups.items())


def _words(text: str) -> set[str]:
    # грубая основа слова: первые 5 букв — «билеты», «билетов», «билет» совпадут
    return {w.lower()[:5] for w in WORD.findall(text or "") if w.lower() not in STOP}


def faq_search(db: Session, text: str, limit: int = 3) -> list[m.FaqItem]:
    """Похожие вопросы по совпадению слов — подсказка до ответа оператора и поиск /faq слово."""
    want = _words(text)
    if not want:
        return []
    scored = []
    for it in faq_items(db):
        q, a = _words(it.question), _words(it.answer)
        score = 2 * len(want & q) + len(want & a)
        if score >= 2:
            scored.append((score, it.order_no, it.id, it))
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    return [x[3] for x in scored[:limit]]


def faq_from_question(db: Session, q: m.Question) -> m.FaqItem:
    """Отвеченный вопрос с доски → черновик FAQ (не опубликован, пока руководитель не проверит формулировку)."""
    item = db.scalar(select(m.FaqItem).where(m.FaqItem.question_id == q.id))
    if item:
        return item
    last = db.scalar(select(func.max(m.FaqItem.order_no))) or 0
    topic = q.category if q.category and q.category not in ("Другое", "SOS") else "Общие вопросы"
    item = m.FaqItem(question=q.text.strip()[:300], answer=(q.answer or "").strip(), topic=topic[:40],
                     order_no=last + 1, is_published=False, question_id=q.id)
    db.add(item)
    return item


# ------------------------------------------------------------------ поддержка
def operators(db: Session) -> list[m.User]:
    """Операторы поддержки; если роль никому не выдана — руководители, чтобы обращения не терялись."""
    def with_role(code):
        return list(db.scalars(select(m.User).join(m.UserRole).join(m.Role)
                               .where(m.Role.code == code, m.User.is_active.is_(True)).order_by(m.User.id)))
    return with_role("support") or with_role("head")


def is_operator(user: m.User | None) -> bool:
    return bool(user and user.has_role(*OPERATOR_ROLES))


def open_count(db: Session) -> int:
    return db.scalar(select(func.count(m.SupportChat.id)).where(m.SupportChat.status == "open")) or 0


def find_chat(db: Session, channel: str, chat_id: str) -> m.SupportChat | None:
    """Последний незакрытый диалог с этим человеком."""
    return db.scalar(select(m.SupportChat).where(m.SupportChat.channel == channel, m.SupportChat.chat_id == chat_id,
                                                 m.SupportChat.status != "closed").order_by(m.SupportChat.id.desc()))


def incoming(db: Session, channel: str, chat_id: str, name: str | None, text: str) -> tuple[m.SupportChat, bool]:
    """Сообщение от человека. Возвращает (диалог, новый ли он)."""
    chat = find_chat(db, channel, chat_id)
    new = chat is None
    if new:
        chat = m.SupportChat(channel=channel, chat_id=chat_id, name=(name or "").strip()[:150] or None)
        db.add(chat)
        db.flush()
    elif name and not chat.name:
        chat.name = name.strip()[:150]
    now = datetime.now()
    db.add(m.SupportMessage(chat_id=chat.id, direction="in", text=text.strip(), source=channel, created_at=now))
    chat.status, chat.updated_at = "open", now
    who = chat.name or ("гость" if channel == "telegram" else "гость ВКонтакте")
    preview = text.strip() if len(text) <= 900 else text.strip()[:900] + "…"
    note = (f"{TAG}{chat.id} · {who} ({'Telegram' if channel == 'telegram' else 'ВКонтакте'})"
            f"{' — новый диалог' if new else ''}:\n{preview}\n\n"
            "Ответьте на это сообщение (reply) — ответ уйдёт человеку от имени бота.")
    for op in operators(db):
        notify(db, op, note, f"/cabinet/support/{chat.id}", kind="support")
    return chat, new


def reply(db: Session, chat: m.SupportChat, operator: m.User, text: str, source: str = "web") -> m.SupportMessage:
    """Ответ оператора: в диалог на сайте и человеку в мессенджер."""
    text = text.strip()
    now = datetime.now()
    msg = m.SupportMessage(chat_id=chat.id, direction="out", text=text, author_id=operator.id, source=source,
                           created_at=now)
    db.add(msg)
    chat.status, chat.updated_at, chat.operator_id = "answered", now, operator.id
    db.add(m.Notification(channel=chat.channel, chat_id=chat.chat_id, text=CLIENT_PREFIX + text))
    return msg


def close(db: Session, chat: m.SupportChat, operator: m.User, notify_client: bool = True) -> None:
    chat.status, chat.updated_at, chat.operator_id = "closed", datetime.now(), chat.operator_id or operator.id
    if notify_client:
        db.add(m.Notification(channel=chat.channel, chat_id=chat.chat_id,
                              text=CLIENT_PREFIX + "Диалог закрыт. Если появится новый вопрос — просто напишите сюда."))


def chats(db: Session, status: str = "") -> list[m.SupportChat]:
    stmt = select(m.SupportChat)
    if status in m.SUPPORT_STATUSES:
        stmt = stmt.where(m.SupportChat.status == status)
    else:
        stmt = stmt.where(or_(m.SupportChat.status != "closed",
                              m.SupportChat.updated_at >= datetime.now() - timedelta(days=30)))
    stmt = stmt.order_by((m.SupportChat.status != "open"), m.SupportChat.updated_at.desc()).limit(200)
    return list(db.scalars(stmt))
