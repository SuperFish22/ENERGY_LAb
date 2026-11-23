"""Рисует диаграммы IDEF0 по текстовому описанию (JSON). Запуск: python idef0.py spec.json out.png"""
import json, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch
plt.rcParams["font.family"] = "Liberation Serif"

def arrow(ax, p, q, lw=1.3):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=14, lw=lw, color="black", shrinkA=0, shrinkB=0))

def poly(ax, pts):
    for a, b in zip(pts[:-2], pts[1:-1]):
        ax.plot([a[0], b[0]], [a[1], b[1]], color="black", lw=1.3)
    arrow(ax, pts[-2], pts[-1])

def legend(ax, x, y, extra=(), w=4.6):
    """Легенда нотации IDEF0 в правом нижнем углу."""
    rows = [("box", "Функция (блок) с номером"), ("in", "Вход – что преобразуется"), ("ctl", "Управление – чем регулируется"),
            ("mech", "Механизм – кто или что выполняет"), ("out", "Выход – результат")] + list(extra)
    h = .42 * len(rows) + .6
    ax.add_patch(Rectangle((x, y), w, h, fill=False, lw=1))
    ax.text(x + .15, y + h - .15, "Обозначения", ha="left", va="top", fontsize=11, fontweight="bold")
    for i, (k, t) in enumerate(rows):
        yy = y + h - .75 - .42 * i
        if k == "box":
            ax.add_patch(Rectangle((x + .2, yy - .14), .7, .3, fill=False, lw=1.5))
        elif k in ("in", "out"):
            arrow(ax, (x + .15, yy), (x + .95, yy), lw=1.1)
        elif k == "ctl":
            arrow(ax, (x + .55, yy + .2), (x + .55, yy - .16), lw=1.1)
        elif k == "mech":
            arrow(ax, (x + .55, yy - .2), (x + .55, yy + .16), lw=1.1)
        ax.text(x + 1.1, yy, t, ha="left", va="center", fontsize=10)


def context(spec, out):
    fig, ax = plt.subplots(figsize=(14.5 * .64, 10.8 * .64)); ax.set_xlim(0, 14.5); ax.set_ylim(-2.8, 8); ax.axis("off")
    x0, y0, w, h = 3.9, 2.7, 5.2, 2.5
    ax.add_patch(Rectangle((x0, y0), w, h, fill=False, lw=2.2))
    ax.text(x0 + w/2, y0 + h/2 + .1, spec["title"], ha="center", va="center", fontsize=14)
    ax.text(x0 + w - .15, y0 + .15, spec.get("node", "A0"), ha="right", va="bottom", fontsize=12)
    def spread(n, a, b): return [a + (b - a) * (i + 1) / (n + 1) for i in range(n)]
    for y, t in zip(spread(len(spec["inputs"]), y0 + h, y0), spec["inputs"]):
        arrow(ax, (1.6, y), (x0, y)); ax.text(1.5, y, t, ha="right", va="center", fontsize=12)
    for y, t in zip(spread(len(spec["outputs"]), y0 + h, y0), spec["outputs"]):
        arrow(ax, (x0 + w, y), (10.6, y)); ax.text(10.7, y, t, ha="left", va="center", fontsize=12)
    n = len(spec["controls"])
    for k, (x, t) in enumerate(zip(spread(n, x0, x0 + w), spec["controls"])):
        mid = 0 < k < n - 1
        top = 6.7 if mid else 6.0
        ha = "center" if mid else ("right" if k == 0 else "left")
        dx = {"center": 0, "right": .05, "left": -.05}[ha]
        arrow(ax, (x, top), (x, y0 + h)); ax.text(x + dx, top + .08, t, ha=ha, va="bottom", fontsize=12)
    n = len(spec["mechanisms"])
    for k, (x, t) in enumerate(zip(spread(n, x0, x0 + w), spec["mechanisms"])):
        left = k < n / 2
        outer = k == 0 or k == n - 1
        bot = 1.6 if outer else 0.9
        ha = "right" if left else "left"
        dx = .05 if left else -.05
        arrow(ax, (x, bot), (x, y0)); ax.text(x + dx, bot - .08, t, ha=ha, va="top", fontsize=12)
    legend(ax, 8.9, -2.7, w=5.7)
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")

def decomposition(spec, out):
    blocks = spec["blocks"]; n = len(blocks)
    W, H = 23, 4 + 2.45 * n
    fig, ax = plt.subplots(figsize=((W + 2.6) * .5, H * .5)); ax.set_xlim(0, W + 2.6); ax.set_ylim(0, H); ax.axis("off")
    bw, bh = 3.3, 1.7; pos = []
    for i, b in enumerate(blocks):
        x = 3.4 + i * 4.0; y = H - 2.9 - i * 2.4
        pos.append((x, y)); ax.add_patch(Rectangle((x, y), bw, bh, fill=False, lw=2))
        ax.text(x + bw/2, y + bh/2 + .1, b["name"], ha="center", va="center", fontsize=10.5)
        ax.text(x + bw - .1, y + .08, f"A{i+1}", ha="right", va="bottom", fontsize=10)
        # управление сверху
        if b.get("control"):
            cx = x + bw * .5; arrow(ax, (cx, y + bh + .55), (cx, y + bh)); ax.text(cx, y + bh + .6, b["control"], ha="center", va="bottom", fontsize=10)
        if b.get("mechanism"):
            mx = x + bw * .5; arrow(ax, (mx, y - .5), (mx, y)); ax.text(mx, y - .55, b["mechanism"], ha="center", va="top", fontsize=10)
    # входы первого блока
    x, y = pos[0]
    for k, t in enumerate(spec["inputs"]):
        yy = y + bh * (.75 - .5 * k / max(len(spec["inputs"]) - 1, 1)); arrow(ax, (.2, yy), (x, yy)); ax.text(.2, yy + .08, t, ha="left", va="bottom", fontsize=10)
    # связи между блоками
    for i in range(n - 1):
        (x1, y1), (x2, y2) = pos[i], pos[i + 1]
        sy = y1 + bh * .3; tx = x2 + bw * .0
        poly(ax, [(x1 + bw, sy), (x2 - .45, sy), (x2 - .45, y2 + bh * .55), (x2, y2 + bh * .55)])
        ax.text(x1 + bw + .08, sy + .05, blocks[i]["out"], ha="left", va="bottom", fontsize=10)
    # выход последнего
    x, y = pos[-1]
    for k, t in enumerate(spec["outputs"]):
        yy = y + bh * (.7 - .4 * k); arrow(ax, (x + bw, yy), (x + bw + 1.2, yy)); ax.text(x + bw + 1.3, yy, t, ha="left", va="center", fontsize=10)
    # обратная связь
    if spec.get("feedback"):
        xl, yl = pos[-1]; xf, yf = pos[0]
        bottom = yl - 1.25
        poly(ax, [(xl + bw * .85, yl), (xl + bw * .85, bottom), (xf + bw * .2, bottom), (xf + bw * .2, yf)])
        ax.text((xf + xl) / 2 + 1, bottom + .1, spec["feedback"], ha="center", va="bottom", fontsize=10)
    legend(ax, .3, .2, w=6.6)
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")

if __name__ == "__main__":
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    (context if spec["type"] == "context" else decomposition)(spec, sys.argv[2])
