"""Общий стиль схем ВКР: светлые заливки, цветная обводка, шрифт без засечек.

Схемы рисуются сразу в итоговом размере (ширина 16,5 см), поэтому кегль в пунктах равен кеглю на странице.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Polygon, Circle, FancyArrowPatch  # noqa: E402

plt.rcParams["font.family"] = "Inter"
plt.rcParams["font.size"] = 8

PAL = {
    "blue": ("#E6EEFB", "#2F6FD1"),
    "green": ("#E0F3E8", "#2E9A5F"),
    "purple": ("#ECE8FB", "#6B4FD0"),
    "orange": ("#FBEFD9", "#C98A12"),
    "pink": ("#FBE6EE", "#C2306B"),
    "gray": ("#EEF0F4", "#7C8597"),
    "white": ("#FFFFFF", "#3A4256"),
}
INK = "#1F2433"
LINE = "#3A4256"
CM = 1 / 2.54


def figure(w_cm=16.5, h_cm=10.0):
    fig = plt.figure(figsize=(w_cm * CM, h_cm * CM))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w_cm)
    ax.set_ylim(0, h_cm)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, text="", color="blue", r=0.12, fs=7.5, bold=False, ls="-", lw=1.1, tcolor=None, fill=True,
        align="center", va="center", z=3):
    """Прямоугольник со скруглением; x, y — левый нижний угол, см."""
    fc, ec = PAL[color]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", fc=fc if fill else "none",
                                ec=ec, lw=lw, ls=ls, zorder=z))
    if text:
        tx = x + w / 2 if align == "center" else x + 0.15
        ty = y + h / 2 if va == "center" else y + h - 0.12
        ax.text(tx, ty, text, ha=align, va=va, fontsize=fs, color=tcolor or INK, fontweight="bold" if bold else None,
                zorder=z + 1, linespacing=1.15)


def arrow(ax, pts, color=LINE, lw=0.9, ls="-", head=True, z=2, ms=7):
    """Ломаная со стрелкой на конце; pts — список точек, см."""
    for (x1, y1), (x2, y2) in zip(pts[:-2], pts[1:-1]):
        ax.plot([x1, x2], [y1, y2], color=color, lw=lw, ls=ls, zorder=z, solid_capstyle="butt")
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>" if head else "-", mutation_scale=ms, lw=lw,
                                 color=color, ls=ls, zorder=z, shrinkA=0, shrinkB=0))


def label(ax, x, y, text, fs=6.8, color=INK, ha="center", va="center", italic=False, bold=False, bg=None, z=6):
    kw = {}
    if bg:
        kw["bbox"] = dict(boxstyle="round,pad=0.12", fc=bg, ec="none")
    ax.text(x, y, text, fontsize=fs, color=color, ha=ha, va=va, style="italic" if italic else "normal",
            fontweight="bold" if bold else None, zorder=z, linespacing=1.15, **kw)


def legend(ax, x, y, items, title="Обозначения", w=None, fs=6.6, row=0.42):
    """items: список (функция_рисования(ax, cx, cy), подпись). Рамка — серая."""
    h = row * len(items) + 0.5
    w = w or 6.0
    box(ax, x, y, w, h, color="gray", fill=False, r=0.08, lw=0.8)
    label(ax, x + 0.15, y + h - 0.22, title, fs=fs + 0.4, ha="left", bold=True)
    for k, (draw, text) in enumerate(items):
        cy = y + h - 0.55 - k * row
        draw(ax, x + 0.55, cy)
        label(ax, x + 1.05, cy, text, fs=fs, ha="left")
    return h


def save(fig, path, dpi=300):
    fig.savefig(path, dpi=dpi, facecolor="white")
    plt.close(fig)
