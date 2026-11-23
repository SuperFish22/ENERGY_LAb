"""Доставка уведомлений: забрать очередь сайта, отправить в Telegram/VK с кнопками, отметить отправленными."""
from __future__ import annotations

import logging
import threading

from bot.core import Outgoing, parse_keyboard
from bot.lab import Lab

log = logging.getLogger("bot.outbox")
# ошибки, при которых повторять бессмысленно: пользователь заблокировал бота, чат не найден
PERMANENT = {400, 403}


def deliver_once(lab: Lab, senders: dict) -> int:
    r = lab.notifications()
    if not r.ok:
        if r.status:
            log.warning("Очередь уведомлений: HTTP %s", r.status)
        return 0
    sent = 0
    for item in r.get("items", []):
        sender = senders.get(item["channel"])
        if not sender:
            continue                                  # канал не настроен на этом боте — оставим в очереди
        out = Outgoing(item["channel"], str(item["chat_id"]), item["text"], parse_keyboard(item.get("reply_markup")))
        res = sender(out) or {}
        tg_ok = res.get("ok") is True
        vk_ok = "response" in res
        if tg_ok or vk_ok:
            lab.mark_sent(item["id"])
            sent += 1
        elif res.get("error_code") in PERMANENT:
            log.warning("Уведомление %s не доставлено навсегда (%s) — снимаю с очереди", item["id"],
                        res.get("error_code"))
            lab.mark_sent(item["id"])
        else:
            log.warning("Уведомление %s не отправлено, повторю позже", item["id"])
    return sent


def run(lab: Lab, senders: dict, every: int, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            n = deliver_once(lab, senders)
            if n:
                log.info("Отправлено уведомлений: %s", n)
        except Exception:
            log.exception("Ошибка доставки уведомлений")
        stop.wait(every)
