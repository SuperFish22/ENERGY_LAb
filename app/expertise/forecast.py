"""Метод Г — прогноз по аналогам (формулы 7–9 ВКР) и правила рекомендации (ЧТЗ-3, раздел 3)."""
import math
from dataclasses import dataclass, field


@dataclass
class EventFeatures:
    id: int
    title: str
    format_code: str           # код классификатора, первая цифра — группа
    price: float
    capacity: int
    month: int
    score: float | None
    # фактические показатели (только у проведённых)
    guests: int | None = None
    tickets: int | None = None
    planned_budget: float | None = None
    actual_cost: float | None = None
    rating: float | None = None
    extra: dict = field(default_factory=dict)


def _minmax(values: list[float]) -> tuple[float, float]:
    lo, hi = min(values), max(values)
    return lo, (hi - lo) or 1.0


def _season(m1: int, m2: int) -> float:
    d = abs(m1 - m2) % 12
    return min(d, 12 - d) / 6  # 0..1


def _format_dist(a: str, b: str) -> float:
    if a == b:
        return 0.0
    if a[:1] == b[:1]:
        return 0.5
    return 1.0


def distance(a: EventFeatures, b: EventFeatures, pool: list[EventFeatures], weights: dict) -> float:
    """d(a,b) = √(Σ λ_f (z_af − z_bf)²), числовые признаки нормируются min-max по пулу."""
    p_lo, p_rng = _minmax([e.price for e in pool + [a]])
    c_lo, c_rng = _minmax([e.capacity for e in pool + [a]])
    terms = {
        "format": _format_dist(a.format_code, b.format_code),
        "price": (a.price - b.price) / p_rng,
        "capacity": (a.capacity - b.capacity) / c_rng,
        "season": _season(a.month, b.month),
        "score": ((a.score or 0) - (b.score or 0)) / 9 if a.score is not None and b.score is not None else 0.0,
    }
    return math.sqrt(sum(weights.get(k, 0) * v ** 2 for k, v in terms.items()))


def idw(values: list[float], dists: list[float]) -> float:
    """ŷ = Σ(y_i/d_i) / Σ(1/d_i); при d = 0 берётся значение этого аналога."""
    for v, d in zip(values, dists, strict=True):
        if d == 0:
            return v
    num = sum(v / d for v, d in zip(values, dists, strict=True))
    den = sum(1 / d for d in dists)
    return num / den


def budget_forecast(station_costs: list[float], overruns: list[float]) -> float:
    """B̂ = (Σ C_s)(1 + δ̄)."""
    base = sum(station_costs)
    delta = sum(overruns) / len(overruns) if overruns else 0.0
    return base * (1 + delta)


def predict(target: EventFeatures, history: list[EventFeatures], weights: dict, k: int,
            station_costs: list[float]) -> dict:
    """Прогноз явки, продаж, выручки, бюджета и средней оценки гостей по k ближайшим аналогам."""
    hist = [h for h in history if h.guests is not None and h.id != target.id]
    if not hist:
        return {"analogs": [], "attendance": None}
    scored = sorted(((distance(target, h, hist, weights), h) for h in hist), key=lambda t: t[0])[: min(k, len(hist))]
    dists = [d for d, _ in scored]
    analogs = [h for _, h in scored]
    cap = target.capacity or max((h.capacity for h in analogs), default=0)
    # явку и продажи переносим через долю заполнения зала
    fills = [h.guests / h.capacity if h.capacity else 0 for h in analogs]
    sells = [(h.tickets or h.guests) / h.capacity if h.capacity else 0 for h in analogs]
    att = idw([f * cap for f in fills], dists)
    tix = idw([s * cap for s in sells], dists)
    att = min(att, cap) if cap else att
    tix = min(tix, cap) if cap else tix
    overruns = [(h.actual_cost / h.planned_budget - 1) for h in analogs
                if h.planned_budget and h.actual_cost is not None]
    ratings = [h.rating for h in analogs if h.rating is not None]
    rating_d = [d for d, h in scored if h.rating is not None]
    return {
        "analogs": [{"id": h.id, "title": h.title, "distance": round(d, 3)} for d, h in scored],
        "attendance": round(att),
        "attendance_low": round(min(f * cap for f in fills)),
        "attendance_high": round(min(max(f * cap for f in fills), cap or 10 ** 9)),
        "tickets_sold": round(tix),
        "revenue": round(tix * target.price, 2),
        "budget": round(budget_forecast(station_costs, overruns), 2),
        "avg_rating": round(idw(ratings, rating_d), 2) if ratings else None,
    }


def recommend(S: float | None, has_red: bool, w: float | None, rounds_done: int, max_rounds: int,
              budget: float | None, revenue: float | None, stations_v: list[tuple[str, float]] | None = None,
              reject_below: float = 5.5, rework_below: float = 6.5, cv_max: float = 33) -> tuple[str, list[str]]:
    """Правила рекомендации, проверяются по порядку (шкала 1–10).

    stations_v — пары (название блока, коэффициент вариации V, %) по оцениваемым блокам сценария.
    """
    reasons: list[str] = []
    if S is None:
        return "Недостаточно оценок", ["Ни один отдел ещё не выставил баллы"]
    if S < reject_below:
        why = f"Итоговая оценка {S:.2f} ниже {reject_below:g}".replace(".", ",")
        return "Отклонить или переработать концепцию", [why]
    if has_red:
        reasons.append("Есть блок сценария в красной зоне риска")
    if w is not None and w < 0.5 and rounds_done >= max_rounds:
        reasons.append(f"Эксперты не согласовали ранжирование блоков: W = {w:.2f} после {rounds_done} туров")
    for title, v in stations_v or []:
        if v is not None and v > cv_max and rounds_done >= max_rounds:
            reasons.append(f"Оценки блока «{title}» не согласованы: V = {v:.0f} % (порог {cv_max:g} %)")
    if S < rework_below:
        reasons.append(f"Итоговая оценка {S:.2f} ниже {rework_below:g}".replace(".", ","))
    warn = []
    if budget is not None and revenue is not None and budget > revenue:
        warn.append("Прогноз затрат выше прогноза выручки: мероприятие не окупается")
    if reasons:
        return "Доработать", reasons + warn
    return "Утвердить", warn
