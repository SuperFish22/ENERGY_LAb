"""Сценарий по времени вместо станций (spec 002): тайминг, карусель, оцениваемые блоки, план и факт."""
from types import SimpleNamespace as NS

from sqlalchemy import select

from app import models as m
from app import scenario
from tests.conftest import Client, app

HEAD = ("head@test.local", "head-password")


def _b(id_, kind, dur, order, parent=None, rated=True, groups=None, transition=None, fact=None):
    return NS(id=id_, kind=kind, duration_min=dur, order_no=order, parent_id=parent, rated=rated, groups=groups,
              transition_min=transition, fact_min=fact)


def test_timeline_and_carousel_math():
    blocks = [_b(1, "service", 15, 1, rated=False), _b(2, "block", 10, 2),
              _b(3, "carousel", 0, 3, rated=False, groups=3, transition=3), _b(4, "block", 15, 4),
              _b(31, "station", 15, 1, parent=3), _b(32, "station", 25, 2, parent=3),
              _b(33, "station", 20, 3, parent=3)]
    rows, total = scenario.timeline(blocks)
    assert [r.start for r in rows] == [0, 15, 25, 106]
    assert rows[2].minutes == 3 * 25 + 2 * 3                    # станций × самая длинная + переходы
    assert total == 121 and [c.block.id for c in rows[2].children] == [31, 32, 33]
    assert [b.id for b in scenario.rated(blocks)] == [2, 31, 32, 33, 4]   # служебный и сама карусель не оцениваются
    assert scenario.clock("19:00", 121) == "21:01" and scenario.clock("23:30", 45) == "00:15"
    assert scenario.clock(None, 10) is None
    blocks[2].groups = 5
    assert "Групп (5) больше, чем станций (3)" in scenario.timeline(blocks)[0][2].warning
    assert scenario.fact_minutes(blocks) == (None, 0)
    blocks[0].fact_min, blocks[1].fact_min = 20, 12
    assert scenario.fact_minutes(blocks) == (32, 2)


def test_build_scenario_in_cabinet(db):
    head = Client(app).__enter__().login(*HEAD)
    ev = db.scalar(select(m.Event).where(m.Event.code == "LAB-2026-08"))
    page = f"/cabinet/projects/{ev.id}?tab=scenario"
    assert "Сценарий" in head.get(page).text
    assert head.get(f"/cabinet/projects/{ev.id}?tab=stations").status_code == 200       # старая ссылка работает
    url = f"/cabinet/projects/{ev.id}/stations"
    head.form(url, {"title": "Сбор гостей", "kind": "service", "duration_min": "10", "rated_field": "1"}, page)
    head.form(url, {"title": "Карусель раундов", "kind": "carousel", "groups": "2", "transition_min": "1",
                    "rated_field": "1", "rated": "1"}, page)
    db.expire_all()
    ev = db.get(m.Event, ev.id)
    car = next(b for b in ev.stations if b.kind == "carousel")
    service = next(b for b in ev.stations if b.title == "Сбор гостей")
    assert service.rated is False and car.rated is False and car.groups == 2
    head.form(url, {"title": "Стол загадок", "duration_min": "12", "parent_id": str(car.id)}, page)
    head.form(url, {"title": "Стол ребусов", "duration_min": "8", "parent_id": str(car.id)}, page)
    db.expire_all()
    ev = db.get(m.Event, ev.id)
    kids = [b for b in ev.stations if b.parent_id == car.id]
    assert {b.kind for b in kids} == {"station"} and all(b.rated for b in kids)
    assert [r.minutes for r in ev.scenario[0] if r.block.id == car.id] == [2 * 12 + 1]
    assert {k.id for k in kids} <= {b.id for b in ev.rated_stations}                     # станции — на экспертизу
    # слот площадки: не влезает
    head.form(f"/cabinet/projects/{ev.id}/timing", {"slot_min": "30"}, page)
    assert "не влезает в слот площадки" in head.get(page).text
    # снять «оценивать» у блока → он пропадает из экспертизы
    first = next(b for b in ev.stations if b.title == "Разминка")
    head.form(f"{url}/{first.id}", {"action": "save", "title": "Разминка", "duration_min": "15", "kind": "block",
                                    "rated_field": "1"}, page)
    db.expire_all()
    assert first.id not in {b.id for b in db.get(m.Event, ev.id).rated_stations}
    # удаление карусели удаляет и её станции
    car_id = car.id
    head.form(f"{url}/{car_id}", {"action": "delete"}, page)
    db.expire_all()
    assert not db.scalars(select(m.Station).where(m.Station.parent_id == car_id)).all()
    assert not db.get(m.Station, car_id)


def test_fact_timing_in_review(db):
    head = Client(app).__enter__().login(*HEAD)
    ev = db.scalar(select(m.Event).where(m.Event.code == "LAB-2026-04"))      # проанализированное мероприятие
    page = f"/cabinet/projects/{ev.id}?tab=scenario"
    for t, d in (("Сбор", "10"), ("Игра", "60")):                          # у прошедших демо-событий сценария нет
        head.form(f"/cabinet/projects/{ev.id}/stations", {"title": t, "duration_min": d}, page)
    db.expire_all()
    top = [r.block for r in db.get(m.Event, ev.id).scenario[0]]
    assert 'name="fact_' in head.get(page).text
    head.form(f"/cabinet/projects/{ev.id}/timing", {f"fact_{b.id}": str(b.duration_min + 5) for b in top}, page)
    rv = head.get(f"/cabinet/projects/{ev.id}?tab=review").text
    assert "Тайминг: план и факт" in rv and "Длительность" in rv and f"+{5 * len(top)}" in rv


def test_feedback_rates_only_rated_blocks(client, db):
    ev = db.scalar(select(m.Event).where(m.Event.code == "LAB-2026-07"))
    names = {b.title: b for b in ev.stations}
    assert "Сбор гостей и деление на группы" not in [b.title for b in ev.rated_stations]
    assert names["Зал реликвии"] in ev.rated_stations
    page = client.get("/e/LAB-2026-07").text
    assert "121 мин" in page and "станции: Вход в музей" in page
