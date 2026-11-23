"""spec 005: вопросы и ответы вместо SOS, поддержка, соцсети, раздел «Оценка», разбор критериев."""
from datetime import datetime, timedelta

from sqlalchemy import select

from app import models as m
from app import site, support
from app.maintenance import purge
from tests.conftest import BOT, Client, app

HEAD = ("head@test.local", "head-password")


def _head():
    return Client(app).__enter__().login(*HEAD)


# ---------------------------------------------------------------- FAQ
def test_faq_public_page_and_admin_crud(client, db):
    page = client.get("/faq").text
    assert "Вопросы и ответы" in page and "Как купить билет?" in page and "SOS" not in page
    head = _head()
    r = head.form("/cabinet/admin/faq", {"question": "Есть ли парковка?", "answer": "Да, у входа.",
                                         "topic": "На мероприятии"}, "/cabinet/admin/faq")
    assert r.status_code == 303
    item = db.scalar(select(m.FaqItem).where(m.FaqItem.question == "Есть ли парковка?"))
    assert item and not item.is_published                                   # без галочки — черновик
    assert "Есть ли парковка?" not in client.get("/faq").text
    head.form(f"/cabinet/admin/faq/{item.id}", {"question": "Есть ли парковка?", "answer": "Да, у входа.",
                                                "topic": "На мероприятии", "is_published": "1"}, "/cabinet/admin/faq")
    assert "Есть ли парковка?" in client.get("/faq").text
    head.form(f"/cabinet/admin/faq/{item.id}", {"action": "up"}, "/cabinet/admin/faq")
    db.expire_all()
    items = support.faq_items(db, published_only=False)
    assert items.index(db.get(m.FaqItem, item.id)) == len(items) - 2
    r = head.form("/cabinet/admin/faq", {"question": "?", "answer": ""}, "/cabinet/admin/faq")
    assert r.status_code == 303 and r.headers["location"].endswith("#new")
    fid = item.id
    head.form(f"/cabinet/admin/faq/{fid}", {"action": "delete"}, "/cabinet/admin/faq")
    db.expunge_all()
    assert db.get(m.FaqItem, fid) is None
    # участник без роли не управляет FAQ
    member = Client(app).__enter__().login("member@energy.local")
    assert member.get("/cabinet/admin/faq").status_code == 403


def test_board_answer_moves_to_faq(client, db):
    q = m.Question(text="Можно ли прийти с собакой?", category="Мероприятия", status="pending")
    db.add(q)
    db.commit()
    op = Client(app).__enter__().login("support@energy.local")          # поддержка тоже модерирует доску
    r = op.form(f"/cabinet/admin/questions/{q.id}", {"action": "faq"}, "/cabinet/admin/questions")
    assert r.status_code == 303 and r.headers["location"] == "/cabinet/admin/questions"   # без ответа нельзя
    op.form(f"/cabinet/admin/questions/{q.id}", {"action": "answer", "answer": "Только с маленькой."},
            "/cabinet/admin/questions")
    r = op.form(f"/cabinet/admin/questions/{q.id}", {"action": "faq"}, "/cabinet/admin/questions")
    assert "/cabinet/admin/faq#f" in r.headers["location"]
    f = db.scalar(select(m.FaqItem).where(m.FaqItem.question_id == q.id))
    assert f.answer == "Только с маленькой." and f.topic == "Мероприятия" and not f.is_published
    op.form(f"/cabinet/admin/questions/{q.id}", {"action": "faq"}, "/cabinet/admin/questions")   # повтор — не дубль
    assert len(db.scalars(select(m.FaqItem).where(m.FaqItem.question_id == q.id)).all()) == 1
    assert "Уже в FAQ" in op.get("/cabinet/admin/questions?status=answered").text


def test_faq_search_matches_word_forms(db):
    found = support.faq_search(db, "как вернуть билеты?")
    assert found and "вернуть" in found[0].question
    assert support.faq_search(db, "") == [] and support.faq_search(db, "zzzz qqqq") == []


# ---------------------------------------------------------------- поддержка
def test_support_without_operators_goes_to_heads_and_closing(client, db):
    sup = db.scalar(select(m.Role).where(m.Role.code == "support"))
    holders = db.scalars(select(m.User).join(m.UserRole).where(m.UserRole.role_id == sup.id)).all()
    for u in holders:                                   # временно снимаем роль: обращения должны уйти руководителям
        u.roles = [r for r in u.roles if r.code != "support"]
    db.commit()
    try:
        r = client.post("/api/bot/support", json={"channel": "vk", "user_id": "88001", "name": "Пётр",
                                                  "text": "Сколько стоит выпускной на 30 человек?"}, headers=BOT)
        assert r.json()["new"]
        cid = r.json()["id"]
        inbox = db.scalars(select(m.InboxItem).where(m.InboxItem.link == f"/cabinet/support/{cid}")).all()
        heads = {u.id for u in support.operators(db)}
        assert inbox and {i.user_id for i in inbox} == heads and all(i.kind == "support" for i in inbox)
    finally:
        for u in holders:
            u.roles = u.roles + [sup]
        db.commit()
    head = _head()
    assert "Пётр" in head.get("/cabinet/support").text
    assert 'class="nav-count"' in head.get("/cabinet").text                 # счётчик открытых диалогов в меню
    head.form(f"/cabinet/support/{cid}/status", {"action": "close"}, "/cabinet/support")
    db.expire_all()
    assert db.get(m.SupportChat, cid).status == "closed"
    last = db.scalar(select(m.Notification).where(m.Notification.chat_id == "88001").order_by(m.Notification.id.desc()))
    assert "Диалог закрыт" in last.text and last.channel == "vk"
    # новое сообщение после закрытия — новый диалог
    r = client.post("/api/bot/support", json={"channel": "vk", "user_id": "88001", "text": "Ещё вопрос"}, headers=BOT)
    assert r.json()["new"] and r.json()["id"] != cid
    # обычный участник в поддержку не заходит
    assert Client(app).__enter__().login("member@energy.local").get("/cabinet/support").status_code == 403


def test_support_rate_limit_and_retention(client, db):
    for i in range(20):
        client.post("/api/bot/support", json={"channel": "telegram", "user_id": "99001", "text": f"сообщение {i}"},
                    headers=BOT)
    r = client.post("/api/bot/support", json={"channel": "telegram", "user_id": "99001", "text": "ещё"}, headers=BOT)
    assert r.status_code == 429
    chat = support.find_chat(db, "telegram", "99001")
    chat.status, chat.updated_at = "closed", datetime.now() - timedelta(days=200)
    db.commit()
    res = purge(db)
    assert res["support_chats_deleted"] >= 1
    assert not db.scalars(select(m.SupportMessage).where(m.SupportMessage.chat_id == chat.id)).all()


# ---------------------------------------------------------------- соцсети
def test_social_links_validation_and_display(client, db):
    assert site.social_url("telegram", "@energy_lab") == "https://t.me/energy_lab"
    assert site.social_url("vk", "vk.ru/planeta.energy") == "https://vk.ru/planeta.energy"
    assert site.social_url("youtube", "https://youtu.be/abc") == "https://youtu.be/abc"
    assert site.social_url("instagram", "https://evil.example/instagram.com") is None
    assert site.social_url("vk", "javascript:alert(1)") is None
    head = _head()
    r = head.form("/cabinet/admin/site/socials", {"vk": "https://vk.ru/planeta.energy", "telegram": "@energy_lab",
                                                  "instagram": "https://instagram.com/energy",
                                                  "youtube": "https://example.com/x", "bot": "@energy_lab_bot"},
                  "/cabinet/admin/site")
    assert r.status_code == 303
    saved = site.socials(db)
    assert saved["telegram"] == "https://t.me/energy_lab" and saved["youtube"] == "" and \
        saved["bot"] == "https://t.me/energy_lab_bot"
    home = client.get("/").text
    assert 'href="https://t.me/energy_lab"' in home and 'href="https://instagram.com/energy"' in home
    assert "признана экстремистской" in home                                 # пометка рядом с Instagram
    assert "https://t.me/energy_lab_bot" in client.get("/faq").text           # кнопка «Написать в Telegram»
    assert 'class="soc soc-bot' not in home                                   # бот — не иконка
    head.form("/cabinet/admin/site/socials", {"vk": "https://vk.ru/planeta.energy"}, "/cabinet/admin/site")
    assert "признана экстремистской" not in client.get("/afisha").text      # нет Instagram — нет и пометки


# ---------------------------------------------------------------- оценка отдельно от проекта
def test_evaluation_section_separate_from_project(client, db):
    head = _head()
    ev = db.scalar(select(m.Event).where(m.Event.status == "analyzed"))
    card = head.get(f"/cabinet/projects/{ev.id}").text
    tabs = card.split('aria-label="Разделы проекта"', 1)[1].split("</nav>", 1)[0]
    assert "Экспертиза" not in tabs and "Итоговая оценка" not in tabs and "Сценарий" in tabs and "Задачи" in tabs
    assert f'href="/cabinet/evaluation/{ev.id}"' in card
    # старые ссылки на вкладки оценки ведут в раздел «Оценка»
    r = head.get(f"/cabinet/projects/{ev.id}?tab=review", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/cabinet/evaluation/{ev.id}?tab=review"
    page = head.get(f"/cabinet/evaluation/{ev.id}?tab=review").text
    assert "План, прогноз и факт" in page and 'aria-label="Этапы оценки"' in page
    assert head.get(f"/cabinet/evaluation/{ev.id}?tab=scenario").status_code == 200   # чужая вкладка → экспертиза
    lst = head.get("/cabinet/evaluation").text
    assert ev.title in lst and "Как считается оценка" in lst
    assert ev.title in head.get("/cabinet/evaluation?stage=review").text
    assert ev.title not in head.get("/cabinet/evaluation?stage=expertise").text
    # участник видит только доступные проекты
    member = Client(app).__enter__().login("member@energy.local")
    draft = db.scalar(select(m.Event).where(m.Event.status == "review"))
    if draft and draft.author_id != db.scalar(select(m.User.id).where(m.User.email == "member@energy.local")):
        assert draft.title not in member.get("/cabinet/evaluation").text
        assert member.get(f"/cabinet/evaluation/{draft.id}").status_code == 403


def test_expert_sees_waiting_round(client, db):
    rnd = next((r for r in db.scalars(select(m.ExpertiseRound)) if r.is_open), None)
    if not rnd:
        return
    ev = db.get(m.Event, rnd.event_id)
    ex = db.scalar(select(m.Expert).join(m.EventExpert, m.EventExpert.expert_id == m.Expert.id)
                   .where(m.EventExpert.event_id == ev.id))
    web = Client(app).__enter__().login(ex.user.email)
    page = web.get("/cabinet/evaluation").text
    assert ev.title in page
    if f'/cabinet/projects/{ev.id}/evaluate' in page:
        assert "Ждут вашей оценки" in page


def test_how_explainer_uses_live_weights(client, db):
    head = _head()
    page = head.get("/cabinet/evaluation/how").text
    assert "1 / 9" in page and "9 / 9" in page and "evaluation-how.js" in page
    for d in db.scalars(select(m.Department)):
        assert d.name in page
    crit = db.scalar(select(m.Criterion).limit(1))
    assert crit.name in page
    assert 'data-green="24"' in page and 'data-yellow="56"' in page         # зоны риска из METHOD
    member = Client(app).__enter__().login("member@energy.local")
    assert member.get("/cabinet/evaluation/how").status_code == 200       # разбор доступен всей команде
