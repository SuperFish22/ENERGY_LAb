"""Мини-рендерер BPMN 2.0: пул с дорожками, задачи, события, шлюзы, потоки, объекты данных, аннотации."""
from matplotlib.patches import Circle, Polygon, FancyBboxPatch, Rectangle
from vstyle import PAL, INK, LINE, box, arrow, label

TW, TH = 2.25, 1.0  # размер задачи, см
ER = 0.22  # радиус события
GR = 0.3  # полудиагональ шлюза


class Pool:
    def __init__(self, ax, x, y, w, title, lanes, lane_h=1.75, head=0.55, lane_head=0.55):
        """lanes: список (ключ, подпись, цвет) сверху вниз."""
        self.ax, self.x, self.y, self.w = ax, x, y, w
        self.lane_h, self.head, self.lh = lane_h, head, lane_head
        self.keys = {}
        h = lane_h * len(lanes)
        self.h = h
        ax.add_patch(Rectangle((x, y), w, h, fc="white", ec=LINE, lw=1.0, zorder=1))
        ax.add_patch(Rectangle((x, y), head, h, fc=PAL["gray"][0], ec=LINE, lw=1.0, zorder=1))
        ax.text(x + head / 2, y + h / 2, title, rotation=90, ha="center", va="center", fontsize=7.6,
                fontweight="bold", color=INK, zorder=5)
        for i, (k, name, col) in enumerate(lanes):
            ly = y + h - (i + 1) * lane_h
            self.keys[k] = ly + lane_h / 2
            ax.add_patch(Rectangle((x + head, ly), lane_head, lane_h, fc=PAL[col][0], ec=LINE, lw=0.8, zorder=1))
            ax.add_patch(Rectangle((x + head + lane_head, ly), w - head - lane_head, lane_h, fc="none", ec=LINE,
                                   lw=0.8, zorder=1))
            ax.text(x + head + lane_head / 2, ly + lane_h / 2, name, rotation=90, ha="center", va="center",
                    fontsize=6.6, color=INK, zorder=5, linespacing=1.05)
        self.x0 = x + head + lane_head

    def cy(self, lane, dy=0.0):
        return self.keys[lane] + dy


def task(ax, cx, cy, text, color="blue", w=TW, h=TH, marker=None, fs=5.9):
    box(ax, cx - w / 2, cy - h / 2, w, h, "", color=color, r=0.14, fs=fs)
    label(ax, cx + (0.1 if marker else 0), cy - 0.05, text, fs=fs)
    mx, my = cx - w / 2 + 0.17, cy + h / 2 - 0.2
    ec = PAL[color][1]
    if marker in ("user", "manual"):  # пользовательская задача: человечек
        from matplotlib.patches import Wedge
        ax.add_patch(Circle((mx, my + 0.06), 0.045, fc="white", ec=ec, lw=0.7, zorder=6))
        ax.add_patch(Wedge((mx, my - 0.07), 0.09, 0, 180, fc="white", ec=ec, lw=0.7, zorder=6))
    elif marker == "service":  # сервисная задача: шестерёнка
        import numpy as np
        a = np.linspace(0, 2 * np.pi, 17)
        rr = np.where(np.arange(17) % 2 == 0, 0.1, 0.075)
        ax.add_patch(Polygon(np.c_[mx + rr * np.cos(a), my + rr * np.sin(a)], closed=True, fc="white", ec=ec, lw=0.7,
                             zorder=6))
        ax.add_patch(Circle((mx, my), 0.03, fc="white", ec=ec, lw=0.6, zorder=7))
    return dict(l=(cx - w / 2, cy), r=(cx + w / 2, cy), t=(cx, cy + h / 2), b=(cx, cy - h / 2), c=(cx, cy))


def event(ax, cx, cy, kind="start", text=None, inner=None, tpos="below"):
    col = {"start": "green", "end": "pink", "inter": "orange"}[kind]
    fc, ec = PAL[col]
    lw = {"start": 1.1, "end": 2.6, "inter": 1.0}[kind]
    ax.add_patch(Circle((cx, cy), ER, fc=fc, ec=ec, lw=lw, zorder=4))
    if kind == "inter":
        ax.add_patch(Circle((cx, cy), ER - 0.05, fc="none", ec=ec, lw=0.8, zorder=4))
    if inner == "msg":
        ax.add_patch(Rectangle((cx - 0.1, cy - 0.065), 0.2, 0.13, fc="white", ec=ec, lw=0.7, zorder=5))
        ax.plot([cx - 0.1, cx, cx + 0.1], [cy + 0.065, cy - 0.01, cy + 0.065], color=ec, lw=0.7, zorder=6)
    if inner == "timer":
        ax.add_patch(Circle((cx, cy), 0.1, fc="white", ec=ec, lw=0.7, zorder=5))
        ax.plot([cx, cx, cx + 0.05], [cy + 0.07, cy, cy], color=ec, lw=0.6, zorder=6)
    if text and tpos == "below":
        label(ax, cx, cy - ER - 0.27, text, fs=5.8)
    elif text:
        label(ax, cx + ER + 0.08, cy, text, fs=5.8, ha="left")
    return dict(l=(cx - ER, cy), r=(cx + ER, cy), t=(cx, cy + ER), b=(cx, cy - ER), c=(cx, cy))


def gateway(ax, cx, cy, text=None, kind="x", tpos="above"):
    fc, ec = PAL["orange"]
    ax.add_patch(Polygon([(cx, cy + GR), (cx + GR, cy), (cx, cy - GR), (cx - GR, cy)], closed=True, fc=fc, ec=ec,
                         lw=1.1, zorder=4))
    d = 0.1
    if kind == "x":
        ax.plot([cx - d, cx + d], [cy - d, cy + d], color=ec, lw=1.4, zorder=5)
        ax.plot([cx - d, cx + d], [cy + d, cy - d], color=ec, lw=1.4, zorder=5)
    elif kind == "+":
        ax.plot([cx - d * 1.3, cx + d * 1.3], [cy, cy], color=ec, lw=1.4, zorder=5)
        ax.plot([cx, cx], [cy - d * 1.3, cy + d * 1.3], color=ec, lw=1.4, zorder=5)
    if text:
        if tpos == "above":
            label(ax, cx, cy + GR + 0.2, text, fs=5.9)
        else:
            label(ax, cx, cy - GR - 0.2, text, fs=5.9)
    return dict(l=(cx - GR, cy), r=(cx + GR, cy), t=(cx, cy + GR), b=(cx, cy - GR), c=(cx, cy))


def flow(ax, pts, text=None, tx=None, ty=None, ls="-"):
    arrow(ax, pts, color=LINE, lw=0.85, ls=ls, ms=6.5)
    if text:
        if tx is None:
            (x1, y1), (x2, y2) = pts[0], pts[1]
            tx, ty = (x1 + x2) / 2, (y1 + y2) / 2 + 0.13
        label(ax, tx, ty, text, fs=5.8, bg="white")


def message(ax, pts, text=None, tx=None, ty=None):
    """Поток сообщений: пунктир, кружок в начале, полая стрелка."""
    x0, y0 = pts[0]
    ax.add_patch(Circle((x0, y0), 0.05, fc="white", ec=LINE, lw=0.7, zorder=6))
    for (x1, y1), (x2, y2) in zip(pts[:-2], pts[1:-1]):
        ax.plot([x1, x2], [y1, y2], color=LINE, lw=0.7, ls=(0, (3, 2)), zorder=2)
    from matplotlib.patches import FancyArrowPatch
    ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=7, lw=0.7, ls=(0, (3, 2)),
                                 fc="white", ec=LINE, zorder=2, shrinkA=0, shrinkB=0))
    if text:
        label(ax, tx, ty, text, fs=5.8, bg="white", italic=True)


def data(ax, cx, cy, text, w=0.42, h=0.55, store=False):
    if store:
        from matplotlib.patches import Ellipse
        fc, ec = PAL["purple"]
        ax.add_patch(Rectangle((cx - w / 2, cy - h / 2), w, h, fc=fc, ec="none", zorder=4))
        ax.plot([cx - w / 2, cx - w / 2], [cy - h / 2, cy + h / 2], color=ec, lw=0.8, zorder=5)
        ax.plot([cx + w / 2, cx + w / 2], [cy - h / 2, cy + h / 2], color=ec, lw=0.8, zorder=5)
        ax.add_patch(Ellipse((cx, cy + h / 2), w, 0.16, fc=fc, ec=ec, lw=0.8, zorder=5))
        ax.add_patch(Ellipse((cx, cy - h / 2), w, 0.16, fc=fc, ec=ec, lw=0.8, zorder=4))
    else:
        fc, ec = PAL["white"]
        f = 0.13
        ax.add_patch(Polygon([(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2 - f),
                              (cx + w / 2 - f, cy + h / 2), (cx - w / 2, cy + h / 2)], closed=True, fc=fc, ec=ec,
                             lw=0.8, zorder=4))
    label(ax, cx, cy - h / 2 - 0.3, text, fs=5.6)
    return dict(c=(cx, cy), t=(cx, cy + h / 2), b=(cx, cy - h / 2), l=(cx - w / 2, cy), r=(cx + w / 2, cy))


def assoc(ax, p1, p2):
    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color="#8A93A6", lw=0.7, ls=(0, (1.5, 1.5)), zorder=2)


def problem(ax, cx, cy, n):
    """Красный маркер проблемного места AS-IS."""
    fc, ec = PAL["pink"]
    ax.add_patch(Circle((cx, cy), 0.15, fc=ec, ec="white", lw=0.8, zorder=9))
    ax.text(cx, cy - 0.005, str(n), ha="center", va="center", fontsize=6, color="white", fontweight="bold", zorder=10)


# --- значки для легенды ---
def lg_task(ax, cx, cy):
    box(ax, cx - 0.3, cy - 0.13, 0.6, 0.26, color="blue", r=0.06)


def lg_service(ax, cx, cy):
    box(ax, cx - 0.3, cy - 0.13, 0.6, 0.26, color="green", r=0.06)


def lg_start(ax, cx, cy):
    ax.add_patch(Circle((cx - 0.15, cy), 0.12, fc=PAL["green"][0], ec=PAL["green"][1], lw=1.0, zorder=4))
    ax.add_patch(Circle((cx + 0.2, cy), 0.12, fc=PAL["pink"][0], ec=PAL["pink"][1], lw=2.2, zorder=4))


def lg_gw(ax, cx, cy):
    ax.add_patch(Polygon([(cx, cy + 0.16), (cx + 0.16, cy), (cx, cy - 0.16), (cx - 0.16, cy)], closed=True,
                         fc=PAL["orange"][0], ec=PAL["orange"][1], lw=1.0, zorder=4))
    ax.plot([cx - .05, cx + .05], [cy - .05, cy + .05], color=PAL["orange"][1], lw=1)
    ax.plot([cx - .05, cx + .05], [cy + .05, cy - .05], color=PAL["orange"][1], lw=1)


def lg_flow(ax, cx, cy):
    arrow(ax, [(cx - 0.35, cy), (cx + 0.35, cy)], ms=6)


def lg_msg(ax, cx, cy):
    message(ax, [(cx - 0.35, cy), (cx + 0.35, cy)])


def lg_data(ax, cx, cy):
    data(ax, cx - 0.2, cy, "", w=0.22, h=0.3)
    data(ax, cx + 0.2, cy, "", w=0.24, h=0.26, store=True)


def lg_problem(ax, cx, cy):
    problem(ax, cx, cy, 1)


def lg_inter(ax, cx, cy):
    fc, ec = PAL["orange"]
    ax.add_patch(Circle((cx, cy), 0.13, fc=fc, ec=ec, lw=0.9, zorder=4))
    ax.add_patch(Circle((cx, cy), 0.1, fc="none", ec=ec, lw=0.6, zorder=4))
