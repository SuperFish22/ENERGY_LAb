"""Бот на Python вместо n8n: команды, кнопки, поддержка, доставка уведомлений — насквозь через настоящий API сайта."""
import json
import threading

import pytest
from sqlalchemy import select

from app import models as m
from app import tasks_board as tb
from bot import core
from bot.config import Config
from bot.core import Incoming, Outgoing, parse
from bot.lab import Lab
from bot.outbox import deliver_once
from bot.telegram import Telegram, TelegramPoller, keyboard, to_incoming
from bot.vk import keyboard as vk_keyboard
from bot.vk import to_incoming as vk_incoming
from tests.conftest import Client, app


# ---------------------------------------------------------------- транспорт: бот → сайт без сети
@pytest.fixture
def lab(client):
    def transport(method, url, *, params=None, json_body=None, form=None, headers=None, timeout=30):
        path = url.split("://", 1)[1].split("/", 1)[1]
        r = client.request(method, "/" + path, params=params, json=json_body, headers=headers)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, r.text
    return Lab("http://lab.test", "test-bot-token", transport)


class FakeTelegram(Telegram):
    """Telegram, который ничего не шлёт в сеть, а записывает вызовы."""

    def __init__(self, replies=None):
        super().__init__("TEST", transport=self._t)
        self.calls, self.replies = [], replies or {}

    def _t(self, method, url, *, json_body=None, **_):
        name = url.rsplit("/", 1)[1]
        self.calls.append((name, json_body))
        return 200, self.replies.get(name, {"ok": True, "result": {"message_id": len(self.calls)}})

    def sent(self, chat_id=None):
        return [b for n, b in self.calls if n == "sendMessage" and (chat_id is None or b["chat_id"] == chat_id)]


def _user(db, email):
    return db.scalar(select(m.User).where(m.User.email == email))


def _msg(user_id, text, reply_to=None, chat_type="private"):
    msg = {"message_id": 1, "from": {"id": user_id, "first_name": "Тест"}, "chat": {"id": user_id, "type": chat_type},
           "text": text}
    if reply_to:
        msg["reply_to_message"] = {"text": reply_to}
    return {"update_id": 100, "message": msg}


def _cb(user_id, data):
    return {"update_id": 101, "callback_query": {"id": "cq1", "from": {"id": user_id, "first_name": "Тест"},
                                                  "message": {"chat": {"id": user_id}}, "data": data}}


# ---------------------------------------------------------------- разбор команд (как было в n8n)
@pytest.mark.parametrize("text,cb,route,args", [
    ("/start", "", "start", {}),
    ("/link 123456", "", "link", {"code": "123456"}),
    ("/link@EnergyBot 654321", "", "link", {"code": "654321"}),
    ("/link", "", "help", {"hint": "Пришлите код из кабинета: /link 123456"}),
    ("Мои задачи", "", "tasks", {}),
    ("/ask SC Тема | подробности", "", "ask", {"department_code": "SC", "title": "Тема", "text": "подробности"}),
    ("/ask", "", "ask_menu", {}),
    ("/question Когда квиз?", "", "question", {"text": "Когда квиз?"}),
    ("/sos", "", "help", {}),                                  # SOS больше нет (spec 005)
    ("/faq", "", "faq", {"q": ""}),
    ("/faq билет", "", "faq", {"q": "билет"}),
    ("Частые вопросы", "", "faq", {"q": ""}),
    ("", "faq:7", "faq_item", {"id": 7}),
    ("", "task:42:done", "task_status", {"id": 42, "status": "done"}),
    ("", "task:x:done", "help", {}),
    ("Здравствуйте, сколько стоит квест?", "", "support", {"text": "Здравствуйте, сколько стоит квест?"}),
    ("/непонятно", "", "help", {}),
])
def test_parse(text, cb, route, args):
    assert parse(Incoming("telegram", "1", "1", text=text, callback=cb)) == (route, args)


def test_reply_to_discussion_and_support():
    inc = Incoming("telegram", "1", "1", text="Согласен", reply_to_text="#обсуждение7 Свет (2)")
    assert parse(inc) == ("reply", {"id": 7, "text": "Согласен"})
    inc = Incoming("telegram", "1", "1", text="Да, можно", reply_to_text="🛟 #диалог12 · Анна (Telegram):\nМожно?")
    assert parse(inc) == ("support_reply", {"id": 12, "text": "Да, можно"})


# ---------------------------------------------------------------- насквозь через сайт
def test_link_tasks_buttons_review_and_accept(lab, db):
    tg = FakeTelegram()
    poller = TelegramPoller(tg, lab, {"telegram": tg.send})
    # незнакомец
    poller.process(_msg(5001, "/start"))
    assert "/link КОД" in tg.sent("5001")[-1]["text"] and "оператор" in tg.sent("5001")[-1]["text"]
    assert "Задача" not in tg.sent("5001")[-1]["text"]
    # код привязки из кабинета → /link
    web = Client(app).__enter__().login("tech@energy.local")
    web.form("/cabinet/profile/link-code", {}, "/cabinet/profile")
    tech = _user(db, "tech@energy.local")
    code = db.scalar(select(m.LinkCode).where(m.LinkCode.user_id == tech.id).order_by(m.LinkCode.id.desc())).code
    poller.process(_msg(5001, f"/link {code}"))
    assert "Аккаунт привязан" in tg.sent("5001")[-1]["text"]
    # задача от автора → /tasks с кнопками
    author = _user(db, "katya@energy.local")
    t = m.Task(title="Проверить звук", author_id=author.id, assignee_id=tech.id, status="todo",
               position=tb.new_position(db))
    db.add(t)
    db.commit()
    poller.process(_msg(5001, "/tasks"))
    reply = tg.sent("5001")[-1]
    assert "Проверить звук" in reply["text"]
    flat = [b["callback_data"] for row in reply["reply_markup"]["inline_keyboard"] for b in row]
    assert f"task:{t.id}:in_progress" in flat and f"task:{t.id}:done" in flat
    # кнопка «сдать» → «На проверке», всплывашка у кнопки подтверждена
    poller.process(_cb(5001, f"task:{t.id}:done"))
    assert any(n == "answerCallbackQuery" for n, _ in tg.calls)
    assert "На проверке" in tg.sent("5001")[-1]["text"]
    db.expire_all()
    assert db.get(m.Task, t.id).status == "review"
    # автор получает уведомление с кнопкой «Принять» (доставка очереди)
    author.telegram_id, author.notify_channel = "5002", "telegram"
    db.commit()
    tb.move(db, author, db.get(m.Task, t.id), "in_progress", comment="Добавь проверку микрофонов")
    db.commit()
    tb.move(db, tech, db.get(m.Task, t.id), "done")
    db.commit()
    n = deliver_once(lab, {"telegram": tg.send})
    assert n >= 1
    to_author = tg.sent("5002")[-1]
    assert "Проверьте задачу «Проверить звук»" in to_author["text"]
    kb = to_author["reply_markup"]["inline_keyboard"]
    assert kb[0][0] == {"text": "✓ Принять", "callback_data": f"task:{t.id}:done"}
    to_tech = [s for s in tg.sent("5001") if "вернули в работу" in s["text"]]
    assert to_tech and "Добавь проверку микрофонов" in to_tech[-1]["text"]
    assert not db.scalars(select(m.Notification).where(m.Notification.sent_at.is_(None),
                                                       m.Notification.channel == "telegram")).all()
    # автор жмёт «Принять» прямо под уведомлением
    poller.process(_cb(5002, f"task:{t.id}:done"))
    db.expire_all()
    assert db.get(m.Task, t.id).status == "done"
    assert "Выполнено" in tg.sent("5002")[-1]["text"]


def test_support_guest_operator_telegram_and_site(lab, db):
    """Гость пишет боту → диалог на сайте и уведомление операторам с #диалогN → оператор отвечает reply в Telegram
    → гость получает ответ от бота; ответ с сайта тоже доходит."""
    op = _user(db, "support@energy.local")
    op.telegram_id, op.notify_channel = "7101", "telegram"
    db.commit()
    tg = FakeTelegram()
    poller = TelegramPoller(tg, lab, {"telegram": tg.send})
    poller.process(_msg(7999, "Здравствуйте! Можно ли вернуть билет, если заболел?"))
    first = tg.sent("7999")[-1]
    assert "оператору" in first["text"]
    hints = [b["callback_data"] for row in first["reply_markup"]["inline_keyboard"] for b in row]
    assert hints and all(h.startswith("faq:") for h in hints)              # подсказка из FAQ про возврат
    poller.process(_cb(7999, hints[0]))
    assert "Timepad" in tg.sent("7999")[-1]["text"]
    chat = db.scalar(select(m.SupportChat).where(m.SupportChat.chat_id == "7999"))
    assert chat and chat.status == "open" and chat.name == "Тест"
    # второе сообщение в том же диалоге — бот молчит, оператор получает
    before = len(tg.sent("7999"))
    poller.process(_msg(7999, "Билет на «Ночь в музее»"))
    assert len(tg.sent("7999")) == before
    deliver_once(lab, {"telegram": tg.send})
    to_op = tg.sent("7101")[-1]["text"]
    assert f"#диалог{chat.id}" in to_op and "Ночь в музее" in to_op and "reply" in to_op
    # оператор отвечает reply прямо в Telegram
    poller.process(_msg(7101, "Да, через Timepad, ссылка в письме с билетом.", reply_to=to_op))
    assert "Ответ отправлен" in tg.sent("7101")[-1]["text"]
    deliver_once(lab, {"telegram": tg.send})
    got = tg.sent("7999")[-1]["text"]
    assert got.startswith("💬 Поддержка Energy Lab") and "ссылка в письме" in got
    db.expire_all()
    chat = db.get(m.SupportChat, chat.id)
    assert chat.status == "answered" and chat.messages[-1].source == "telegram"
    # ответ с сайта
    web = Client(app).__enter__().login("support@energy.local")
    page = web.get(f"/cabinet/support/{chat.id}").text
    assert "Ночь в музее" in page and "ссылка в письме" in page
    web.form(f"/cabinet/support/{chat.id}", {"text": "Если что-то ещё — пишите!"}, f"/cabinet/support/{chat.id}")
    deliver_once(lab, {"telegram": tg.send})
    assert "пишите!" in tg.sent("7999")[-1]["text"]
    feed = web.get(f"/cabinet/support/{chat.id}/feed", params={"after": 0}).json()
    assert [x["dir"] for x in feed["messages"]][-2:] == ["out", "out"]
    # участник Lab без роли поддержки не может отвечать в диалогах
    tech = _user(db, "tech@energy.local")
    tech.telegram_id = "7102"
    db.commit()
    poller.process(_msg(7102, "Влезу в чужой диалог", reply_to=to_op))
    assert "операторы поддержки" in tg.sent("7102")[-1]["text"]
    # привязанному участнику обычный текст не открывает диалог — бот показывает команды
    poller.process(_msg(7102, "привет"))
    assert "/tasks" in tg.sent("7102")[-1]["text"]
    assert not db.scalar(select(m.SupportChat).where(m.SupportChat.chat_id == "7102"))


def test_faq_command(lab):
    tg = FakeTelegram()
    poller = TelegramPoller(tg, lab, {"telegram": tg.send})
    poller.process(_msg(7201, "/faq"))
    r = tg.sent("7201")[-1]
    assert "Частые вопросы" in r["text"] and r["reply_markup"]["inline_keyboard"]
    poller.process(_msg(7201, "/faq возраст"))
    assert "Похожие" in tg.sent("7201")[-1]["text"]
    poller.process(_msg(7201, "/faq абракадабра"))
    assert "ничего не нашлось" in tg.sent("7201")[-1]["text"]
    poller.process(_cb(7201, "faq:999999"))
    assert "больше нет" in tg.sent("7201")[-1]["text"]


def test_afisha_ask_menu_and_question(lab, db):
    tg = FakeTelegram()
    poller = TelegramPoller(tg, lab, {"telegram": tg.send})
    poller.process(_msg(8001, "/afisha"))
    assert "Ближайшие запуски" in tg.sent("8001")[-1]["text"] and "₽" in tg.sent("8001")[-1]["text"]
    poller.process(_msg(8001, "/ask"))
    menu = tg.sent("8001")[-1]["reply_markup"]["inline_keyboard"]
    assert menu and menu[0][0]["callback_data"].startswith("ask:")
    poller.process(_msg(8001, "/question Будет ли квиз в декабре?"))
    assert "модератору" in tg.sent("8001")[-1]["text"]
    poller.process(_msg(8001, "/tasks"))
    assert "/link" in tg.sent("8001")[-1]["text"] or "привяж" in tg.sent("8001")[-1]["text"].lower()


def test_polling_offset_groups_and_409(lab):
    tg = FakeTelegram({"getUpdates": {"ok": True, "result": [
        {"update_id": 10, **{k: v for k, v in _msg(9001, "/start").items() if k != "update_id"}},
        {"update_id": 11, **{k: v for k, v in _msg(-100, "/start", chat_type="group").items() if k != "update_id"}},
    ]}})
    poller = TelegramPoller(tg, lab, {"telegram": tg.send})
    assert poller.poll_once() == 2 and poller.offset == 12
    assert len(tg.sent("9001")) == 1 and not tg.sent("-100")                 # в группах бот молчит
    tg409 = FakeTelegram({"getUpdates": {"ok": False, "error_code": 409, "description": "Conflict"}})
    import bot.telegram as bt
    sleep, bt.time.sleep = bt.time.sleep, lambda s: None
    try:
        TelegramPoller(tg409, lab, {}).poll_once()
    finally:
        bt.time.sleep = sleep
    assert ("deleteWebhook", {"drop_pending_updates": False}) in tg409.calls


def test_outbox_retries_and_permanent_errors(lab, db):
    u = _user(db, "smi@energy.local")
    u.telegram_id, u.notify_channel = "6001", "telegram"
    from app.notify import notify
    notify(db, u, "Проверка доставки", "/cabinet/tasks")
    db.commit()
    nid = db.scalar(select(m.Notification.id).where(m.Notification.chat_id == "6001")
                    .order_by(m.Notification.id.desc()))
    down = FakeTelegram({"sendMessage": {"ok": False, "error_code": 0, "description": "network"}})
    deliver_once(lab, {"telegram": down.send})
    db.expire_all()
    assert db.get(m.Notification, nid).sent_at is None                      # сеть упала — повторим
    blocked = FakeTelegram({"sendMessage": {"ok": False, "error_code": 403, "description": "blocked by user"}})
    deliver_once(lab, {"telegram": blocked.send})
    db.expire_all()
    assert db.get(m.Notification, nid).sent_at is not None                  # заблокировал бота — снимаем


def test_keyboards_and_vk():
    kb = keyboard([[("Открыть", "url:http://localhost/x")], [("Сдать", "task:1:done"), ("Сайт", "url:https://a.b/c")]])
    assert kb == {"inline_keyboard": [[{"text": "Сдать", "callback_data": "task:1:done"},
                                       {"text": "Сайт", "url": "https://a.b/c"}]]}
    assert keyboard([]) is None
    markup = {"inline_keyboard": [[{"text": "✓ Принять", "callback_data": "task:5:done"}],
                                  [{"text": "Открыть", "url": "https://x"}]]}
    parsed = core.parse_keyboard(json.dumps(markup))
    assert parsed == [[("✓ Принять", "task:5:done")], [("Открыть", "url:https://x")]]
    assert core.parse_keyboard("{}") == [] and core.parse_keyboard("") == []
    vk = json.loads(vk_keyboard(parsed))
    assert vk["inline"] and json.loads(vk["buttons"][0][0]["action"]["payload"]) == {"cmd": "task:5:done"}
    inc = vk_incoming({"message": {"from_id": 77, "peer_id": 77, "text": "1 → сдать",
                                   "payload": json.dumps({"cmd": "task:9:done"})}})
    assert inc.channel == "vk" and inc.callback == "task:9:done" and inc.text == ""
    assert vk_incoming({"message": {"from_id": -5, "peer_id": 1, "text": "x"}}) is None
    tg_inc, cq = to_incoming(_cb(3, "task:2:in_progress"))
    assert tg_inc.callback == "task:2:in_progress" and cq == "cq1"
    assert to_incoming({"update_id": 1, "edited_message": {}}) == (None, None)


def test_config_problems(monkeypatch):
    for k in ("BOT_API_TOKEN", "TELEGRAM_BOT_TOKEN", "VK_GROUP_TOKEN", "VK_GROUP_ID"):
        monkeypatch.delenv(k, raising=False)
    assert len(Config().problems()) == 2
    monkeypatch.setenv("BOT_API_TOKEN", "x")
    monkeypatch.setenv("VK_GROUP_TOKEN", "y")
    assert Config().problems() == ["Для VK нужен VK_GROUP_ID"]


def test_wrong_token_is_reported(client):
    def transport(method, url, **kw):
        r = client.request(method, "/" + url.split("://", 1)[1].split("/", 1)[1], params=kw.get("params"),
                           json=kw.get("json_body"), headers=kw.get("headers"))
        return r.status_code, r.json()
    bad = Lab("http://lab.test", "wrong", transport)
    r = bad.me({"channel": "telegram", "user_id": "1"})
    assert r.status == 401 and "авторизоваться" in r.error
    out = core.handle(bad, Incoming("telegram", "1", "1", text="/tasks"))
    assert isinstance(out[0], Outgoing) and "авторизоваться" in out[0].text
    assert threading.active_count() >= 1
