"""Администрирование: приглашения, роли, веса критериев, модерация доски; второй тур Дельфи."""
import re
from urllib.parse import urlencode

from sqlalchemy import select

from app import models as m
from app.expertise import delphi
from tests.conftest import BOT, Client, app

HEAD = ("head@test.local", "head-password")


def test_median_iqr_and_second_round_rule():
    med, iqr = delphi.median_iqr([2, 3, 4, 5])
    assert med == 3.5 and iqr > 0
    assert delphi.median_iqr([4]) == (4, 0.0)
    assert delphi.needs_second_round(0.3, 1, 0.5, 2) is True
    assert delphi.needs_second_round(0.3, 2, 0.5, 2) is False     # не больше двух туров
    assert delphi.needs_second_round(None, 1, 0.5, 2) is False


def test_invite_and_register(client, db):
    head = Client(app).__enter__().login(*HEAD)
    body = urlencode([("csrf_token", head.csrf("/cabinet/admin/users")), ("email", "new@lab.ru"), ("role", "member"),
                      ("role", "expert"), ("dept", "SMI")])
    head.post("/cabinet/admin/invite", content=body, follow_redirects=False,
              headers={"content-type": "application/x-www-form-urlencoded"})
    link = re.search(r'value="(http[^"]+/invite/[^"]+)"', head.get("/cabinet/admin/users").text).group(1)
    token_path = link.split("localhost:8000")[-1] if "localhost:8000" in link else "/invite/" + link.rsplit("/", 1)[1]
    new = Client(app).__enter__()
    r = new.form(token_path, {"full_name": "Новый Эксперт", "password": "short"}, token_path)
    assert r.status_code == 400                                       # короткий пароль, нет согласия
    r = new.form(token_path, {"full_name": "Новый Эксперт", "password": "long-password", "consent": "1"}, token_path)
    assert r.status_code == 303
    u = db.scalar(select(m.User).where(m.User.email == "new@lab.ru"))
    assert u.has_role("expert") and u.expert.department.code == "SMI"
    assert new.get("/invite/broken-token").status_code == 400


def test_last_head_cannot_lose_role(client, db):
    head = Client(app).__enter__().login(*HEAD)
    me = db.scalar(select(m.User).where(m.User.email == HEAD[0]))
    others = db.scalars(select(m.User).join(m.UserRole).join(m.Role).where(m.Role.code == "head",
                                                                           m.User.id != me.id)).all()
    for o in others:  # оставляем одного руководителя
        body = urlencode([("csrf_token", head.csrf("/cabinet/admin/users")), ("role", "member"), ("is_active", "1")])
        head.post(f"/cabinet/admin/users/{o.id}", content=body,
                  headers={"content-type": "application/x-www-form-urlencoded"})
    body = urlencode([("csrf_token", head.csrf("/cabinet/admin/users")), ("role", "member"), ("is_active", "1")])
    head.post(f"/cabinet/admin/users/{me.id}", content=body,
              headers={"content-type": "application/x-www-form-urlencoded"})
    db.expire_all()
    assert db.get(m.User, me.id).has_role("head")
    # вернём роли остальным
    for o in others:
        body = urlencode([("csrf_token", head.csrf("/cabinet/admin/users")), ("role", "member"), ("role", "head"),
                          ("role", "expert"), ("is_active", "1")])
        head.post(f"/cabinet/admin/users/{o.id}", content=body,
                  headers={"content-type": "application/x-www-form-urlencoded"})


def test_criteria_weights_normalized(client, db):
    head = Client(app).__enter__().login(*HEAD)
    d = db.scalar(select(m.Department).where(m.Department.code == "TECH"))
    data = {f"crit_{c.id}": "1" for c in d.criteria}
    head.form("/cabinet/admin/criteria", data, "/cabinet/admin/criteria")
    db.expire_all()
    d = db.scalar(select(m.Department).where(m.Department.code == "TECH"))
    assert abs(sum(c.weight for c in d.criteria) - 1) < 1e-3
    assert abs(sum(x.weight for x in db.scalars(select(m.Department))) - 1) < 1e-3


def test_moderation_notifies_bot_author(client, db):
    client.post("/api/bot/questions", json={"channel": "telegram", "user_id": "321", "text": "Во сколько отбой?",
                                            "category": "Режим дня"}, headers=BOT)
    q = db.scalar(select(m.Question).where(m.Question.text == "Во сколько отбой?"))
    head = Client(app).__enter__().login(*HEAD)
    head.form(f"/cabinet/admin/questions/{q.id}", {"action": "answer", "answer": "В 22:30"}, "/cabinet/admin/questions")
    assert "В 22:30" in client.get("/board").text
    db.expire_all()
    assert db.scalar(select(m.Notification).where(m.Notification.chat_id == "321"))


def test_second_round_shows_medians(client, db):
    ev = db.scalar(select(m.Event).where(m.Event.code == "LAB-2026-08"))
    head = Client(app).__enter__().login(*HEAD)
    page = f"/cabinet/projects/{ev.id}"
    script = db.scalar(select(m.Expert).join(m.User).where(m.User.email == "script@energy.local"))
    tech = db.scalar(select(m.Expert).join(m.User).where(m.User.email == "tech@energy.local"))
    body = urlencode([("csrf_token", head.csrf(page)), ("expert_id", str(script.id)), ("expert_id", str(tech.id))])
    head.post(f"{page}/experts", content=body, headers={"content-type": "application/x-www-form-urlencoded"})
    head.form(f"{page}/rounds", {}, page)
    c = Client(app).__enter__().login("script@energy.local")
    crit = script.department.criteria[0].id
    c.form(f"{page}/evaluate", {f"score_{crit}": "5", "action": "submit", "station_id": ""}, f"{page}/evaluate")
    head.form(f"{page}/rounds/close", {}, page)
    assert head.form(f"{page}/rounds", {}, page).status_code == 303          # второй тур
    txt = c.get(f"{page}/evaluate").text
    assert "медиана тура 1" in txt
    # большой сдвиг балла без причины не принимается
    c.form(f"{page}/evaluate", {f"score_{crit}": "2", "comment_" + str(crit): "", "action": "submit",
                                "station_id": ""}, f"{page}/evaluate")
    db.expire_all()
    rnd2 = db.scalar(select(m.ExpertiseRound).where(m.ExpertiseRound.event_id == ev.id, m.ExpertiseRound.round_no == 2))
    e = db.scalar(select(m.Evaluation).where(m.Evaluation.round_id == rnd2.id, m.Evaluation.criterion_id == crit))
    assert e.score == 5
    head.form(f"{page}/rounds/close", {}, page)
    assert head.form(f"{page}/rounds", {}, page).status_code == 303
    db.expire_all()
    assert not db.scalar(select(m.ExpertiseRound).where(m.ExpertiseRound.event_id == ev.id,
                                                        m.ExpertiseRound.round_no == 3))   # третьего тура нет


def test_export_placeholders(client, db):
    head = Client(app).__enter__().login(*HEAD)
    ev = db.scalar(select(m.Event).where(m.Event.code == "LAB-2026-01"))
    r = head.get(f"/cabinet/projects/{ev.id}/export.json")
    assert r.status_code == 200 and r.json()["placeholders"]["TITLE"] == "Велесовы тропы"
    assert "attachment" in r.headers["content-disposition"]
    assert "TITLE;Велесовы тропы" in head.get(f"/cabinet/projects/{ev.id}/export.csv").text
    assert head.get(f"/cabinet/projects/{ev.id}/export.xml").status_code == 404
    reg = head.get("/cabinet/registry.csv").text
    assert reg.startswith("﻿CODE;TITLE") and "LAB-2026-07" in reg
    member = Client(app).__enter__().login("member@energy.local")
    assert member.get("/cabinet/registry.csv").status_code == 403
    rows = client.get("/api/bot/export/registry", headers=BOT).json()["rows"]
    assert any(r["CODE"] == "LAB-2026-01" and r["GUESTS_FACT"] == 45 for r in rows)
    one = client.get("/api/bot/export/events/LAB-2026-07", headers=BOT).json()
    assert one["placeholders"]["CODE"] == "LAB-2026-07" and len(one["stations"]) == 3
    assert "@" not in str(one)                                                 # нет e-mail в выгрузке
    assert client.get("/api/bot/export/events/NOPE", headers=BOT).status_code == 404


def test_maintenance_and_profile(client, db):
    from datetime import date

    from app.maintenance import purge
    ev = db.scalar(select(m.Event).where(m.Event.code == "LAB-2026-01"))
    db.add(m.Ticket(event_id=ev.id, external_order_id=f"{ev.id}:old", email="old@x.ru", buyer_name="Гость"))
    db.commit()
    res = purge(db, today=date(2026, 10, 1))
    assert res["tickets_anonymized"] >= 1
    db.expire_all()
    assert db.scalar(select(m.Ticket).where(m.Ticket.external_order_id == f"{ev.id}:old")).email is None
    # отключение уведомлений и отвязка мессенджера
    c = Client(app).__enter__().login("smi@energy.local")
    u = db.scalar(select(m.User).where(m.User.email == "smi@energy.local"))
    u.telegram_id = "9001"
    db.commit()
    c.form("/cabinet/profile", {"full_name": "СМИ Lab", "notify_channel": "none"}, "/cabinet/profile")
    from app.notify import notify
    db.expire_all()
    u = db.get(m.User, u.id)
    before = len(db.scalars(select(m.Notification)).all())
    notify(db, u, "тест")
    db.commit()
    assert len(db.scalars(select(m.Notification)).all()) == before
    c.form("/cabinet/profile/unlink", {"channel": "telegram"}, "/cabinet/profile")
    db.expire_all()
    assert db.get(m.User, u.id).telegram_id is None


def test_timepad_cp1251(client, db):
    head = Client(app).__enter__().login(*HEAD)
    ev = db.scalar(select(m.Event).where(m.Event.code == "LAB-2026-07"))
    page = f"/cabinet/projects/{ev.id}"
    csv_text = "Номер заказа;E-mail;Сумма;Статус\n9001;a@x.ru;1300;Оплачен\n9002;b@x.ru;1300;Возврат\n"
    head.form(f"{page}/tickets/import", {}, page, files={"file": ("o.csv", csv_text.encode("cp1251"), "text/csv")})
    db.expire_all()
    t = {x.external_order_id: x.status for x in db.scalars(select(m.Ticket).where(m.Ticket.event_id == ev.id))}
    assert t[f"{ev.id}:9001"] == "paid" and t[f"{ev.id}:9002"] == "refunded"
