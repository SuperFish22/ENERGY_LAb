from vstyle import figure, save, box, label, arrow, legend, PAL, LINE

fig, ax = figure(16.5, 14.2)
def frame(x, y, w, h, title, col, ls=(0, (4, 2))):
    box(ax, x, y, w, h, color=col, fill=False, r=0.15, lw=1.0, ls=ls)
    label(ax, x + 0.15, y + h - 0.25, title, ha="left", bold=True, fs=7.0, color=PAL[col][1], bg="white", z=9)
def band(x, y, w, h, title):
    box(ax, x, y, w, h, color="gray", r=0.08, lw=0.6)
    label(ax, x + 0.12, y + h - 0.2, title, ha="left", fs=6.3, italic=True, color="#5A6274")

# клиенты
frame(0.1, 12.0, 7.3, 2.1, "Клиенты", "gray")
box(ax, 0.35, 12.2, 3.2, 1.4, "Браузер\n(сайт, кабинет, анкета)", "white", fs=6.6)
box(ax, 3.95, 12.2, 3.2, 1.4, "Мессенджер\n(чат с ботом)", "white", fs=6.6)
# внешние
frame(7.8, 12.0, 8.6, 2.1, "Внешние сервисы", "gray")
for i, t in enumerate(["API\nмессенджера", "Timepad\n(билеты, 54-ФЗ)", "GitHub Actions\n(проверки)"]):
    box(ax, 8.05 + i * 2.8, 12.2, 2.6, 1.4, t, "white", fs=6.3)

# сервер РФ
frame(0.1, 2.5, 11.6, 9.2, "Сервер в РФ — граница обработки ПДн (152-ФЗ), Docker", "blue", ls="-")
band(0.35, 9.55, 11.1, 1.75, "Уровень представления")
box(ax, 0.55, 9.7, 2.3, 1.25, "Nginx\nTLS, статика", "blue", fs=6.4)
box(ax, 3.15, 9.7, 8.1, 1.25, "", "blue")
label(ax, 7.2, 10.62, "Маршрутизаторы FastAPI + шаблоны Jinja2", fs=6.6, bold=True)
for i, t in enumerate(["public", "cabinet", "evaluation", "expertise", "support", "admin", "api_bot"]):
    box(ax, 3.3 + i * 1.13, 9.8, 1.05, 0.5, t, "white", fs=5.4, r=0.06)

band(0.35, 4.55, 11.1, 4.75, "Уровень бизнес-логики")
box(ax, 0.55, 4.75, 6.3, 4.1, "", "purple", lw=1.6)
label(ax, 3.7, 8.6, "Модуль оценивания (app/expertise)", fs=6.8, bold=True, color=PAL["purple"][1])
mods = [("scoring", "S, V, W"), ("delphi", "туры"), ("risk", "R = P·I, Q"),
        ("forecast", "kNN, правила"), ("competence", "веса cᵢ"), ("review", "итог, V гостей")]
for i, (m, d) in enumerate(mods):
    cx, cy = 0.75 + (i % 3) * 2.0, 7.15 - (i // 3) * 1.25
    box(ax, cx, cy, 1.85, 1.05, f"{m}\n{d}", "white", fs=6.2, r=0.08)
box(ax, 0.75, 4.9, 5.85, 0.75, "service — сборка данных из БД и вызов расчётов", "purple", fs=6.2, r=0.08)
others = [("Проекты", "scenario, pricing"), ("Задачи", "tasks_board"), ("Поддержка", "support, FAQ"),
          ("Уведомления", "notify"), ("Сайт и медиа", "site, media"), ("Безопасность", "security, deps")]
for i, (t, d) in enumerate(others):
    cx, cy = 7.1 + (i % 2) * 2.15, 7.45 - (i // 2) * 1.2
    box(ax, cx, cy, 2.0, 1.0, f"{t}\n{d}", "green", fs=6.0, r=0.08)

band(0.35, 2.7, 11.1, 1.65, "Уровень данных")
box(ax, 0.55, 2.85, 3.6, 1.05, "ORM SQLAlchemy\nмиграции Alembic", "white", fs=6.3)
box(ax, 4.45, 2.85, 2.6, 1.05, "PostgreSQL 16", "purple", fs=6.6, bold=True)
box(ax, 7.35, 2.85, 2.0, 1.05, "Файлы\nmedia, files", "white", fs=6.2)
box(ax, 9.6, 2.85, 1.7, 1.05, "cron:\nкопии, очистка", "white", fs=6.0)

# внешний сервер
frame(12.0, 6.2, 4.4, 5.5, "Внешний сервер (без ПДн)", "orange", ls="-")
box(ax, 12.25, 9.3, 3.9, 1.5, "Бот\nдиалоги, анкеты,\nуведомления", "orange", fs=6.4)
box(ax, 12.25, 7.0, 3.9, 1.5, "n8n\nвыгрузка отчётов", "orange", fs=6.4)

A = lambda pts, **k: arrow(ax, pts, z=8, **k)
A([(1.95, 12.2), (1.95, 10.95)]); label(ax, 2.05, 11.86, "HTTPS", fs=5.8, ha="left")
A([(2.85, 10.32), (3.15, 10.32)])
A([(5.55, 12.2), (5.55, 11.75), (13.2, 11.75), (13.2, 10.8)], color="#8A93A6")
label(ax, 7.6, 11.87, "сообщения через API мессенджера", fs=5.6, italic=True)
A([(12.25, 10.05), (11.25, 10.05)]); label(ax, 11.75, 10.4, "HTTPS\n/api/bot", fs=5.6)
A([(12.25, 7.75), (11.7, 7.75), (11.7, 9.7)], color="#8A93A6")
A([(9.35, 12.2), (9.35, 11.75)], color="#8A93A6", head=False)
A([(7.2, 9.7), (7.2, 9.3)], lw=1.4, ms=9)
label(ax, 7.3, 9.48, "вызовы функций", fs=5.8, ha="left")
A([(3.7, 4.75), (3.7, 3.9)], lw=1.4, ms=9); A([(9.2, 4.55), (9.2, 4.2), (5.8, 4.2), (5.8, 3.9)], lw=1.0)
A([(4.15, 3.37), (4.45, 3.37)])
A([(14.2, 7.0), (14.2, 5.5)], color="#8A93A6"); box(ax, 12.25, 4.6, 3.9, 0.9, "Google Таблицы", "white", fs=6.2)
A([(15.75, 12.2), (15.75, 11.9), (16.35, 11.9), (16.35, 2.0), (6.0, 2.0), (6.0, 2.5)], color="#8A93A6", ls=(0, (3, 2)))
label(ax, 12.0, 1.85, "выкладка по SSH после проверок", fs=5.8, italic=True)

legend(ax, 0.1, 0.05, [(lambda a, x, y: box(a, x - 0.3, y - 0.13, 0.6, 0.26, color="purple", r=0.05),
                        "ядро: система оценивания"),
                       (lambda a, x, y: box(a, x - 0.3, y - 0.13, 0.6, 0.26, color="green", r=0.05),
                        "прочие модули бизнес-логики")], w=5.4, row=0.5)
legend(ax, 5.7, 0.05, [(lambda a, x, y: arrow(a, [(x - 0.35, y), (x + 0.35, y)]), "вызов / запрос"),
                       (lambda a, x, y: arrow(a, [(x - 0.35, y), (x + 0.35, y)], ls=(0, (3, 2))), "выкладка (CI/CD)")],
       w=5.0, row=0.5, title=" ")
save(fig, "png/architecture.png")
