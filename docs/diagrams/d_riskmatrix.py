from vstyle import figure, save, label, PAL, CM
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
fig, ax = figure(16.5, 10.2)
x0, y0, c = 1.6, 1.3, 0.78
G, Y, Rr = "#CFEBD9", "#F8E3B5", "#F5C6D3"
for p in range(1, 11):
    for i in range(1, 11):
        r = p * i
        col = G if r <= 24 else Y if r <= 56 else Rr
        ax.add_patch(Rectangle((x0 + (i - 1) * c, y0 + (p - 1) * c), c, c, fc=col, ec="white", lw=1.2))
        ax.text(x0 + (i - 0.5) * c, y0 + (p - 0.5) * c, str(r), ha="center", va="center", fontsize=6.2, color="#1F2433")
for k in range(1, 11):
    label(ax, x0 + (k - 0.5) * c, y0 - 0.25, str(k), fs=6.6)
    label(ax, x0 - 0.25, y0 + (k - 0.5) * c, str(k), fs=6.6)
label(ax, x0 + 5 * c, y0 - 0.65, "Влияние I (последствия для мероприятия), баллы", fs=7)
label(ax, x0 - 0.75, y0 + 5 * c, "Вероятность P, баллы", fs=7); ax.texts[-1].set_rotation(90)
pts = [("1", 3, 3, "Разминка: R = 9"), ("2", 6.36, 6.36, "Музыкальный раунд: R = 40,5"), ("3", 3, 6, "Финал: R = 18")]
for n, p, i, t in pts:
    cx, cy = x0 + (i - 0.5) * c, y0 + (p - 0.5) * c
    ax.add_patch(Circle((cx, cy), 0.2, fc="#6B4FD0", ec="white", lw=1.2, zorder=5))
    ax.text(cx, cy - 0.01, n, ha="center", va="center", fontsize=6.4, color="white", fontweight="bold", zorder=6)
X = 10.0
label(ax, X, 9.5, "Зоны риска R = P · I", ha="left", bold=True, fs=7.6)
for k, (col, t) in enumerate([(G, "зелёная, R ≤ 24 — риск допустим"), (Y, "жёлтая, 24 < R ≤ 56 — нужны меры"),
                              (Rr, "красная, R > 56 — блок переработать")]):
    ax.add_patch(Rectangle((X, 8.7 - k * 0.55), 0.45, 0.35, fc=col, ec="none"))
    label(ax, X + 0.6, 8.875 - k * 0.55, t, ha="left", fs=6.8)
label(ax, X, 6.9, "Контрольный пример (средние P и I)", ha="left", bold=True, fs=7.6)
for k, (n, p, i, t) in enumerate(pts):
    yy = 6.3 - k * 0.55
    ax.add_patch(Circle((X + 0.22, yy), 0.17, fc="#6B4FD0", ec="white", lw=1, zorder=5))
    ax.text(X + 0.22, yy - 0.01, n, ha="center", va="center", fontsize=6, color="white", fontweight="bold", zorder=6)
    label(ax, X + 0.6, yy, t, ha="left", fs=6.8)
label(ax, X, 4.1, "Риск проекта", ha="left", bold=True, fs=7.6)
label(ax, X, 3.3, "Q = 1 − Π(1 − κ·Rⱼ / 100)\nвероятность, что сработает\nхотя бы один риск блоков;\nв примере Q = 0,56", ha="left", fs=6.8)
save(fig, "png/riskmatrix.png")
