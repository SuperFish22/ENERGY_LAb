"""Уведомления об изменениях задач на сайте и в Telegram (spec 003)."""
import json
import re

from sqlalchemy import select

from app import models as m
from app import notify as nt
from app import tasks_board as tb
from tests.conftest import BOT, Client, app

HEAD = ("head@test.local", "head-password")


def _user(db, email):
    return db.scalar(select(m.User).where(m.User.email == email))


def _inbox(db, user):
    db.flush()
    return db.scalars(select(m.InboxItem).where(m.InboxItem.user_id == user.id).order_by(m.InboxItem.id.desc())).all()


def _outbox(db, user):
    db.flush()
    return db.scalars(select(m.Notification).where(m.Notification.user_id == user.id)
                      .order_by(m.Notification.id.desc())).all()


def test_notify_site_always_messenger_when_linked(db):
    u = _user(db, "tech@energy.local")
    actor = _user(db, "katya@energy.local")
    u.telegram_id, u.notify_channel = None, "telegram"
    nt.notify(db, u, "Без мессенджера", "/cabinet/tasks/1")
    assert _inbox(db, u)[0].text == "Без мессенджера" and _inbox(db, u)[0].kind == "task"
    assert not [n for n in _outbox(db, u) if "Без мессенджера" in n.text]
    u.telegram_id = "tg-777"
    nt.notify(db, u, "С кнопками", "/cabinet/tasks/1", buttons=[("✓ Сдать", "task:1:done")])
    n = _outbox(db, u)[0]
    assert n.text.startswith("📋 С кнопками") and n.chat_id == "tg-777"
    kb = json.loads(n.reply_markup)["inline_keyboard"]
    assert kb[0][0] == {"text": "✓ Сдать", "callback_data": "task:1:done"}
    nt.notify(db, actor, "Сам себе", "/cabinet/tasks/1", actor=actor)          # автору действия — не шлём
    assert not [i for i in _inbox(db, actor) if i.text == "Сам себе"]
    u.notify_channel = "none"                                                   # мессенджер отключён — сайт остаётся
    nt.notify(db, u, "Только сайт", "/cabinet/tasks/1")
    assert _inbox(db, u)[0].text == "Только сайт" and "Только сайт" not in _outbox(db, u)[0].text
    db.rollback()


def test_task_lifecycle_notifications_and_bell(db):
    head = Client(app).__enter__().login(*HEAD)
    tech = _user(db, "tech@energy.local")
    tech.telegram_id, tech.notify_channel = "tg-555", "telegram"
    db.commit()
    head.form("/cabinet/tasks", {"title": "Купить гирлянды", "assignee_id": str(tech.id), "due_date": "2026-12-01",
                                 "priority": "high"}, "/cabinet/tasks")
    t = db.scalar(select(m.Task).where(m.Task.title == "Купить гирлянды"))
    note = _inbox(db, tech)[0]
    assert "поставил(а) вам задачу «Купить гирлянды», срок 01.12 — срочно" in note.text
    assert note.link == f"/cabinet/tasks/{t.id}" and note.task_id == t.id
    tg = _outbox(db, tech)[0]
    assert [b[0]["callback_data"] for b in json.loads(tg.reply_markup)["inline_keyboard"]][:2] == \
        [f"task:{t.id}:in_progress", f"task:{t.id}:done"]
    # исполнитель видит колокольчик и всплывающее уведомление
    c = Client(app).__enter__().login("tech@energy.local")
    feed = c.get("/cabinet/notifications/feed").json()
    assert feed["unread"] >= 1 and feed["last"] >= note.id
    assert c.get(f"/cabinet/notifications/feed?after={note.id - 1}").json()["items"][-1]["text"] == note.text
    assert 'data-bell-count' in c.get("/cabinet").text and "Купить гирлянды" in c.get("/cabinet/notifications").text
    # автор меняет срок → исполнитель получает «изменил(а) задачу … срок: 05.12.2026»
    page = f"/cabinet/tasks/{t.id}"
    head.form(f"{page}/edit", {"title": "Купить гирлянды", "assignee_id": str(tech.id), "due_date": "2026-12-05",
                               "priority": "high", "description": ""}, page)
    db.expire_all()
    assert "изменил(а) задачу «Купить гирлянды»: срок → 05.12.2026" in _inbox(db, tech)[0].text
    ev = db.scalar(select(m.TaskEvent).where(m.TaskEvent.task_id == t.id, m.TaskEvent.field == "due_date"))
    assert (ev.old_value, ev.new_value) == ("01.12.2026", "05.12.2026")
    assert "05.12.2026" in head.get(page).text                                            # история на странице задачи
    # исполнитель не может править задачу
    tok = c.csrf(page)
    assert c.post(f"{page}/edit", data={"csrf_token": tok, "title": "x"}).status_code == 403
    # открыл задачу — её уведомления прочитаны
    c.get(page)
    db.expire_all()
    assert not [i for i in _inbox(db, tech) if i.task_id == t.id and i.read_at is None]
    # передача другому исполнителю: новый получает задачу, прежний — что её передали
    smi = _user(db, "smi@energy.local")
    head.form(f"{page}/edit", {"title": "Купить гирлянды", "assignee_id": str(smi.id), "due_date": "2026-12-05",
                               "priority": "high"}, page)
    db.expire_all()
    assert "передал(а) вам задачу «Купить гирлянды»" in _inbox(db, smi)[0].text
    assert "Задачу «Купить гирлянды» передали: " in _inbox(db, tech)[0].text
    hist = db.scalar(select(m.TaskEvent).where(m.TaskEvent.task_id == t.id, m.TaskEvent.field == "assignee"))
    assert hist.old_value == tech.full_name and hist.new_value == smi.full_name


def test_review_accept_from_telegram_and_read_all(client, db):
    head_user = _user(db, "head@test.local")
    author = _user(db, "katya@energy.local")
    assignee = _user(db, "script@energy.local")
    author.telegram_id, author.notify_channel = "tg-katya", "telegram"
    t = m.Task(title="Сценарий финала", author_id=author.id, assignee_id=assignee.id, status="in_progress",
               position=tb.new_position(db, "in_progress"))
    db.add(t)
    db.commit()
    tb.move(db, assignee, t, "done")                                    # исполнитель сдаёт → «На проверке»
    db.commit()
    note = _outbox(db, author)[0]
    assert "Проверьте задачу «Сценарий финала»" in note.text
    assert json.loads(note.reply_markup)["inline_keyboard"][0][0]["callback_data"] == f"task:{t.id}:done"
    items = client.get("/api/bot/notifications", headers=BOT).json()["items"]
    mine = next(i for i in items if i["id"] == note.id)
    assert json.loads(mine["reply_markup"])["inline_keyboard"] and mine["chat_id"] == "tg-katya"
    # автор жмёт «Принять» в Telegram
    r = client.post(f"/api/bot/tasks/{t.id}/status", json={"channel": "telegram", "user_id": "tg-katya",
                                                          "status": "done"}, headers=BOT)
    assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["title"] == "Сценарий финала"
    assert "принята ✓" in _inbox(db, assignee)[0].text
    # посторонний не может
    outsider = _user(db, "smi@energy.local")
    outsider.telegram_id = "tg-smi"
    db.commit()
    r = client.post(f"/api/bot/tasks/{t.id}/status", json={"channel": "telegram", "user_id": "tg-smi",
                                                          "status": "todo"}, headers=BOT)
    assert r.status_code == 404
    # «Прочитать все» на сайте
    c = Client(app).__enter__().login("script@energy.local")
    assert c.get("/cabinet/notifications/feed").json()["unread"] >= 1
    c.form("/cabinet/notifications/read", {}, "/cabinet/notifications")
    assert c.get("/cabinet/notifications/feed").json()["unread"] == 0
    assert head_user is not None


def test_open_notification_marks_read_and_redirects(db):
    u = _user(db, "member@energy.local")
    nt.notify(db, u, "Посмотрите проект", "/cabinet/projects")
    db.commit()
    item = _inbox(db, u)[0]
    c = Client(app).__enter__().login("member@energy.local")
    r = c.get(f"/cabinet/notifications/{item.id}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/cabinet/projects"
    db.expire_all()
    assert db.get(m.InboxItem, item.id).read_at is not None
    other = Client(app).__enter__().login("smi@energy.local")
    assert other.get(f"/cabinet/notifications/{item.id}").status_code == 404           # чужое — не открыть
    assert re.search(r"Уведомления", c.get("/cabinet/notifications").text)
