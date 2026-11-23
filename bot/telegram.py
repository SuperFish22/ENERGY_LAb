"""Telegram Bot API: long polling (getUpdates) — без вебхука, домена и nginx на сервере бота."""
from __future__ import annotations

import logging
import threading
import time

from bot.core import Button, Incoming, Outgoing, handle
from bot.lab import Lab
from bot.net import Requester, request

log = logging.getLogger("bot.telegram")
API = "https://api.telegram.org/bot{token}/{method}"


def keyboard(buttons: list[list[Button]]) -> dict | None:
    rows = []
    for row in buttons:
        r = []
        for text, data in row:
            if data.startswith("url:"):
                url = data[4:]
                if url.startswith("https://"):          # Telegram не принимает ссылки на localhost/http
                    r.append({"text": text, "url": url})
            else:
                r.append({"text": text, "callback_data": data[:64]})
        if r:
            rows.append(r)
    return {"inline_keyboard": rows} if rows else None


def to_incoming(update: dict) -> tuple[Incoming | None, str | None]:
    """Update Telegram → Incoming и id callback-запроса (его нужно подтвердить, чтобы у кнопки пропали «часики»)."""
    if "callback_query" in update:
        cq = update["callback_query"]
        msg, frm = cq.get("message") or {}, cq.get("from") or {}
        chat = (msg.get("chat") or {}).get("id", frm.get("id"))
        return Incoming("telegram", str(frm.get("id")), str(chat), _name(frm), callback=cq.get("data") or ""), cq["id"]
    msg = update.get("message")
    if not msg or "text" not in msg:
        return None, None
    frm = msg.get("from") or {}
    if (msg.get("chat") or {}).get("type") not in (None, "private"):
        return None, None                                 # в группах бот молчит: задачи и поддержка — личное
    reply = (msg.get("reply_to_message") or {}).get("text") or ""
    return Incoming("telegram", str(frm.get("id")), str(msg["chat"]["id"]), _name(frm), text=msg["text"],
                    reply_to_text=reply), None


def _name(frm: dict) -> str:
    return " ".join(x for x in (frm.get("first_name"), frm.get("last_name")) if x)


class Telegram:
    def __init__(self, token: str, transport: Requester = request):
        self.token, self.t = token, transport

    def call(self, method: str, http_timeout: float = 30, **body) -> dict:
        try:
            status, data = self.t("POST", API.format(token=self.token, method=method), json_body=body,
                                  timeout=http_timeout)
        except OSError as e:
            log.warning("Telegram %s: сеть недоступна (%s)", method, e.__class__.__name__)
            return {"ok": False, "error_code": 0, "description": "network"}
        if not isinstance(data, dict):
            return {"ok": False, "error_code": status, "description": str(data)[:200]}
        if not data.get("ok"):
            log.warning("Telegram %s: %s %s", method, data.get("error_code"), data.get("description"))
        return data

    def send(self, out: Outgoing) -> dict:
        body = {"chat_id": out.chat_id, "text": out.text[:4096], "disable_web_page_preview": True}
        kb = keyboard(out.buttons)
        if kb:
            body["reply_markup"] = kb
        return self.call("sendMessage", **body)

    def answer_callback(self, cq_id: str, text: str = "") -> None:
        self.call("answerCallbackQuery", callback_query_id=cq_id, text=text[:200])


class TelegramPoller:
    """Цикл getUpdates. Перед стартом снимает вебхук (его ставил n8n), иначе Telegram вернёт 409."""

    def __init__(self, tg: Telegram, lab: Lab, senders: dict, timeout: int = 25):
        self.tg, self.lab, self.senders, self.timeout = tg, lab, senders, timeout
        self.offset = 0

    def start(self) -> None:
        me = self.tg.call("getMe")
        if me.get("ok"):
            log.info("Telegram: бот @%s", me["result"].get("username"))
        self.tg.call("deleteWebhook", drop_pending_updates=False)

    def process(self, update: dict) -> None:
        inc, cq_id = to_incoming(update)
        if inc is None:
            return
        outs = handle(self.lab, inc)
        if cq_id:
            # ответ на кнопку — коротко во всплывашке и полностью сообщением
            first = outs[0].text if outs else ""
            self.tg.answer_callback(cq_id, first if len(first) <= 200 else "")
        for out in outs:
            sender = self.senders.get(out.channel)
            if sender:
                sender(out)

    def poll_once(self) -> int:
        r = self.tg.call("getUpdates", http_timeout=self.timeout + 10, offset=self.offset, timeout=self.timeout,
                         allowed_updates=["message", "callback_query"])
        if not r.get("ok"):
            if r.get("error_code") == 409:
                log.error("Telegram 409: этот токен уже слушает кто-то другой (вебхук n8n или вторая копия бота). "
                          "Выключите сценарии Telegram в n8n — бот снимет вебхук сам.")
                self.tg.call("deleteWebhook", drop_pending_updates=False)
            time.sleep(5)
            return 0
        updates = r.get("result") or []
        for u in updates:
            self.offset = max(self.offset, u["update_id"] + 1)
            try:
                self.process(u)
            except Exception:                        # одно битое сообщение не должно ронять бота
                log.exception("Ошибка обработки update %s", u.get("update_id"))
        return len(updates)

    def run(self, stop: threading.Event) -> None:
        self.start()
        while not stop.is_set():
            self.poll_once()

