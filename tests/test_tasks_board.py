"""Доска задач (spec 001): правила переходов, порядок карточек, история, доска в кабинете и в боте."""
import re

import pytest
from sqlalchemy import select

from app import models as m
from app import tasks_board as tb
from tests.conftest import BOT, Client, app

HEAD = ("head@test.local", "head-password")


def _user(db, email):
    return db.scalar(select(m.User).where(m.User.email == email))


@pytest.fixture
def people(db):
    return {"head": _user(db, "oleg@energy.local"), "author": _user(db, "katya@energy.local"),
            "assignee": _user(db, "script@energy.local"), "other": _user(db, "member@energy.local")}


def _task(db, author, assignee, status="todo", title="Тестовая задача"):
    t = m.Task(title=title, author_id=author.id, assignee_id=assignee.id, status=status,
               position=tb.new_position(db, status))
    db.add(t)
    db.flush()
    return t


# ---------------------------------------------------------------- правила переходов (data-model.md)
# (кто, из, в, разрешено?)
CASES = [
    ("assignee", "todo", "in_progress", True),
    ("assignee", "in_progress", "todo", True),
    ("assignee", "in_progress", "review", True),
    ("assignee", "todo", "review", True),
    ("assignee", "review", "in_progress", False),     # вернуть с проверки — не исполнитель
    ("assignee", "review", "done", False),
    ("assignee", "done", "todo", False),
    ("author", "todo", "done", True),
    ("author", "review", "done", True),
    ("author", "done", "in_progress", True),
    ("head", "review", "done", True),
    ("head", "todo", "review", True),
    ("other", "todo", "in_progress", False),
    ("other", "review", "done", False),
]


@pytest.mark.parametrize("who,frm,to,allowed", CASES)
def test_transition_rules(db, people, who, frm, to, allowed):
    t = _task(db, people["author"], people["assignee"], frm)
    err = tb.can_move(people[who], t, to, comment="поправь")
    assert (err is None) is allowed, err
    db.rollback()


def test_assignee_done_goes_to_review_and_own_task_closes(db, people):
    t = _task(db, people["author"], people["assignee"], "in_progress")
    res = tb.move(db, people["assignee"], t, "done")
    assert res.ok and t.status == "review" and res.note == "Отправлено на проверку автору"
    own = _task(db, people["assignee"], people["assignee"], "in_progress")
    assert tb.move(db, people["assignee"], own, "done").status == "done" and own.done_at is not None
    db.rollback()


def test_return_from_review_needs_comment_and_is_logged(db, people):
    people["assignee"].telegram_id = "tg-test-1"                    # чтобы уведомление встало в очередь
    t = _task(db, people["author"], people["assignee"], "review")
    res = tb.move(db, people["author"], t, "in_progress")
    assert not res.ok and res.error == tb.NEED_COMMENT and t.status == "review"
    res = tb.move(db, people["author"], t, "in_progress", comment="Добавь смету")
    assert res.ok and t.status == "in_progress"
    ev = db.scalar(select(m.TaskEvent).where(m.TaskEvent.task_id == t.id))
    assert (ev.old_value, ev.new_value, ev.comment, ev.user_id) == ("review", "in_progress", "Добавь смету",
                                                                     people["author"].id)
    note = db.scalar(select(m.Notification).where(m.Notification.user_id == people["assignee"].id)
                     .order_by(m.Notification.id.desc()))
    assert "Добавь смету" in note.text
    db.rollback()


def test_conflict_when_someone_moved_first(db, people):
    t = _task(db, people["author"], people["assignee"], "in_progress")
    res = tb.move(db, people["head"], t, "done", expected="todo")
    assert res.conflict and not res.ok and t.status == "in_progress"
    db.rollback()


def test_positions_insert_between_and_renumber(db, people):
    a, b = (_task(db, people["author"], people["assignee"], "todo", n) for n in ("A", "B"))
    c = _task(db, people["author"], people["assignee"], "in_progress", "C")
    tb.move(db, people["head"], c, "todo", before_id=b.id)          # между A и B
    assert a.position < c.position < b.position
    a.position, b.position = 5000, 5001                              # соседи слиплись
    c.position = 0
    tb.place(db, c, "todo", b.id)
    col = sorted([a, b, c], key=lambda t: t.position)
    assert [t.title for t in col][-2:] == ["C", "B"] and len({t.position for t in col}) == 3
    db.rollback()


# ---------------------------------------------------------------- кабинет
def test_board_page_and_move_endpoint(db):
    head = Client(app).__enter__().login(*HEAD)
    page = head.get("/cabinet/tasks?scope=all").text
    for name in m.TASK_STATUSES.values():
        assert name in page
    assert 'data-board' in page and 'name="status"' in page                # работает и без JS
    t = db.scalar(select(m.Task).where(m.Task.status == "todo"))
    tok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = head.post(f"/cabinet/tasks/{t.id}/move", data={"csrf_token": tok, "status": "in_progress", "expected": "todo"},
                  headers={"Accept": "application/json"})
    assert r.status_code == 200 and r.json()["status"] == "in_progress"
    db.refresh(t)
    assert t.status == "in_progress"
    # повтор с устаревшим статусом — конфликт
    r = head.post(f"/cabinet/tasks/{t.id}/move", data={"csrf_token": tok, "status": "done", "expected": "todo"},
                  headers={"Accept": "application/json"})
    assert r.status_code == 409
    # без JS — обычная форма с переадресацией
    r = head.post(f"/cabinet/tasks/{t.id}/move", data={"csrf_token": tok, "status": "todo"}, follow_redirects=False)
    assert r.status_code == 303


def test_stranger_cannot_move(db):
    member = Client(app).__enter__().login("member@energy.local")
    t = db.scalar(select(m.Task).where(m.Task.assignee_id != _user(db, "member@energy.local").id))
    tok = member.csrf("/cabinet/tasks")
    r = member.post(f"/cabinet/tasks/{t.id}/move", data={"csrf_token": tok, "status": "done"},
                    headers={"Accept": "application/json"})
    assert r.status_code == 403 and r.json()["error"] == tb.NO_RIGHTS


def test_bot_done_sends_to_review(client, db):
    c = Client(app).__enter__().login("smi@energy.local")
    c.form("/cabinet/profile/link-code", {}, "/cabinet/profile")
    u = _user(db, "smi@energy.local")
    code = db.scalar(select(m.LinkCode).where(m.LinkCode.user_id == u.id).order_by(m.LinkCode.id.desc())).code
    client.post("/api/bot/link", json={"channel": "telegram", "user_id": "4242", "code": code}, headers=BOT)
    t = db.scalar(select(m.Task).where(m.Task.assignee_id == u.id, m.Task.author_id != u.id,
                                       m.Task.status.in_(("todo", "in_progress"))))
    r = client.post(f"/api/bot/tasks/{t.id}/status", json={"channel": "telegram", "user_id": "4242", "status": "done"},
                    headers=BOT)
    assert r.status_code == 200 and r.json()["status"] == "review" and r.json()["status_name"] == "На проверке"
    ev = db.scalar(select(m.TaskEvent).where(m.TaskEvent.task_id == t.id).order_by(m.TaskEvent.id.desc()))
    assert ev.source == "telegram"
