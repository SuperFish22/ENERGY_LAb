"""Кабинет оператора поддержки: диалоги с покупателями и гостями, которые пишут боту (spec 005)."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app import models as m
from app import support
from app.db import get_db
from app.deps import csrf, flash, render, require
from app.security import audit

router = APIRouter(prefix="/cabinet/support")
operator = require(*support.OPERATOR_ROLES)


def _chat(db: Session, chat_id: int) -> m.SupportChat:
    chat = db.get(m.SupportChat, chat_id)
    if not chat:
        raise HTTPException(404, "Диалог не найден")
    return chat


def _msg(x: m.SupportMessage) -> dict:
    return {"id": x.id, "dir": x.direction, "text": x.text, "at": x.created_at.strftime("%d.%m %H:%M"),
            "who": x.author.full_name if x.author else None,
            "source": {"web": "с сайта", "telegram": "из Telegram", "vk": "из ВКонтакте"}.get(x.source, "")}


@router.get("")
def chats(request: Request, status: str = "", db: Session = Depends(get_db), user: m.User = Depends(operator)):
    return render(request, "cabinet/support.html", {
        "user": user, "chats": support.chats(db, status), "status": status, "statuses": m.SUPPORT_STATUSES,
        "nav": "support", "operators": support.operators(db)})


@router.get("/{chat_id}")
def chat_view(chat_id: int, request: Request, db: Session = Depends(get_db), user: m.User = Depends(operator)):
    chat = _chat(db, chat_id)
    hints = support.faq_search(db, " ".join(x.text for x in chat.messages if x.direction == "in")[-1000:], limit=4)
    return render(request, "cabinet/support_chat.html", {"user": user, "chat": chat, "nav": "support",
                                                         "hints": hints, "statuses": m.SUPPORT_STATUSES})


@router.get("/{chat_id}/feed")
def chat_feed(chat_id: int, after: int = 0, db: Session = Depends(get_db), user: m.User = Depends(operator)):
    """Новые сообщения для открытой страницы диалога (опрос раз в 10 секунд)."""
    chat = _chat(db, chat_id)
    return JSONResponse({"status": chat.status, "status_name": chat.status_name,
                         "messages": [_msg(x) for x in chat.messages if x.id > after]})


@router.post("/{chat_id}", dependencies=[Depends(csrf)])
def chat_reply(chat_id: int, request: Request, text: str = Form(""), db: Session = Depends(get_db),
               user: m.User = Depends(operator)):
    chat = _chat(db, chat_id)
    text = text.strip()
    if not text:
        flash(request, "Напишите ответ", "error")
        return RedirectResponse(f"/cabinet/support/{chat.id}", 303)
    msg = support.reply(db, chat, user, text[:4000], source="web")
    db.commit()
    if request.headers.get("accept", "").startswith("application/json"):
        return JSONResponse({"ok": True, "message": _msg(msg), "status_name": chat.status_name})
    return RedirectResponse(f"/cabinet/support/{chat.id}#m{msg.id}", 303)


@router.post("/{chat_id}/status", dependencies=[Depends(csrf)])
def chat_status(chat_id: int, request: Request, action: str = Form(...), db: Session = Depends(get_db),
                user: m.User = Depends(operator)):
    chat = _chat(db, chat_id)
    if action == "close":
        support.close(db, chat, user)
        flash(request, "Диалог закрыт, человеку ушло короткое сообщение об этом")
    elif action == "reopen":
        chat.status = "open"
    elif action == "delete" and user.has_role("head"):
        audit(db, user.id, "support_delete", "support", str(chat.id))
        db.delete(chat)
        db.commit()
        flash(request, "Диалог удалён вместе с перепиской")
        return RedirectResponse("/cabinet/support", 303)
    db.commit()
    return RedirectResponse(f"/cabinet/support/{chat.id}", 303)
