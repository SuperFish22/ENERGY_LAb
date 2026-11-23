"""Физическая модель БД: четыре рисунка по предметным областям (12a–12d_er_*.puml).
Запуск из корня репозитория: python docs/diagrams/er_from_models.py [каталог_вывода]"""
import os
import sys

sys.path.insert(0, os.getcwd())
import app.models  # noqa: E402,F401
from app.db import Base  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
T = Base.metadata.tables
GROUPS = [
    ("12a_er_users.puml", ["roles", "user_roles", "users", "departments", "experts", "competence_history",
                           "team_members", "link_codes", "calendar_feeds"]),
    ("12b_er_expertise.puml", ["event_formats", "venues", "events", "stations", "criteria", "event_experts",
                               "expertise_rounds", "evaluations", "risk_assessments", "attachments",
                               "event_photos"]),
    ("12c_er_sales.puml", ["forecasts", "decisions", "event_results", "tickets", "feedback", "feedback_stations",
                           "party_requests"]),
    ("12d_er_tasks.puml", ["tasks", "task_events", "notifications", "inbox", "discussions", "messages",
                           "questions", "faq", "support_chats", "support_messages", "audit_log", "site_settings"]),
]
# скрытые связи, чтобы рисунок помещался по ширине страницы
LAYOUT = {"12d_er_tasks.puml": ["support_messages -[hidden]down-> notifications", "faq -[hidden]down-> site_settings",
                                "messages -[hidden]down-> audit_log"]}
LEGEND = """legend bottom left
  <b>Обозначения</b>
  | прямоугольник | таблица: над чертой первичный ключ, под чертой остальные столбцы |
  | серый прямоугольник только с ключом | таблица из другого рисунка физической модели |
  | <<PK>> | первичный ключ |
  | <<FK>> | внешний ключ |
  | <<UK>> | уникальное значение |
  | две черты — вилка с кружком | связь «один ко многим» (ноль или много записей) |
endlegend"""


def typ(c):
    return str(c.type).replace("INTEGER", "INT").replace("DATETIME", "TIMESTAMP")


def ent(name):
    t = T[name]
    out = [f"entity {name} {{"]
    for c in t.columns:
        if c.primary_key:
            out.append(f"  *{c.name} : {typ(c)} <<PK>>{' <<FK>>' if c.foreign_keys else ''}")
    out.append("  --")
    for c in t.columns:
        if not c.primary_key:
            tag = " <<FK>>" if c.foreign_keys else (" <<UK>>" if c.unique else "")
            out.append(f"  {c.name} : {typ(c)}{tag}")
    return "\n".join(out + ["}"])


def write(fn, names):
    ext = sorted({fk.column.table.name for n in names for fk in T[n].foreign_keys} - set(names))
    allnames = set(names) | set(ext)
    rels = sorted({f"{fk.column.table.name} ||--o{{ {n}" for n in names
                   for fk in T[n].foreign_keys if fk.column.table.name in allnames})
    stubs = "\n".join(f"entity {n} #DDDDDD {{\n  *id : INT <<PK>>\n}}" for n in ext)
    with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
        f.write("@startuml\n!include _style.iuml\nskinparam defaultFontSize 13\nskinparam monochrome false\n"
                "skinparam ClassBackgroundColor white\nskinparam ClassBorderColor black\nhide circle\nhide methods\n"
                "skinparam linetype ortho\n" + "\n".join(ent(n) for n in names) + "\n" + stubs + "\n"
                + "\n".join(rels + LAYOUT.get(fn, [])) + "\n" + LEGEND + "\n@enduml\n")


covered = [n for _, g in GROUPS for n in g]
missing = sorted(set(T) - set(covered))
assert not missing, f"таблицы без рисунка: {missing}"
for fn, names in GROUPS:
    write(fn, names)
print(len(T), "таблиц в", len(GROUPS), "рисунках")
