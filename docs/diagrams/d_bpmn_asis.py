from vstyle import figure, save, box, label, legend, PAL
from bpmn import *

fig, ax = figure(16.5, 11.6)
P = Pool(ax, 0.05, 4.35, 16.4, "Лаборатория Energy Lab (до внедрения ИС)",
         [("a", "Автор\nпроекта", "blue"), ("m", "Руководитель", "purple"), ("d", "Отделы\n(эксперты)", "green"),
          ("g", "Гости", "orange")], lane_h=1.8)
ya, ym, yd, yg = P.cy("a"), P.cy("m"), P.cy("d"), P.cy("g")
s = event(ax, 1.7, ya, "start", "Идея")
t1 = task(ax, 3.35, ya, "Описать идею\nв мессенджере", marker="user")
t2 = task(ax, 5.4, ym, "Переслать\nописание отделам", color="purple", marker="manual")
t3 = task(ax, 7.6, yd, "Обсудить проект\nв общем чате", color="green", marker="manual")
t4 = task(ax, 9.8, ym, "Собрать мнения,\nрешить «на глаз»", color="purple", marker="manual")
g = gateway(ax, 11.75, ym, "Одобрено?", tpos="below")
tr = task(ax, 11.75, ya, "Переписать\nописание", marker="user")
t6 = task(ax, 14.1, ym, "Провести\nмероприятие", color="purple", marker="manual")
t7 = task(ax, 14.1, yg, "Посетить; отзыв\nпо желанию", color="orange", marker="user")
e = event(ax, 16.0, yg, "end", "Итоги не\nразобраны")
d1 = data(ax, 5.6, yd, "Переписка\nв чате")

flow(ax, [s["r"], t1["l"]])
flow(ax, [t1["r"], (5.4 - 1.3, ya), (5.4 - 1.3, ym + 0.2), (t2["l"][0], ym + 0.2)])
flow(ax, [t2["r"], (7.6, ym), t3["t"]])
flow(ax, [t3["r"], (9.8, yd), t4["b"]])
flow(ax, [t4["r"], g["l"]])
flow(ax, [g["t"], tr["b"]], "нет", 12.05, ym + 0.75)
flow(ax, [tr["l"], (8.3, ya), (5.4, ya), t2["t"]])
flow(ax, [g["r"], t6["l"]], "да", 12.5, ym + 0.15)
flow(ax, [t6["b"], t7["t"]])
flow(ax, [t7["r"], e["l"]])
assoc(ax, t3["l"], d1["r"])

problem(ax, t1["t"][0] + 0.95, t1["t"][1] + 0.02, 1)
problem(ax, t3["t"][0] + 0.95, t3["t"][1] + 0.02, 2)
problem(ax, t4["t"][0] + 0.95, t4["t"][1] + 0.02, 3)
problem(ax, g["c"][0] + 0.38, g["c"][1] + 0.3, 4)
problem(ax, t7["t"][0] + 0.95, t7["t"][1] + 0.02, 5)

# слабые места
issues = ["нет единой формы: состав блоков, бюджет и риски не описаны",
          "нет шкалы: оценки словами, перевешивает мнение самого активного",
          "решение не обосновано числами и нигде не фиксируется",
          "нет критериев «да/нет» и прогноза посещаемости и выручки",
          "отзывы гостей не собираются, опыт не переходит в следующие проекты"]
box(ax, 6.55, 0.1, 9.9, 4.0, color="pink", fill=False, r=0.08, lw=0.8)
label(ax, 6.7, 3.85, "Слабые места процесса", ha="left", bold=True, fs=7)
for i, t in enumerate(issues):
    yy = 3.38 - i * 0.68
    problem(ax, 6.95, yy, i + 1)
    label(ax, 7.25, yy, t, ha="left", fs=6.5)
legend(ax, 0.05, 0.1, [(lg_start, "начальное / конечное событие"), (lg_task, "задача (ручная, пользовательская)"),
                       (lg_gw, "исключающий шлюз (XOR)"), (lg_flow, "поток управления"),
                       (lg_data, "объект данных / хранилище"), (lg_problem, "проблемное место")],
       w=6.3, row=0.56)
save(fig, "png/bpmn_asis.png")
