from vstyle import figure, save, box, label, legend, PAL
from bpmn import *

fig, ax = figure(16.5, 10.9)
P = Pool(ax, 0.05, 2.85, 16.4, "Экспертиза проекта в ИС Energy Lab",
         [("a", "Автор\nпроекта", "blue"), ("s", "Система", "green"), ("e", "Эксперты\nотделов", "purple"),
          ("m", "Руково-\nдитель", "orange")], lane_h=2.0)
ya, ys, ye, ym = P.cy("a"), P.cy("s"), P.cy("e"), P.cy("m")
st = event(ax, 1.6, ya, "start", "Идея")
t1 = task(ax, 3.3, ya, "Заполнить\nкарточку, бюджет,\nблоки сценария", marker="user")
t2 = task(ax, 5.75, ys, "Проверить\nполноту, открыть\nтур, уведомить", color="green", marker="service")
t4 = task(ax, 7.95, ye, "Оценить блоки\n(1–10) и риски\n(P, I от 1 до 10)", color="purple", marker="user")
t5 = task(ax, 10.0, ys, "Рассчитать\nS, V, W и R = P·I", color="green", marker="service")
g1 = gateway(ax, 11.7, ys)
label(ax, 11.7, ys + 0.64, "W ≥ 0,5 и\nV ≤ 33 %?", fs=5.6)
t7 = task(ax, 13.45, ys, "Прогноз по\nаналогам (kNN),\nрекомендация", color="green", marker="service", w=2.1)
t8 = task(ax, 13.45, ym + 0.3, "Изучить\nзаключение,\nпринять решение", color="orange", marker="user", w=2.1)
g2 = gateway(ax, 15.1, ym + 0.3)
tr = task(ax, 14.65, ya, "Доработать\nпроект по\nзамечаниям", marker="user")
e1 = event(ax, 15.95, ym + 0.3, "end")
e2 = event(ax, 15.1, ym - 0.55, "end", "Отклонён", tpos="right")
label(ax, 16.38, ym + 0.3 + 0.45, "Утверждён", fs=5.6, ha="right")
db = data(ax, 10.45, ym + 0.05, "БД: оценки,\nриски, итоги", store=True)
d1 = data(ax, 6.1, ye - 0.1, "Лист\nоценки")

flow(ax, [st["r"], t1["l"]])
flow(ax, [t1["b"], (3.3, ys), t2["l"]])
flow(ax, [t2["r"], (7.95, ys), t4["t"]])
flow(ax, [t4["r"], (9.55, ye), (9.55, ys - 0.5)])
flow(ax, [t5["r"], g1["l"]])
flow(ax, [g1["b"], (11.7, ye - 0.75), (7.95, ye - 0.75), t4["b"]])
label(ax, 10.6, ye - 0.6, "нет: 2-й тур, видны медиана и IQR", fs=5.8, bg="white")
flow(ax, [g1["r"], t7["l"]], "да", 12.2, ys + 0.15)
flow(ax, [t7["b"], t8["t"]])
flow(ax, [t8["r"], g2["l"]])
flow(ax, [g2["r"], e1["l"]])
flow(ax, [g2["b"], e2["t"]])
flow(ax, [g2["t"], (15.1, ya - 0.5)])
label(ax, 15.1, ys + 0.75, "доработать", fs=5.8, bg="white")
flow(ax, [tr["l"], (5.75, ya), t2["t"]])
assoc(ax, t4["l"], d1["r"])
assoc(ax, (10.45, ys - 0.5), db["t"])

legend(ax, 0.05, 0.05, [(lg_start, "начальное / конечное событие"), (lg_task, "пользовательская задача"),
                        (lg_service, "сервисная задача (выполняет ИС)")], w=5.3, row=0.55)
legend(ax, 5.55, 0.05, [(lg_gw, "исключающий шлюз (XOR)"), (lg_flow, "поток управления"),
                        (lg_data, "объект данных / хранилище")], w=5.3, row=0.55, title=" ")
box(ax, 11.05, 0.05, 5.4, 2.15, color="green", fill=False, r=0.08, lw=0.8)
label(ax, 11.2, 1.97, "Что изменилось", ha="left", bold=True, fs=6.8)
for i, t in enumerate(["единая карточка и проверки полноты", "шкала 1–10 и веса компетентности",
                       "согласие экспертов: W и V", "решение по правилам и прогнозу"]):
    label(ax, 11.2, 1.55 - i * 0.4, "✓  " + t, ha="left", fs=6.3)
save(fig, "png/bpmn_tobe1.png")
