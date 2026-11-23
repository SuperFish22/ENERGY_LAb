"""Логика бота, не зависящая от мессенджера: разобрать входящее → спросить сайт → собрать ответы с кнопками.

Команды: /start, /link КОД, /unlink, /tasks, /ask, /discussions, /afisha, /faq [слово], /question ТЕКСТ,
ответ (reply) на сообщение с #обсуждениеN или #диалогN. Кнопки: task:ID:статус, ask:КОД, faq:ID.
Обычный текст (не команда) от человека без привязанного аккаунта уходит в поддержку — операторам (spec 005).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from bot.lab import Lab

Button = tuple[str, str]            # (текст, callback_data) или (текст, "url:https://…")


@dataclass
class Incoming:
    channel: str                    # telegram / vk
    user_id: str
    chat_id: str
    name: str = ""
    text: str = ""
    callback: str = ""              # данные нажатой кнопки
    reply_to_text: str = ""         # текст сообщения, на которое ответили (reply)

    @property
    def who(self) -> dict:
        return {"channel": self.channel, "user_id": self.user_id}


@dataclass
class Outgoing:
    channel: str
    chat_id: str
    text: str
    buttons: list[list[Button]] = field(default_factory=list)


HELP = ("Команды:\n/tasks — мои задачи\n/ask — вопрос отделу\n/discussions — обсуждения отдела\n"
        "/afisha — ближайшие запуски\n/faq — частые вопросы\n/question ТЕКСТ — вопрос на доску\n"
        "/link КОД — привязать")
START_LINKED = ("Привет, {name}! Центр управления на связи 🚀\n/tasks — мои задачи\n/ask — вопрос отделу\n"
                "/discussions — обсуждения отдела\n/afisha — ближайшие запуски\n/faq — частые вопросы")
START_GUEST = ("Привет! Это бот Energy Lab 🚀\nНапишите свой вопрос обычным сообщением — ответит живой оператор, "
               "ответ придёт сюда.\n/faq — частые вопросы\n/afisha — ближайшие мероприятия\n\n"
               "Вы из команды Lab? Получите код в кабинете («Профиль» → «Бот и уведомления») и отправьте /link КОД.")
SUPPORT_NEW = "Передали ваш вопрос оператору — ответ придёт сюда. Обычно отвечаем в течение рабочего дня."


def parse(inc: Incoming) -> tuple[str, dict]:
    """Маршрут и аргументы. Порядок проверок повторяет прежний сценарий n8n."""
    cb, text = inc.callback or "", (inc.text or "").strip()
    if cb.startswith("task:"):
        parts = cb.split(":")
        if len(parts) == 3 and parts[1].isdigit():
            return "task_status", {"id": int(parts[1]), "status": parts[2]}
        return "help", {}
    if cb.startswith("faq:"):
        return ("faq_item", {"id": int(cb[4:])}) if cb[4:].isdigit() else ("faq", {"q": ""})
    if cb.startswith("ask:"):
        return "help", {"hint": f"Напишите одним сообщением:\n/ask {cb[4:]} Тема вопроса | подробности"}
    if re.match(r"^/start\b", text):
        return "start", {}
    if m := re.match(r"^/link(?:@\w+)?\s+(\d{6})\b", text):
        return "link", {"code": m.group(1)}
    if re.match(r"^/link\b", text):
        return "help", {"hint": "Пришлите код из кабинета: /link 123456"}
    if re.match(r"^/unlink\b", text):
        return "unlink", {}
    if re.match(r"^/tasks\b|^мои задачи", text, re.I):
        return "tasks", {}
    if m := re.match(r"^/ask(?:@\w+)?\s+([A-Z]+)\s+(.+)$", text, re.S):
        title, _, rest = m.group(2).partition("|")
        return "ask", {"department_code": m.group(1), "title": title.strip()[:200], "text": rest.strip() or None}
    if re.match(r"^/ask\b|^вопрос отделу", text, re.I):
        return "ask_menu", {}
    if re.match(r"^/discussions\b|^обсуждения", text, re.I):
        return "discussions", {}
    if m := re.match(r"^/question(?:@\w+)?\s+(.{3,})$", text, re.S):
        return "question", {"text": m.group(1).strip()}
    if re.match(r"^/afisha\b|^афиша", text, re.I):
        return "afisha", {}
    if m := re.match(r"^(?:/faq(?:@\w+)?|частые вопросы|вопросы и ответы)(?:\s+(.+))?$", text, re.I | re.S):
        return "faq", {"q": (m.group(1) or "").strip()}
    if inc.reply_to_text and (m := re.search(r"#диалог(\d+)", inc.reply_to_text)) and text:
        return "support_reply", {"id": int(m.group(1)), "text": text}
    if inc.reply_to_text and (m := re.search(r"#обсуждение(\d+)", inc.reply_to_text)) and text:
        return "reply", {"id": int(m.group(1)), "text": text}
    if text and not text.startswith("/"):
        return "support", {"text": text}
    return "help", {}


def handle(lab: Lab, inc: Incoming) -> list[Outgoing]:
    route, args = parse(inc)
    out = Outgoing(inc.channel, inc.chat_id, "")
    extra: list[Outgoing] = []
    who = inc.who

    if route == "start":
        r = lab.me(who)
        out.text = START_LINKED.format(name=r.get("full_name")) if r.get("linked") else START_GUEST
        if r.error:
            out.text = r.error
    elif route == "link":
        r = lab.link(who, args["code"])
        out.text = r.error or f"Готово, {r.get('full_name')}. Аккаунт привязан, уведомления будут приходить сюда."
    elif route == "unlink":
        r = lab.unlink(who)
        out.text = r.error or "Аккаунт отвязан. Уведомлений больше не будет."
    elif route == "tasks":
        r = lab.tasks(who)
        if r.error:
            out.text = r.error
        elif not r.get("tasks"):
            out.text = "Открытых задач нет. Чистая орбита ✨"
        else:
            tasks = r.get("tasks")
            lines = ["Ваши задачи:"]
            for i, t in enumerate(tasks, 1):
                tail = f", срок {_ru_date(t['due_date'])}" if t.get("due_date") else ""
                lines.append(f"{i}. {t['title']}{' — ' + t['event'] if t.get('event') else ''}\n   "
                             f"{t['status_name']}{tail}{' ⚠️ просрочено' if t.get('overdue') else ''}")
            out.text = "\n".join(lines)
            for i, t in enumerate(tasks[:8], 1):
                if t["status"] == "review":              # ждёт автора — кнопок нет
                    continue
                row = [(f"{i} → в работу", f"task:{t['id']}:in_progress")] if t["status"] == "todo" else []
                out.buttons.append(row + [(f"{i} → сдать", f"task:{t['id']}:done")])
    elif route == "task_status":
        r = lab.task_status(who, args["id"], args["status"])
        out.text = r.error or f"«{r.get('title') or 'Задача'}» — {r.get('status_name')}" \
                              + (f". {r.get('note')}" if r.get("note") else "")
    elif route == "ask_menu":
        r = lab.departments()
        out.text = r.error or "Какому отделу вопрос?"
        out.buttons = [[(d["name"], f"ask:{d['code']}")] for d in r.get("departments", [])]
    elif route == "ask":
        r = lab.ask(who, args["department_code"], args["title"], args["text"])
        out.text = r.error or f"Вопрос отправлен отделу. Эксперты получат уведомление.\n{r.get('url')}"
    elif route == "discussions":
        r = lab.discussions(who)
        items = r.get("discussions", [])
        out.text = r.error or ("Открытые обсуждения:\n" + "\n".join(
            f"#обсуждение{d['id']} {d['title']} ({d['messages']})\n{d['url']}" for d in items)
            + "\n\nЧтобы ответить — ответьте (reply) на это сообщение строкой с нужным #обсуждением."
            if items else "Открытых обсуждений нет.")
    elif route == "reply":
        r = lab.reply(who, args["id"], args["text"])
        out.text = r.error or "Ответ добавлен в обсуждение."
    elif route == "question":
        r = lab.question(who, inc.name or None, args["text"])
        out.text = r.error or "Вопрос отправлен модератору. Ответ придёт сюда."
    elif route == "afisha":
        r = lab.events()
        evs = r.get("events", [])
        out.text = r.error or ("Ближайшие запуски:\n" + "\n".join(
            f"{_ru_date(e['date']) if e.get('date') else 'дата уточняется'} — {e['title']} ({e['age']}), "
            f"{_money(e['price'])}\n{e['url']}" for e in evs) if evs else "Пока нет мероприятий в продаже.")
    elif route == "faq":
        r = lab.faq(args["q"])
        items = r.get("items", [])
        if r.error:
            out.text = r.error
        elif not items:
            out.text = (f"По запросу «{args['q']}» ничего не нашлось. Напишите вопрос обычным сообщением — ответит "
                        "оператор." if args["q"] else "Раздел «Вопросы и ответы» пока пуст.")
        else:
            out.text = ("Похожие вопросы:" if args["q"] else "Частые вопросы — нажмите, чтобы увидеть ответ:") + \
                       (f"\nВсе ответы на сайте: {r.get('url')}" if r.get("url") else "")
            out.buttons = _faq_buttons(items)
    elif route == "faq_item":
        r = lab.faq_item(args["id"])
        out.text = r.error or f"❓ {r.get('question')}\n\n{r.get('answer')}"
    elif route == "support":
        r = lab.support(who, inc.name or None, args["text"])
        if r.get("linked"):
            out.text = HELP
        elif r.error:
            out.text = r.error
        elif r.get("new"):
            out.text = SUPPORT_NEW
            if r.get("faq"):
                out.text += "\n\nПока ждёте — возможно, ответ уже есть:"
                out.buttons = _faq_buttons(r.get("faq"))
        else:
            out.text = ""                       # диалог уже идёт — не отвечаем на каждое сообщение
    elif route == "support_reply":
        r = lab.support_reply(who, args["id"], args["text"])
        out.text = r.error or f"Ответ отправлен{' — ' + r.get('name') if r.get('name') else ''} (#диалог{args['id']})."
    else:
        out.text = args.get("hint") or HELP
    return [o for o in (out, *extra) if o.text]


def _faq_buttons(items: list[dict]) -> list[list[Button]]:
    return [[(_short(f["question"]), f"faq:{f['id']}")] for f in items[:10]]


def _short(text: str, n: int = 60) -> str:
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _ru_date(iso: str) -> str:
    y, mth, d = iso[:10].split("-")
    return f"{d}.{mth}.{y}"


def _money(v) -> str:
    return f"{int(round(float(v or 0))):,} ₽".replace(",", " ")


def parse_keyboard(reply_markup) -> list[list[Button]]:
    """reply_markup из очереди уведомлений сайта (JSON-строка Telegram) → кнопки в общем виде."""
    import json
    if not reply_markup:
        return []
    try:
        data = json.loads(reply_markup) if isinstance(reply_markup, str) else reply_markup
    except ValueError:
        return []
    rows = []
    for row in (data or {}).get("inline_keyboard", []):
        btns = [(b["text"], b["callback_data"]) if "callback_data" in b else (b["text"], "url:" + b["url"])
                for b in row if "text" in b and ("callback_data" in b or "url" in b)]
        if btns:
            rows.append(btns)
    return rows
