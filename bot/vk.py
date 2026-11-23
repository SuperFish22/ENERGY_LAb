"""ВКонтакте: Bots Long Poll API сообщества (без вебхука). Включается, если заданы VK_GROUP_TOKEN и VK_GROUP_ID.

Кнопки — inline-клавиатура с payload {"cmd": "task:5:done"}; нажатие приходит обычным сообщением с payload.
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time

from bot.core import Button, Incoming, Outgoing, handle
from bot.lab import Lab
from bot.net import Requester, request

log = logging.getLogger("bot.vk")
API = "https://api.vk.com/method/{method}"
V = "5.199"


def keyboard(buttons: list[list[Button]]) -> str | None:
    rows = []
    for row in buttons[:6]:
        r = []
        for text, data in row[:4]:
            if data.startswith("url:"):
                r.append({"action": {"type": "open_link", "link": data[4:], "label": text[:40]}})
            else:
                r.append({"action": {"type": "text", "label": text[:40], "payload": json.dumps({"cmd": data})}})
        if r:
            rows.append(r)
    return json.dumps({"inline": True, "buttons": rows}, ensure_ascii=False) if rows else None


class VK:
    def __init__(self, token: str, group_id: str, transport: Requester = request):
        self.token, self.group_id, self.t = token, group_id, transport

    def call(self, method: str, **params) -> dict:
        try:
            _, data = self.t("POST", API.format(method=method),
                             form={**params, "access_token": self.token, "v": V}, timeout=35)
        except OSError:
            return {"error": {"error_msg": "network"}}
        if isinstance(data, dict) and "error" in data:
            log.warning("VK %s: %s", method, data["error"].get("error_msg"))
        return data if isinstance(data, dict) else {}

    def send(self, out: Outgoing) -> dict:
        params = {"peer_id": out.chat_id, "random_id": random.randint(1, 2**31 - 1), "message": out.text[:4000]}
        kb = keyboard(out.buttons)
        if kb:
            params["keyboard"] = kb
        return self.call("messages.send", **params)


def to_incoming(obj: dict) -> Incoming | None:
    msg = obj.get("message") or {}
    if not msg or msg.get("from_id", 0) <= 0:
        return None
    cb = ""
    if msg.get("payload"):
        try:
            cb = json.loads(msg["payload"]).get("cmd", "")
        except (ValueError, AttributeError):
            cb = ""
    reply = (msg.get("reply_message") or {}).get("text") or ""
    return Incoming("vk", str(msg["from_id"]), str(msg["peer_id"]), "", text="" if cb else msg.get("text", ""),
                    callback=cb, reply_to_text=reply)


class VKPoller:
    def __init__(self, vk: VK, lab: Lab, senders: dict):
        self.vk, self.lab, self.senders = vk, lab, senders
        self.server = self.key = self.ts = None

    def connect(self) -> bool:
        r = self.vk.call("groups.getLongPollServer", group_id=self.vk.group_id).get("response")
        if not r:
            return False
        self.server, self.key, self.ts = r["server"], r["key"], r["ts"]
        return True

    def poll_once(self) -> None:
        if not self.server and not self.connect():
            time.sleep(10)
            return
        try:
            _, data = self.vk.t("GET", self.server, params={"act": "a_check", "key": self.key, "ts": self.ts,
                                                             "wait": 25}, timeout=35)
        except OSError:
            time.sleep(5)
            return
        if not isinstance(data, dict) or "failed" in data:
            if isinstance(data, dict) and data.get("failed") == 1:
                self.ts = data.get("ts", self.ts)
            else:
                self.server = None
            return
        self.ts = data.get("ts", self.ts)
        for upd in data.get("updates", []):
            if upd.get("type") != "message_new":
                continue
            inc = to_incoming(upd.get("object") or {})
            if not inc:
                continue
            try:
                for out in handle(self.lab, inc):
                    sender = self.senders.get(out.channel)
                    if sender:
                        sender(out)
            except Exception:
                log.exception("Ошибка обработки сообщения VK")

    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            self.poll_once()
