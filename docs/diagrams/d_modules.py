from vstyle import figure, save, box, label, arrow, legend, PAL, LINE
from matplotlib.patches import Circle

fig, ax = figure(16.5, 12.8)
def frame(x, y, w, h, title, col):
    box(ax, x, y, w, h, color=col, fill=False, r=0.15, lw=1.0, ls=(0, (4, 2)))
    label(ax, x + 0.15, y + h - 0.25, title, ha="left", bold=True, fs=7.0, color=PAL[col][1], bg="white", z=9)
A = lambda pts, **k: arrow(ax, pts, z=8, **k)
def num(x, y, n, col=LINE):
    ax.add_patch(Circle((x, y), 0.17, fc=col, ec="white", lw=0.8, zorder=10))
    ax.text(x, y - 0.01, str(n), ha="center", va="center", fontsize=6, color="white", fontweight="bold", zorder=11)
GRAY = "#8A93A6"
TOP, H = 12.7, 7.4
Y0 = TOP - H
# маршрутизаторы
frame(0.1, Y0, 3.6, H, "Маршрутизаторы", "blue")
R = {}
for i, (k, t) in enumerate([("exp", "expertise.py\nлист оценки, тур"), ("eval", "evaluation.py\nсводка, прогноз, решение"),
                            ("cab", "cabinet.py\nразбор полёта"), ("pub", "public.py\nанкета гостя"),
                            ("bot", "api_bot.py\nанкета в боте")]):
    y = TOP - 1.65 - i * 1.4
    box(ax, 0.35, y, 3.1, 1.15, t, "blue", fs=6.2)
    R[k] = (y, y + 0.575)
# сервисный слой
frame(4.1, Y0, 4.4, H, "Сервисный слой", "purple")
box(ax, 4.35, 8.55, 3.9, 3.5, "", "purple", lw=1.4)
label(ax, 6.3, 11.78, "service.py", fs=7, bold=True)
for i, t in enumerate(["summary() — S, V, W, R, Q", "round_medians() — медиана, IQR", "close_round() — итог тура",
                       "build_forecast() — прогноз", "update_competence() — веса"]):
    label(ax, 4.5, 11.3 - i * 0.55, "• " + t, ha="left", fs=6.0)
box(ax, 4.35, 5.55, 3.9, 2.7, "", "purple", lw=1.4)
label(ax, 6.3, 7.98, "review.py", fs=7, bold=True)
for i, t in enumerate(["build() — план, прогноз, факт", "V гостей по блокам, NPS", "accuracy() — точность"]):
    label(ax, 4.5, 7.5 - i * 0.55, "• " + t, ha="left", fs=6.0)
# расчётные модули
frame(8.9, Y0, 4.1, H, "Расчётные модули (без БД)", "green")
C = {}
for i, (k, t) in enumerate([("sc", "scoring\nweighted_mean, variation,\nagreement"), ("de", "delphi\nkendall_w, median_iqr,\nneeds_second_round"),
                            ("ri", "risk\nlevel, zone, event_risk"), ("fo", "forecast\ndistance, predict,\nrecommend"),
                            ("co", "competence\nupdate")]):
    y = TOP - 1.65 - i * 1.4
    box(ax, 9.65, y, 3.15, 1.15, t, "green", fs=5.9)
    C[k] = y + 0.575
# конфигурация
frame(13.4, Y0, 3.0, H, "Конфигурация", "orange")
box(ax, 13.6, 8.6, 2.6, 3.3, "config.METHOD\n\nscale_max = 10\ncv_zones = 20, 33\nrisk_zones = 24, 56\nw_threshold = 0,5\nreject < 5,5\nrework < 6,5", "orange", fs=6.0)
box(ax, 13.6, 5.55, 2.6, 2.7, "Веса отделов\nи критериев,\nk аналогов,\nη = 0,2", "orange", fs=6.0)
# данные
frame(0.1, 2.75, 16.3, 2.1, "Данные: ORM SQLAlchemy → PostgreSQL", "gray")
D = {}
for i, (k, t) in enumerate([("fb", "event_results\nfeedback_stations"), ("ev", "evaluations\nrisk_assessments"),
                            ("rd", "expertise_rounds\nevent_experts"), ("fc", "forecasts\ndecisions"),
                            ("ex", "experts\ncompetence_history")]):
    x = 0.35 + i * 3.23
    box(ax, x, 2.95, 2.95, 1.2, t, "white", fs=6.0)
    D[k] = x + 1.475
# связи: маршрутизаторы → сервис
A([(3.45, R["exp"][1]), (4.35, R["exp"][1])]); num(3.9, R["exp"][1] + 0.22, 1)
A([(3.45, R["eval"][1]), (4.35, R["eval"][1])]); num(3.9, R["eval"][1] + 0.22, 2)
A([(3.45, R["cab"][1]), (3.9, R["cab"][1]), (3.9, 6.9), (4.35, 6.9)]); num(3.9, R["cab"][1] + 0.22, 3)
A([(3.45, R["pub"][1]), (3.95, R["pub"][1]), (3.95, 4.55), (D["fb"], 4.55), (D["fb"], 4.15)], color=GRAY)
A([(3.45, R["bot"][1]), (3.95, R["bot"][1])], color=GRAY, head=False); num(4.18, R["pub"][1] - 0.6, 4, GRAY)
# сервис → расчёт: шина
bus = 9.3
ax.plot([bus, bus], [C["co"], C["sc"]], color=PAL["purple"][1], lw=1.4, zorder=7)
A([(8.25, 10.3), (bus, 10.3)], color=PAL["purple"][1], lw=1.4, head=False)
A([(8.25, 6.9), (bus, 6.9)], color=PAL["purple"][1], lw=1.4, head=False)
for k in C:
    A([(bus, C[k]), (9.65, C[k])], color=PAL["purple"][1])
num(8.75, 10.55, 5, PAL["purple"][1])
# конфигурация → расчёт
A([(13.6, 10.25), (12.8, 10.25)], color=PAL["orange"][1], ls=(0, (3, 2)))
A([(13.6, 6.9), (12.8, 6.9)], color=PAL["orange"][1], ls=(0, (3, 2)))
# сервис ↔ данные
for x in (4.8, 5.6, 6.4, 7.2):
    pass
A([(5.0, 5.55), (5.0, 4.15)], color=GRAY); A([(7.0, 5.55), (7.0, 4.15)], color=GRAY)
A([(7.6, 5.55), (7.6, 5.0), (D["fc"], 5.0), (D["fc"], 4.15)], color=GRAY)
A([(7.9, 5.55), (7.9, 5.15), (D["ex"], 5.15), (D["ex"], 4.15)], color=GRAY)

legend(ax, 0.1, 0.05, [(lambda a, x, y: arrow(a, [(x - 0.35, y), (x + 0.35, y)], color=PAL["purple"][1]),
                        "вызов расчётной функции"),
                       (lambda a, x, y: arrow(a, [(x - 0.35, y), (x + 0.35, y)], color=GRAY), "чтение / запись БД"),
                       (lambda a, x, y: arrow(a, [(x - 0.35, y), (x + 0.35, y)], color=PAL["orange"][1],
                                              ls=(0, (3, 2))), "параметры методики")], w=5.4, row=0.5)
items = ["1  эксперт сохраняет лист; закрытие тура → summary(), needs_second_round()",
         "2  руководитель открывает сводку → summary(), build_forecast() → recommend()",
         "3  разбор полёта → review.build(), update_competence()",
         "4  анкеты гостей пишутся в feedback_stations без расчётов",
         "5  сервис передаёт расчётным модулям только числа, БД им недоступна"]
box(ax, 5.7, 0.05, 10.7, 2.5, color="gray", fill=False, r=0.08, lw=0.8)
label(ax, 5.85, 2.3, "Сценарии взаимодействия", ha="left", bold=True, fs=7)
for i, t in enumerate(items):
    label(ax, 5.85, 1.88 - i * 0.4, t, ha="left", fs=6.1)
save(fig, "png/modules.png")
