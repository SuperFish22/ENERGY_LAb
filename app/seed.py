"""Начальное наполнение: роли, отделы, критерии, классификатор форматов, администратор.

Запуск: python -m app.seed            — справочники и администратор
        python -m app.seed --demo     — плюс демонстрационные проекты (ДЕМО-цифры, заменить реальными)
"""
import sys
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.security import hash_password

ROLES = list(m.ROLE_NAMES.items())

# Отделы, веса α и критерии (раздел 2.2 ВКР; отдел маркетинга переименован в СМИ)
DEPARTMENTS = [
    ("SC", "Сценарный", 0.25, [("SC-1", "Оригинальность идеи", 0.40), ("SC-2", "Драматургия и логика сюжета", 0.35),
                               ("SC-3", "Соответствие целевой аудитории", 0.25)]),
    ("DIR", "Режиссёрско-постановочный", 0.25, [("DIR-1", "Вовлечённость и интерактивность", 0.40),
                                                ("DIR-2", "Тайминг и темп", 0.30),
                                                ("DIR-3", "Реализуемость силами команды", 0.30)]),
    ("TECH", "Технический", 0.15, [("TECH-1", "Свет и звук", 0.40), ("TECH-2", "Сложность оборудования", 0.35),
                                   ("TECH-3", "Безопасность", 0.25)]),
    ("PROD", "Продюсерский", 0.20, [("PROD-1", "Соответствие бюджету", 0.40), ("PROD-2", "Площадка и логистика", 0.30),
                                    ("PROD-3", "Сроки и ресурсы", 0.30)]),
    ("SMI", "СМИ", 0.15, [("SMI-1", "Инфоповод и медийность", 0.40),
                          ("SMI-2", "Визуальный контент для фото и видео", 0.30),
                          ("SMI-3", "Потенциал охвата", 0.30)]),
]

FORMATS = [
    ("10", "Интеллектуальные", "Интеллектуальные (группа)"), ("11", "Интеллектуальные", "Квиз"),
    ("12", "Интеллектуальные", "Театрализованный квиз"),
    ("20", "Квестовые", "Квестовые (группа)"), ("21", "Квестовые", "Иммерсивный квест"),
    ("22", "Квестовые", "Ролевой квест"),
    ("30", "Игровые", "Игровые (группа)"), ("31", "Игровые", "Стратегическая ролевая игра"),
    ("40", "Развлекательные", "Развлекательные (группа)"), ("41", "Развлекательные", "Вечеринка с DJ-сетом"),
    ("42", "Развлекательные", "Тематическая тусовка"),
]


def seed_reference(db: Session) -> None:
    for code, name in ROLES:
        if not db.scalar(select(m.Role).where(m.Role.code == code)):
            db.add(m.Role(code=code, name=name))
    for code, name, w, crits in DEPARTMENTS:
        d = db.scalar(select(m.Department).where(m.Department.code == code))
        if not d:
            d = m.Department(code=code, name=name, weight=w)
            db.add(d)
            db.flush()
        for ccode, cname, cw in crits:
            if not db.scalar(select(m.Criterion).where(m.Criterion.code == ccode)):
                db.add(m.Criterion(department_id=d.id, code=ccode, name=cname, weight=cw))
    for code, group, name in FORMATS:
        if not db.scalar(select(m.EventFormat).where(m.EventFormat.code == code)):
            db.add(m.EventFormat(code=code, group_name=group, name=name))
    db.flush()
    admin = db.scalar(select(m.User).where(m.User.email == settings.admin_email))
    if not admin:
        admin = m.User(full_name="Администратор Lab", email=settings.admin_email,
                       password_hash=hash_password(settings.admin_password))
        admin.roles = list(db.scalars(select(m.Role).where(m.Role.code.in_(["head", "member", "expert"]))))
        db.add(admin)
        db.flush()
        sc = db.scalar(select(m.Department).where(m.Department.code == "SC"))
        db.add(m.Expert(user_id=admin.id, department_id=sc.id, competence=1.0))
    db.commit()


def _user(db, name, email, roles, dept=None, comp=0.7):
    u = db.scalar(select(m.User).where(m.User.email == email))
    if u:
        return u
    u = m.User(full_name=name, email=email, password_hash=hash_password("demo12345"))
    u.roles = list(db.scalars(select(m.Role).where(m.Role.code.in_(roles))))
    db.add(u)
    db.flush()
    if dept:
        d = db.scalar(select(m.Department).where(m.Department.code == dept))
        db.add(m.Expert(user_id=u.id, department_id=d.id, competence=comp))
    return u


DEMO_ART = [("#3b48dd", "#69ddd9"), ("#e5483b", "#ffb547"), ("#2c3878", "#4fd1a1"), ("#7b2ff7", "#ff7ab6")]


def _demo_cover(code: str, title: str, k: int, pal: tuple[str, str]) -> str:
    """Демо-обложка альбома (SVG), пока команда не загрузила настоящие фото."""
    import os
    import random
    from xml.sax.saxutils import escape
    rnd = random.Random(f"{code}{k}")
    a, b = pal
    dots = "".join(f'<circle cx="{rnd.randint(0, 800)}" cy="{rnd.randint(0, 600)}" r="{rnd.choice([2, 3, 5, 8])}" '
                   f'fill="#fff" opacity="{rnd.uniform(.25, .8):.2f}"/>' for _ in range(40))
    shapes = [f'<circle cx="{rnd.randint(450, 650)}" cy="{rnd.randint(180, 330)}" r="{rnd.randint(110, 170)}" '
              f'fill="{b}" opacity=".85"/><ellipse cx="560" cy="300" rx="260" ry="60" fill="none" stroke="#fff" '
              f'stroke-width="10" opacity=".6" transform="rotate(-14 560 300)"/>',
              "".join(f'<rect x="{rnd.randint(0, 780)}" y="{rnd.randint(0, 580)}" width="14" height="28" fill="'
                      f'{rnd.choice([a, b, "#fff"])}" transform="rotate({rnd.randint(0, 90)})" opacity=".8"/>'
                      for _ in range(36)),
              f'<path d="M0 600 L400 {rnd.randint(260, 360)} L800 600z" fill="{b}" opacity=".6"/>'
              f'<circle cx="{rnd.randint(150, 650)}" cy="140" r="60" fill="#fff" opacity=".85"/>'][k % 3]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600"><defs><linearGradient id="g" x1="0" y1="0" '
           f'x2="1" y2="1"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="#0f1638"/></linearGradient>'
           f'</defs><rect width="800" height="600" fill="url(#g)"/>{dots}{shapes}'
           f'<text x="40" y="540" font-family="Arial, sans-serif" font-size="44" font-weight="700" fill="#fff">'
           f'{escape(title)}</text><text x="40" y="575" font-family="Arial, sans-serif" font-size="20" fill="#fff" '
           f'opacity=".7">демо-обложка · загрузите фото в кабинете</text></svg>')
    folder = os.path.join(settings.media_dir, "demo")
    os.makedirs(folder, exist_ok=True)
    name = f"{code}-{k + 1}.svg"
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(svg)
    return f"demo/{name}"


def _demo_avatar(k: int, a: str, b: str) -> str:
    """Демо-портрет (силуэт) для слайдера команды, пока не загружены настоящие фото."""
    import os
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 500"><defs><linearGradient id="g" x1="0" y1="0" '
           f'x2="0" y2="1"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="#18214d"/></linearGradient>'
           f'</defs><rect width="400" height="500" fill="url(#g)"/><circle cx="310" cy="90" r="46" fill="{b}" '
           f'opacity=".7"/><circle cx="200" cy="215" r="82" fill="#f4f2ff" opacity=".92"/>'
           f'<path d="M58 500c8-118 70-178 142-178s134 60 142 178z" fill="#f4f2ff" opacity=".92"/>'
           f'<text x="200" y="478" text-anchor="middle" font-family="Arial, sans-serif" font-size="18" '
           f'fill="#18214d" opacity=".7">демо-фото</text></svg>')
    folder = os.path.join(settings.media_dir, "demo")
    os.makedirs(folder, exist_ok=True)
    name = f"team-{k}.svg"
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(svg)
    return f"demo/{name}"


def seed_demo(db: Session) -> None:
    """ДЕМО-данные для показа и тестов. Названия прошлых мероприятий реальные, цифры — условные."""
    if db.scalar(select(m.Event).where(m.Event.code == "LAB-2026-01")):
        return
    fmt = {f.code: f for f in db.scalars(select(m.EventFormat))}
    venue = m.Venue(name="Пространство ENERGY", address="Москва", capacity=60)
    camp = m.Venue(name="ДОЛ «Дружба»", address="Московская область", capacity=80)
    db.add_all([venue, camp])
    db.flush()
    users = [
        _user(db, "Олег Шведков", "oleg@energy.local", ["head", "member", "expert"], "DIR", 1.0),
        _user(db, "Катя", "katya@energy.local", ["head", "member", "expert"], "PROD", 1.0),
        _user(db, "Сценарист Lab", "script@energy.local", ["member", "expert"], "SC", 0.8),
        _user(db, "Техник Lab", "tech@energy.local", ["member", "expert"], "TECH", 0.8),
        _user(db, "СМИ Lab", "smi@energy.local", ["member", "expert"], "SMI", 0.8),
        _user(db, "Участник Lab", "member@energy.local", ["member"]),
    ]
    past = [  # код, название, формат, дата, площадка, цена, гости, продано, план, факт, рейтинг
        ("LAB-2026-01", "Велесовы тропы", "12", date(2026, 2, 22), venue, 500, 45, 45, 2000, 1985, 4.6),
        ("LAB-2026-02", "Не та сказка", "21", date(2026, 5, 1), camp, 0, 40, 40, 6000, 6400, 4.7),
        ("LAB-2026-03", "Алое восстание", "31", date(2026, 5, 2), camp, 0, 38, 38, 5000, 5300, 4.4),
        ("LAB-2026-04", "Секреты Ренессанса", "22", date(2026, 5, 16), venue, 0, 50, 50, 4000, 4300, 4.5),
    ]
    for code, title, f, d, v, price, guests, sold, plan, fact, rating in past:
        ev = m.Event(code=code, title=title, format_id=fmt[f].id, venue_id=v.id, author_id=users[0].id,
                     status="analyzed", planned_date=d, ticket_price=price, planned_budget=plan, capacity=v.capacity,
                     age_rating="16+", description="Проведённое мероприятие Energy Lab (ДЕМО-цифры).")
        db.add(ev)
        db.flush()
        db.add(m.EventResult(event_id=ev.id, guests_count=guests, tickets_sold=sold, revenue=price * sold,
                             actual_cost=fact, avg_rating=rating))
        db.add(m.Forecast(event_id=ev.id, expert_score=round(rating - 0.3, 2), recommendation="Утвердить"))
        pal = DEMO_ART[int(code[-2:]) % len(DEMO_ART)]
        for k in range(3):
            db.add(m.EventPhoto(event_id=ev.id, file=_demo_cover(code, title, k, pal), order_no=k, is_cover=k == 0,
                                caption=["Старт", "Станции", "Финал"][k]))
    upcoming = m.Event(code="LAB-2026-07", title="Ночь в музее", format_id=fmt["21"].id, venue_id=venue.id,
                       author_id=users[2].id, status="on_sale", planned_date=date.today() + timedelta(days=16),
                       start_time="19:00", ticket_price=1300, planned_budget=12500, capacity=60, age_rating="16+",
                       target_audience="Студенты и молодые специалисты 18–25 лет",
                       description="Иммерсивный квест: гости оказываются в музее после закрытия, где экспонаты "
                                   "оживают и просят помочь вернуть украденную реликвию.")
    draft = m.Event(code="LAB-2026-08", title="Новогодний квиз", format_id=fmt["11"].id, venue_id=venue.id,
                    author_id=users[5].id, status="review", planned_date=date(2026, 12, 20), start_time="18:00",
                    ticket_price=700, planned_budget=8000, capacity=60, age_rating="12+",
                    description="Командный квиз с новогодними раундами и музыкальной паузой.")
    party = m.Event(code="LAB-2026-09", title="Звёздная новогодняя вечеринка", format_id=fmt["41"].id,
                    venue_id=venue.id, author_id=users[1].id, status="approved", planned_date=date(2026, 12, 27),
                    start_time="20:00", ticket_price=900, planned_budget=9000, capacity=60, age_rating="18+",
                    description="DJ-сет, космический дресс-код и фотозона.")
    db.add_all([upcoming, draft, party])
    db.flush()
    for ev, stations in ((upcoming, [("Вход в музей", 15, 3000), ("Лаборатория алхимика", 25, 5500),
                                     ("Зал реликвии", 20, 4000)]),
                         (draft, [("Разминка", 15, 1000), ("Музыкальный раунд", 20, 3000), ("Финал", 20, 2000)])):
        for i, (t, dur, cost) in enumerate(stations, 1):
            db.add(m.Station(event_id=ev.id, order_no=i, title=t, duration_min=dur, cost=cost,
                             responsible_id=users[3].id))
    depts = {d.code: d for d in db.scalars(select(m.Department))}
    db.add_all([
        m.Task(event_id=upcoming.id, department_id=depts["TECH"].id, title="Проверить дым-генератор",
               assignee_id=users[3].id, author_id=users[0].id, due_date=date.today() + timedelta(days=5)),
        m.Task(event_id=upcoming.id, department_id=depts["SMI"].id, title="Анонс во ВКонтакте и Telegram-канале",
               assignee_id=users[4].id, author_id=users[1].id, status="in_progress",
               due_date=date.today() + timedelta(days=3)),
        m.Task(event_id=upcoming.id, department_id=depts["SC"].id, title="Финальная версия текста станции 2",
               assignee_id=users[2].id, author_id=users[0].id, due_date=date.today() + timedelta(days=7)),
    ])
    crew = [("Александр Рыбаков", "Руководитель Energy Lab", "SC", "Придумывает форматы и отвечает за цифровую часть"),
            ("Олег Шведков", "Руководитель, режиссёр", "DIR", "Ставит программы и держит темп всей тусовки"),
            ("Катя", "Руководитель, продюсер", "PROD", "Находит площадки, партнёров и собирает смету"),
            ("Сценарист Lab", "Сценарист", "SC", "Пишет легенды и тексты станций"),
            ("Техник Lab", "Свет и звук", "TECH", "Отвечает за технику и безопасность"),
            ("СМИ Lab", "Фото и анонсы", "SMI", "Снимает и собирает фотоальбом")]
    for k, (name, role, dcode, bio) in enumerate(crew):
        a, b = DEMO_ART[k % len(DEMO_ART)]
        db.add(m.TeamMember(full_name=name, role=role, department_id=depts[dcode].id, bio=bio, order_no=k,
                            photo=_demo_avatar(k + 1, a, b), is_public=True, consent=True))
    disc = m.Discussion(department_id=depts["TECH"].id, event_id=upcoming.id, title="Где взять второй дым-генератор?",
                        author_id=users[3].id, source="telegram")
    db.add(disc)
    db.flush()
    db.add(m.Message(discussion_id=disc.id, author_id=users[3].id, source="telegram",
                     text="Текущий работает нестабильно. Можем арендовать у «Форт 57»?"))
    db.commit()


def main() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_reference(db)
        if "--demo" in sys.argv:
            seed_demo(db)
    print("Справочники загружены" + (" + демо-данные" if "--demo" in sys.argv else ""))


if __name__ == "__main__":
    main()
