"""Сквозной сценарий ТЗ, раздел 7: проект → экспертиза → прогноз → утверждение → продажи → анкета → факт."""
from urllib.parse import urlencode

from sqlalchemy import select

from app import models as m
from tests.conftest import BOT, Client, app

HEAD = ("head@test.local", "head-password")


def _expert_login(email):
    c = Client(app)
    c.__enter__()
    return c.login(email)


def test_public_pages(client):
    for url in ("/", "/afisha", "/board", "/e/LAB-2026-07"):
        assert client.get(url).status_code == 200
    assert "Т−" in client.get("/").text
    assert client.get("/e/LAB-2026-08").status_code == 404     # проект на экспертизе в афише не виден


def test_cabinet_requires_login(client):
    r = client.get("/cabinet", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_login_lockout(client):
    tok = client.csrf()
    for _ in range(5):
        client.post("/login", data={"email": "nobody@x.ru", "password": "bad", "csrf_token": tok})
    r = client.post("/login", data={"email": "nobody@x.ru", "password": "bad", "csrf_token": tok})
    assert r.status_code == 429


def test_csrf_required(client):
    client.login(*HEAD)
    r = client.post("/cabinet/tasks", data={"title": "без токена"})
    assert r.status_code == 400


def test_full_flow(client, db):
    member = Client(app).__enter__().login("member@energy.local")
    # 1. участник создаёт проект и станции
    r = member.form("/cabinet/projects/new", {"title": "Звёздный квиз", "format_id": "1", "planned_date": "2026-12-05",
                                              "age_rating": "12+", "ticket_price": "800", "planned_budget": "9000",
                                              "capacity": "50", "venue_id": "1"}, page="/cabinet/projects/new")
    assert r.status_code == 303
    ev_id = int(r.headers["location"].rsplit("/", 1)[1])
    page = f"/cabinet/projects/{ev_id}"
    for t, cost in (("Старт", 2000), ("Орбита", 3000), ("Посадка", 2500)):
        r = member.form(f"{page}/stations", {"title": t, "duration_min": "20", "cost": str(cost)}, page)
        assert r.status_code == 303
    assert member.form(f"{page}/status", {"to": "review"}, page).status_code == 303
    # участник не может сам утвердить проект
    assert member.form(f"{page}/status", {"to": "evaluated"}, page).status_code == 403

    # 2. руководитель назначает экспертов и открывает тур
    head = Client(app).__enter__().login(*HEAD)
    experts = db.scalars(select(m.Expert).join(m.User).where(m.User.email.in_(
        ["oleg@energy.local", "script@energy.local", "tech@energy.local", "smi@energy.local"]))).all()
    body = urlencode([("csrf_token", head.csrf(page))] + [("expert_id", str(e.id)) for e in experts])
    r = head.post(f"{page}/experts", content=body, follow_redirects=False,
                  headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 303
    assert head.form(f"{page}/rounds", {"deadline": "2026-11-20"}, page).status_code == 303

    # 3. эксперты оценивают проект и станции
    ev = db.get(m.Event, ev_id)
    db.refresh(ev)
    station_ids = [s.id for s in ev.stations]
    plans = {"oleg@energy.local": [5, 4, 3], "script@energy.local": [4, 4, 2], "tech@energy.local": [5, 3, 3],
             "smi@energy.local": [4, 5, 2]}
    for email, st_scores in plans.items():
        c = _expert_login(email)
        ex = next(e for e in experts if e.user.email == email)
        crits = [cr.id for cr in ex.department.criteria]
        ev_page = f"{page}/evaluate"
        data = {f"score_{cid}": "4" for cid in crits} | {"action": "submit", "station_id": ""}
        assert c.form(ev_page, data, ev_page).status_code == 303
        for sid, sc in zip(station_ids, st_scores, strict=True):
            data = {f"score_{cid}": str(sc) for cid in crits}
            data |= {"action": "submit", "station_id": str(sid), "probability": "2" if sc > 2 else "4",
                     "impact": "2" if sc > 2 else "4"}
            if sc <= 2:
                data |= {f"comment_{cid}": "Нужна доработка" for cid in crits}
            assert c.form(ev_page, data, ev_page).status_code == 303
        # чужой отдел оценивать нельзя
        other = db.scalar(select(m.Criterion).where(m.Criterion.department_id != ex.department_id))
        bad = c.form(ev_page, {f"score_{other.id}": "3", "action": "submit", "station_id": ""}, ev_page)
        assert bad.status_code == 403

    # балл 1 без комментария не сохраняется
    c = _expert_login("tech@energy.local")
    tech = next(e for e in experts if e.user.email == "tech@energy.local")
    cid = tech.department.criteria[0].id
    c.form(f"{page}/evaluate", {f"score_{cid}": "1", "action": "submit", "station_id": ""}, f"{page}/evaluate")
    db.expire_all()
    e = db.scalar(select(m.Evaluation).where(m.Evaluation.expert_id == tech.id, m.Evaluation.criterion_id == cid,
                                             m.Evaluation.station_id.is_(None)))
    assert e.score == 4

    # 4. закрытие тура, прогноз, утверждение
    assert head.form(f"{page}/rounds/close", {}, page).status_code == 303
    assert head.form(f"{page}/forecast", {}, page).status_code == 303
    db.expire_all()
    fc = db.scalar(select(m.Forecast).where(m.Forecast.event_id == ev_id).order_by(m.Forecast.id.desc()))
    assert fc.expert_score is not None and 1 <= fc.expert_score <= 5
    assert fc.attendance is not None and fc.attendance <= 50
    assert fc.analogs and len(fc.analogs) == 3
    assert db.get(m.Event, ev_id).status == "evaluated"
    assert head.form(f"{page}/status", {"to": "approved", "comment": "Летим"}, page).status_code == 303
    assert head.form(f"{page}/status", {"to": "on_sale"}, page).status_code == 303
    code = db.get(m.Event, ev_id).code
    assert client.get(f"/e/{code}").status_code == 200

    # 5. импорт продаж Timepad и анкета гостя
    csv_text = "Номер заказа;Имя;E-mail;Сумма;Статус\n101;Аня;anya@x.ru;800;Оплачен\n102;Боря;bor@x.ru;800;Оплачен\n"
    files = {"file": ("orders.csv", csv_text.encode(), "text/csv")}
    assert head.form(f"{page}/tickets/import", {}, page, files=files).status_code == 303
    head.form(f"{page}/tickets/import", {}, page, files={"file": ("o.csv", csv_text.encode(), "text/csv")})
    db.expire_all()
    assert len(db.scalars(select(m.Ticket).where(m.Ticket.event_id == ev_id)).all()) == 2   # без дублей
    fb_page = f"/e/{code}/feedback"
    r = client.form(fb_page, {"rating": "5", "nps": "9", "email": "anya@x.ru", f"st_{station_ids[0]}": "5"}, fb_page)
    assert r.status_code == 303
    r2 = client.form(fb_page, {"rating": "1"}, fb_page)
    assert "thanks" not in r2.headers["location"]                                          # повтор отклонён

    # 6. проведено → факт → разбор полёта, компетентность обновлена
    assert head.form(f"{page}/status", {"to": "held"}, page).status_code == 303
    before = {e.id: e.competence for e in experts}
    r = head.form(f"{page}/result", {"guests_count": "44", "tickets_sold": "45", "revenue": "36000",
                                     "actual_cost": "9800", "avg_rating": "4.6", "finalize": "1"}, page)
    assert r.status_code == 303
    db.expire_all()
    assert db.get(m.Event, ev_id).status == "analyzed"
    hist = db.scalars(select(m.CompetenceHistory).where(m.CompetenceHistory.event_id == ev_id)).all()
    assert len(hist) == 4
    assert any(abs(db.get(m.Expert, e).competence - c0) > 1e-9 for e, c0 in before.items())


def test_bot_api(client, db):
    assert client.get("/api/bot/events").status_code == 401
    # привязка аккаунта
    c = Client(app).__enter__().login("tech@energy.local")
    c.form("/cabinet/profile/link-code", {}, "/cabinet/profile")
    user = db.scalar(select(m.User).where(m.User.email == "tech@energy.local"))
    code = db.scalar(select(m.LinkCode).where(m.LinkCode.user_id == user.id)).code
    r = client.post("/api/bot/link", json={"channel": "telegram", "user_id": "555", "code": code}, headers=BOT)
    assert r.status_code == 200 and r.json()["full_name"] == "Техник Lab"
    assert client.post("/api/bot/link", json={"channel": "telegram", "user_id": "555", "code": code},
                       headers=BOT).status_code == 400                                     # одноразовый код
    # задачи
    tasks = client.get("/api/bot/tasks", params={"channel": "telegram", "user_id": "555"}, headers=BOT).json()["tasks"]
    assert tasks and tasks[0]["title"]
    r = client.post(f"/api/bot/tasks/{tasks[0]['id']}/status",
                    json={"channel": "telegram", "user_id": "555", "status": "done"}, headers=BOT)
    assert r.json()["status_name"] == "Готово"
    # вопрос на обсуждение в отдел
    r = client.post("/api/bot/discussions", json={"channel": "telegram", "user_id": "555", "department_code": "TECH",
                                                  "title": "Нужен второй проектор?", "text": "Для зала реликвии"},
                    headers=BOT)
    assert r.status_code == 200
    lst = client.get("/api/bot/discussions", params={"channel": "telegram", "user_id": "555"}, headers=BOT).json()
    assert lst["department"] == "TECH" and any(d["title"] == "Нужен второй проектор?" for d in lst["discussions"])
    # непривязанный пользователь
    r = client.get("/api/bot/tasks", params={"channel": "vk", "user_id": "999"}, headers=BOT)
    assert r.status_code == 404
    # SOS не попадает на доску и возвращает дежурных
    r = client.post("/api/bot/sos", json={"channel": "vk", "user_id": "777", "text": "Плохо гостю"}, headers=BOT)
    assert r.status_code == 200 and "112" in r.json()["reply"]
    assert "Плохо гостю" not in client.get("/board").text
    # очередь уведомлений: задача привязанному пользователю → уведомление в его Telegram
    head = Client(app).__enter__().login(*HEAD)
    head.form("/cabinet/tasks", {"title": "Проверить проектор", "assignee_id": str(user.id)}, "/cabinet/tasks")
    items = client.get("/api/bot/notifications", headers=BOT).json()["items"]
    assert any(i["chat_id"] == "555" and "Проверить проектор" in i["text"] for i in items)
    assert client.post(f"/api/bot/notifications/{items[0]['id']}/sent", headers=BOT).json()["ok"]
    # ограничение частоты вопросов
    for i in range(5):
        client.post("/api/bot/questions", json={"channel": "vk", "user_id": "42", "text": f"вопрос {i}"}, headers=BOT)
    r = client.post("/api/bot/questions", json={"channel": "vk", "user_id": "42", "text": "ещё"}, headers=BOT)
    assert r.status_code == 429
