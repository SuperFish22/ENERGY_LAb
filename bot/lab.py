"""Клиент закрытого API сайта /api/bot/* (Authorization: Bearer BOT_API_TOKEN)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.net import Requester, request


@dataclass
class Reply:
    status: int
    data: Any

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def error(self) -> str | None:
        if self.ok:
            return None
        if self.status == 401:
            return "Бот не смог авторизоваться на сайте — сообщите администратору"
        d = self.data if isinstance(self.data, dict) else {}
        detail = d.get("detail")
        if isinstance(detail, str):
            return detail
        if self.status >= 500 or self.status == 0:
            return "Сайт сейчас недоступен, попробуйте через минуту"
        return "Проверьте команду"

    def get(self, key, default=None):
        return self.data.get(key, default) if isinstance(self.data, dict) else default


class Lab:
    def __init__(self, base_url: str, token: str, transport: Requester = request):
        self.base = base_url.rstrip("/") + "/api/bot"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.t = transport

    def _call(self, method: str, path: str, *, params=None, body=None) -> Reply:
        try:
            status, data = self.t(method, self.base + path, params=params, json_body=body, headers=self.headers,
                                  timeout=20)
        except OSError:
            return Reply(0, None)
        return Reply(status, data)

    # --- пользователь
    def me(self, who: dict) -> Reply:
        return self._call("GET", "/me", params=who)

    def link(self, who: dict, code: str) -> Reply:
        return self._call("POST", "/link", body={**who, "code": code})

    def unlink(self, who: dict) -> Reply:
        return self._call("POST", "/unlink", body=who)

    # --- задачи
    def tasks(self, who: dict) -> Reply:
        return self._call("GET", "/tasks", params=who)

    def task_status(self, who: dict, task_id: int, status: str) -> Reply:
        return self._call("POST", f"/tasks/{task_id}/status", body={**who, "status": status})

    # --- обсуждения, доска, афиша
    def departments(self) -> Reply:
        return self._call("GET", "/departments")

    def discussions(self, who: dict) -> Reply:
        return self._call("GET", "/discussions", params=who)

    def ask(self, who: dict, department_code: str, title: str, text: str | None) -> Reply:
        return self._call("POST", "/discussions", body={**who, "department_code": department_code, "title": title,
                                                         "text": text})

    def reply(self, who: dict, disc_id: int, text: str) -> Reply:
        return self._call("POST", f"/discussions/{disc_id}/messages", body={**who, "text": text})

    def question(self, who: dict, name: str | None, text: str) -> Reply:
        return self._call("POST", "/questions", body={**who, "name": name, "text": text})

    # --- вопросы и ответы, поддержка
    def faq(self, q: str = "") -> Reply:
        return self._call("GET", "/faq", params={"q": q} if q else None)

    def faq_item(self, faq_id: int) -> Reply:
        return self._call("GET", f"/faq/{faq_id}")

    def support(self, who: dict, name: str | None, text: str) -> Reply:
        return self._call("POST", "/support", body={**who, "name": name, "text": text})

    def support_reply(self, who: dict, chat_id: int, text: str) -> Reply:
        return self._call("POST", f"/support/{chat_id}/reply", body={**who, "text": text})

    def events(self) -> Reply:
        return self._call("GET", "/events")

    # --- очередь уведомлений
    def notifications(self, limit: int = 50) -> Reply:
        return self._call("GET", "/notifications", params={"limit": limit})

    def mark_sent(self, nid: int) -> Reply:
        return self._call("POST", f"/notifications/{nid}/sent")
