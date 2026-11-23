from vstyle import save, CM
import matplotlib.pyplot as plt
import numpy as np
plt.rcParams["font.family"] = "Inter"; plt.rcParams["font.size"] = 8
fig, ax = plt.subplots(figsize=(16.5 * CM, 7.5 * CM))
blocks = ["Разминка", "Музыкальный раунд", "Финал"]
ve, vg = [10.7, 27.1, 15.1], [7.0, 34.6, 7.8]
x = np.arange(3); w = 0.32
ax.axhspan(0, 20, color="#E0F3E8", zorder=0); ax.axhspan(20, 33, color="#FBEFD9", zorder=0)
ax.axhspan(33, 42, color="#FBE6EE", zorder=0)
b1 = ax.bar(x - w / 2 - 0.01, ve, w, color="#6B4FD0", label="эксперты (тур 1)", zorder=3)
b2 = ax.bar(x + w / 2 + 0.01, vg, w, color="#2F6FD1", label="гости (12 анкет)", zorder=3)
for b in list(b1) + list(b2):
    ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.6, f"{b.get_height():.1f}".replace(".", ",") + " %",
            ha="center", fontsize=7, color="#1F2433")
ax.set_xticks(x, blocks); ax.set_ylim(0, 42); ax.set_ylabel("Коэффициент вариации V, %")
for y, t in [(10, "согласованная\n(≤ 20 %)"), (26.5, "умеренная\n(≤ 33 %)"), (37.5, "несогласованная\n(> 33 %)")]:
    ax.text(2.45, y, t, fontsize=6.8, va="center", ha="left", color="#3A4256", style="italic")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(loc="upper left", frameon=False, fontsize=7)
ax.set_xlim(-0.5, 3.35)
fig.tight_layout()
save(fig, "png/cvchart.png")
