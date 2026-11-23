"""DFD в нотации Гейна–Сарсона: формирует 04_dfd.dot и PNG через graphviz."""
import subprocess

F = 'fontname="Liberation Serif"'


def proc(n, t):
    return (f'P{n} [shape=plain label=<<TABLE STYLE="ROUNDED" BORDER="2" CELLBORDER="0" CELLSPACING="0" CELLPADDING="5">'
            f'<TR><TD BORDER="1" SIDES="B"><B>{n}</B></TD></TR><TR><TD>{t}</TD></TR></TABLE>>];')


def store(n, t):
    return (f'D{n} [shape=plain label=<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="5">'
            f'<TR><TD SIDES="TBL" BGCOLOR="#eeeeee"><B>D{n}</B></TD><TD SIDES="TB">{t}</TD></TR></TABLE>>];')


def ext(k, t):
    return f'{k} [shape=box style="filled" fillcolor="#dddddd" penwidth=2 margin="0.15,0.1" label=<{t}>];'


nodes = [
    ext("U", "Участник Lab"), ext("E", "Эксперт"), ext("R", "Руководитель"), ext("G", "Гость /<BR/>покупатель"),
    proc(1, "Ведение проекта<BR/>и сценария"), proc(2, "Экспертная<BR/>оценка"), proc(3, "Прогноз,<BR/>рекомендация"),
    proc(4, "Продажа билетов<BR/>(Timepad)"), proc(5, "Итоговая оценка<BR/>(разбор полёта)"),
    proc(6, "Задачи и<BR/>уведомления"), proc(7, "Поддержка<BR/>и FAQ"),
    store(1, "Проекты, блоки сценария, документы"), store(2, "Туры, оценки, риски"),
    store(3, "Прогнозы и решения"), store(4, "Билеты, анкеты, факт"),
    store(5, "Задачи, уведомления"), store(6, "FAQ, диалоги поддержки"),
]
edges = [
    ("U", "P1", "концепция,\\nсценарий, смета"), ("P1", "D1", ""), ("D1", "P2", "карточка проекта"),
    ("E", "P2", "баллы, P и I"), ("P2", "D2", ""), ("D2", "P3", "S, W, R"), ("D4", "P3", "аналоги"),
    ("P3", "D3", ""), ("D3", "R", "прогноз,\\nрекомендация"), ("R", "P1", "решение"),
    ("G", "P4", "покупка, анкета"), ("P4", "D4", ""), ("D4", "P5", "гости, выручка,\\nзатраты, анкеты"),
    ("D3", "P5", "прогноз"), ("P5", "D4", ""), ("P5", "R", "точность прогноза,\\nкомпетентность"),
    ("R", "P6", "задача"), ("P6", "D5", ""), ("D5", "U", "уведомление\\n(сайт, Telegram)"),
    ("G", "P7", "вопрос в боте"), ("P7", "D6", ""), ("D6", "G", "ответ оператора,\\nподсказка FAQ"),
]
legend = '''L [shape=plain label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="6" CELLPADDING="4">
<TR><TD COLSPAN="2" ALIGN="LEFT"><B>Обозначения</B></TD></TR>
<TR><TD BORDER="2" BGCOLOR="#dddddd">Имя</TD><TD ALIGN="LEFT">внешняя сущность (источник или получатель данных)</TD></TR>
<TR><TD><TABLE STYLE="ROUNDED" BORDER="2" CELLBORDER="0" CELLSPACING="0"><TR><TD BORDER="1" SIDES="B">N</TD></TR><TR><TD>Процесс</TD></TR></TABLE></TD><TD ALIGN="LEFT">процесс с номером</TD></TR>
<TR><TD><TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0"><TR><TD SIDES="TBL" BGCOLOR="#eeeeee">Dn</TD><TD SIDES="TB">Хранилище</TD></TR></TABLE></TD><TD ALIGN="LEFT">накопитель данных с идентификатором</TD></TR>
<TR><TD>⟶</TD><TD ALIGN="LEFT">поток данных (подпись — передаваемые данные)</TD></TR>
</TABLE>>];'''
dot = ["digraph DFD {", "graph [rankdir=TB nodesep=0.35 ranksep=0.6 dpi=150 " + F + "];",
       "node [" + F + " fontsize=14];", "edge [" + F + " fontsize=12 arrowsize=0.8];"]
dot += nodes + [legend]
dot += [f'{a} -> {b} [label="{l}"];' if l else f"{a} -> {b};" for a, b, l in edges]
dot += ["{rank=sink; L}", "D6 -> L [style=invis];", "}"]
open("04_dfd.dot", "w").write("\n".join(dot))
subprocess.run(["dot", "-Tpng", "04_dfd.dot", "-o", "04_dfd.png"], check=True)
