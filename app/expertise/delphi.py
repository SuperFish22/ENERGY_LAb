"""Метод Б — облегчённый Дельфи: ранги, коэффициент конкордации Кендалла, медиана и IQR (формула 4 ВКР)."""
import statistics


def ranks(values: list[float]) -> list[float]:
    """Ранги по убыванию балла (лучший — 1); связанные значения получают средний ранг."""
    order = sorted(range(len(values)), key=lambda i: -values[i])
    result = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            result[order[k]] = avg
        i = j + 1
    return result


def kendall_w(matrix: list[list[float]]) -> float | None:
    """W = 12·S_R / (m²(n³ − n)); matrix — строки экспертов, столбцы объектов (баллы).

    Возвращает None, если экспертов меньше 2 или объектов меньше 3 (ЧТЗ-3, EXP-08).
    """
    m = len(matrix)
    if m < 2:
        return None
    n = len(matrix[0])
    if n < 3 or any(len(r) != n for r in matrix):
        return None
    rank_rows = [ranks(r) for r in matrix]
    sums = [sum(r[j] for r in rank_rows) for j in range(n)]
    mean = sum(sums) / n
    s_r = sum((s - mean) ** 2 for s in sums)
    return 12 * s_r / (m ** 2 * (n ** 3 - n))


def median_iqr(values: list[float]) -> tuple[float, float]:
    if not values:
        raise ValueError("нет значений")
    med = statistics.median(values)
    if len(values) < 2:
        return med, 0.0
    q = statistics.quantiles(values, n=4, method="inclusive")
    return med, q[2] - q[0]


def needs_second_round(w: float | None, round_no: int, threshold: float, max_rounds: int,
                       max_v: float | None = None, cv_max: float = 33) -> bool:
    """Второй тур нужен, если ранжирование не согласовано (W ниже порога) или оценки хотя бы одного блока
    разошлись сильнее порога коэффициента вариации."""
    if round_no >= max_rounds:
        return False
    return (w is not None and w < threshold) or (max_v is not None and max_v > cv_max)
