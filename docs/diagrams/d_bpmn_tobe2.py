from vstyle import figure, save, box, label, legend, PAL
from bpmn import *

fig, ax = figure(16.5, 9.4)
P = Pool(ax, 0.05, 2.85, 16.4, "Проведение и разбор",
         [("m", "Руково-\nдитель", "orange"), ("s", "Система", "green"), ("g", "Гости\n(сайт, бот)", "blue")],
         lane_h=2.15)
ym, ys, yg = P.cy("m"), P.cy("s"), P.cy("g")
st = event(ax, 1.85, ym, "start", "Проект\nутверждён")
t1 = task(ax, 3.25, ys, "Опубликовать\nафишу, открыть\nпродажу", color="green", marker="service", w=2.05)
t2 = task(ax, 5.3, ym, "Провести\nмероприятие", color="orange", marker="user", w=1.9)
p1 = gateway(ax, 6.95, ym, kind="+")
t3 = task(ax, 8.55, ym, "Внести факт:\nгости, билеты,\nвыручка, затраты", color="orange", marker="user", w=2.1)
ev = event(ax, 6.95, yg, "inter", inner="msg")
label(ax, 6.95, yg - 0.5, "Ссылка\nна анкету", fs=5.6)
t4 = task(ax, 8.55, yg, "Оценить блоки\nи мероприятие\nпо шкале 1–10", marker="user", w=2.1)
p2 = gateway(ax, 10.1, ys, kind="+")
t5 = task(ax, 11.8, ys, "Разбор: точность,\nV гостей по\nблокам, NPS", color="green", marker="service", w=2.25)
t6 = task(ax, 14.2, ys, "Обновить компе-\nтентность и базу\nаналогов", color="green", marker="service", w=2.25)
en = event(ax, 16.0, ys, "end")
label(ax, 16.0, ys + 0.62, "Опыт\nучтён", fs=5.6)
t7 = task(ax, 14.2, ym, "Записать выводы\nдля следующих\nпроектов", color="orange", marker="user", w=2.25)
db = data(ax, 13.1, yg, "БД: факт, анкеты,\nкомпетентность", store=True)

flow(ax, [st["r"], (3.25, ym), t1["t"]])
flow(ax, [t1["r"], (5.3, ys), t2["b"]])
flow(ax, [t2["r"], p1["l"]])
flow(ax, [p1["r"], t3["l"]])
flow(ax, [p1["b"], ev["t"]])
flow(ax, [ev["r"], t4["l"]])
flow(ax, [t3["r"], (10.1, ym), p2["t"]])
flow(ax, [t4["r"], (10.1, yg), p2["b"]])
flow(ax, [p2["r"], t5["l"]])
flow(ax, [t5["r"], t6["l"]])
flow(ax, [t6["r"], en["l"]])
flow(ax, [t5["t"], (11.8, ym), t7["l"]])
assoc(ax, t6["b"], db["t"])
assoc(ax, t7["b"], t6["t"])
assoc(ax, t4["r"], db["l"])

legend(ax, 0.05, 0.05, [(lg_start, "начальное / конечное событие"), (lg_inter, "событие-сообщение"),
                        (lg_task, "пользовательская задача")], w=5.3, row=0.55)
def lg_par(ax, cx, cy):
    from matplotlib.patches import Polygon
    ax.add_patch(Polygon([(cx, cy + 0.16), (cx + 0.16, cy), (cx, cy - 0.16), (cx - 0.16, cy)], closed=True,
                         fc=PAL["orange"][0], ec=PAL["orange"][1], lw=1.0, zorder=4))
    ax.plot([cx - .07, cx + .07], [cy, cy], color=PAL["orange"][1], lw=1, zorder=5)
    ax.plot([cx, cx], [cy - .07, cy + .07], color=PAL["orange"][1], lw=1, zorder=5)
legend(ax, 5.55, 0.05, [(lg_service, "сервисная задача (выполняет ИС)"), (lg_par, "параллельный шлюз (AND)"),
                        (lg_data, "объект данных / хранилище")], w=5.3, row=0.55, title=" ")
box(ax, 11.05, 0.05, 5.4, 2.15, color="green", fill=False, r=0.08, lw=0.8)
label(ax, 11.2, 1.97, "Что изменилось", ha="left", bold=True, fs=6.8)
for i, t in enumerate(["гости оценивают каждый блок", "V гостей — итоговая оценка блока",
                       "точность прогноза и экспертов", "компетентность обновляется сама"]):
    label(ax, 11.2, 1.55 - i * 0.4, "✓  " + t, ha="left", fs=6.3)
save(fig, "png/bpmn_tobe2.png")
