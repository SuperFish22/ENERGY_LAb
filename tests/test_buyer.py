"""Главная для покупателей: заявка на тусовку, калькулятор стоимости, календарь, фотоальбом."""
import io
import os

from sqlalchemy import select

from app import models as m
from app import pricing
from app.config import PRICING, settings
from tests.conftest import Client, app

HEAD = ("head@test.local", "head-password")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_home_blocks(client):
    html = client.get("/").text
    for text in ("Мероприятия", "Какие события будут", "Заявка на", "Как рассчитывается стоимость",
                 "Фотоальбом прошедших тусовок", "Кто создаёт тусовки"):
        assert text in html
    assert "Звёздная новогодняя вечеринка" in html and "скоро продажи" in html     # утверждённое — в календаре
    assert client.get("/e/LAB-2026-09").status_code == 404                        # но без страницы продаж
    assert client.get("/archive").status_code == 200
    assert "Как это было" in client.get("/e/LAB-2026-01").text


def test_pricing_formula(db):
    rates = pricing.per_guest_rates(db)
    q = rates["Квестовые"]
    assert q["source"] == "history" and q["n"] >= 2                               # 2 квеста в демо-истории
    assert rates["Игровые"]["source"] == "norm"
    est = pricing.estimate(rates, "Квестовые", 20, hours=3, options=["venue"])
    sub = q["rate"] * 20 + PRICING["team_per_hour"] * 3 + PRICING["options"]["venue"][1]
    assert est["total"] == round(sub * (1 + PRICING["margin"]), -2)
    small = pricing.estimate(rates, "Квестовые", 3)                               # минимум гостей в расчёте
    assert dict(small["lines"])["Реквизит и материалы"] == q["rate"] * PRICING["min_guests"]


def test_party_request_flow(client, db):
    tok = client.csrf("/")
    form = {"csrf_token": tok, "name": "Ира", "contact": "+7 900 000-00-00", "occasion": "День рождения",
            "guests": "25", "message": "Квест для 14-летних"}
    r = client.post("/request", data=form, follow_redirects=False)
    assert r.headers["location"] == "/#request"
    assert not db.scalar(select(m.PartyRequest).where(m.PartyRequest.name == "Ира"))   # нет согласия
    assert "Нужно согласие" in client.get("/").text
    client.post("/request", data=form | {"consent": "1", "website": "spam"})        # бот-ловушка
    assert not db.scalar(select(m.PartyRequest).where(m.PartyRequest.name == "Ира"))
    client.post("/request", data=form | {"consent": "1", "csrf_token": client.csrf("/")})
    db.expire_all()
    pr = db.scalar(select(m.PartyRequest).where(m.PartyRequest.name == "Ира"))
    assert pr and pr.estimate and pr.status == "new"
    # контакты не уходят в мессенджер
    notes = db.scalars(select(m.Notification).where(m.Notification.text.contains("заявка"))).all()
    assert all("900" not in n.text for n in notes)
    head = Client(app).__enter__().login(*HEAD)
    assert "+7 900 000-00-00" in head.get("/cabinet/requests").text
    head.form(f"/cabinet/requests/{pr.id}", {"status": "in_work", "note": "Позвонили"}, "/cabinet/requests")
    db.expire_all()
    assert db.get(m.PartyRequest, pr.id).status == "in_work"
    member = Client(app).__enter__().login("member@energy.local")
    assert member.get("/cabinet/requests").status_code == 403


def test_photo_upload(client, db):
    head = Client(app).__enter__().login(*HEAD)
    ev = db.scalar(select(m.Event).where(m.Event.code == "LAB-2026-02"))
    page = f"/cabinet/projects/{ev.id}?tab=photos"
    files = [("files", ("a.png", io.BytesIO(PNG), "image/png")),
             ("files", ("b.txt", io.BytesIO(b"hello"), "text/plain"))]
    r = head.post(f"/cabinet/projects/{ev.id}/photos", data={"csrf_token": head.csrf(page), "caption": "Финал"},
                  files=files, follow_redirects=False)
    assert r.status_code == 303
    db.expire_all()
    ph = db.scalar(select(m.EventPhoto).where(m.EventPhoto.event_id == ev.id, m.EventPhoto.file.like("events/%")))
    assert ph and os.path.isfile(os.path.join(settings.media_dir, ph.file))
    assert client.get(f"/media/{ph.file}").status_code == 200
    head.form(f"/cabinet/projects/{ev.id}/photos/{ph.id}", {"action": "cover"}, page)
    db.expire_all()
    assert db.get(m.Event, ev.id).cover.id == ph.id
    head.form(f"/cabinet/projects/{ev.id}/photos/{ph.id}", {"action": "delete"}, page)
    assert not os.path.isfile(os.path.join(settings.media_dir, ph.file))


def test_team_slider_and_site_settings(client, db):
    html = client.get("/").text
    assert "team-slider" in html and "Олег Шведков" in html
    head = Client(app).__enter__().login(*HEAD)
    page = "/cabinet/admin/site"
    assert head.get(page).status_code == 200
    # добавить человека без согласия — на сайте не появится
    r = head.post(f"{page}/team", data={"csrf_token": head.csrf(page), "full_name": "Новая Ведущая", "role": "Ведущая",
                                        "is_public": "1"},
                  files={"photo": ("p.png", io.BytesIO(PNG), "image/png")}, follow_redirects=False)
    assert r.status_code == 303
    assert "Новая Ведущая" not in client.get("/").text
    t = db.scalar(select(m.TeamMember).where(m.TeamMember.full_name == "Новая Ведущая"))
    assert t.photo and t.photo.startswith("team/")
    head.form(f"{page}/team/{t.id}", {"full_name": "Новая Ведущая", "role": "Ведущая", "is_public": "1", "consent": "1",
                                       "action": "save"}, page)
    assert "Новая Ведущая" in client.get("/").text
    tid, photo = t.id, t.photo
    head.form(f"{page}/team/{tid}", {"action": "up"}, page)
    head.form(f"{page}/team/{tid}", {"action": "delete"}, page)
    db.expire_all()
    assert not db.get(m.TeamMember, tid)
    assert not os.path.isfile(os.path.join(settings.media_dir, photo))
    # тексты и калькулятор
    head.form(f"{page}/texts", {"lead": "Самые громкие тусовки района"}, page)
    assert "Самые громкие тусовки района" in client.get("/").text
    head.form(f"{page}/pricing", {"team_per_hour": "3000", "hours_default": "2", "min_guests": "12", "margin": "10",
                                  "min_history": "2", "opt_name": "Аниматор", "opt_price": "3500"}, page)
    from app import site
    db.expire_all()
    cfg = site.pricing(db)
    assert cfg["team_per_hour"] == 3000 and cfg["margin"] == 0.1
    assert list(cfg["options"].values()) == [["Аниматор", 3500]]
    assert "Аниматор" in client.get("/").text
    db.delete(db.get(m.SiteSetting, "pricing"))                                     # вернуть значения по умолчанию
    db.delete(db.get(m.SiteSetting, "texts"))
    db.commit()
    member = Client(app).__enter__().login("member@energy.local")
    assert member.get(page).status_code == 403
