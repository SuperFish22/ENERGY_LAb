"""Метод А — взвешенная оценка по критериям и коэффициент вариации оценок (шкала 1–10)."""
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Score:
    expert_id: int
    criterion_id: int
    score: int
    station_id: int | None = None


def normalize(weights: dict) -> dict:
    """w_k = v_k / Σ v_i. Пустой или нулевой набор — равные веса."""
    total = sum(v for v in weights.values() if v and v > 0)
    if not weights:
        return {}
    if total <= 0:
        return {k: 1 / len(weights) for k in weights}
    return {k: (v if v and v > 0 else 0) / total for k, v in weights.items()}


def weighted_mean(values: list[float], competences: list[float]) -> float:
    """x̄ = Σ c_e·x_e / Σ c_e."""
    if not values:
        raise ValueError("нет оценок")
    den = sum(competences)
    return sum(c * x for c, x in zip(competences, values, strict=True)) / den


def variation(values: list[float], competences: list[float] | None = None) -> dict | None:
    """Коэффициент вариации V = σ / x̄ · 100 %, σ — взвешенное по компетентности стандартное отклонение.

    Возвращает среднее, σ и V; для одного значения V = 0. Пусто — None.
    """
    if not values:
        return None
    c = competences or [1.0] * len(values)
    den = sum(c)
    mean = sum(ci * x for ci, x in zip(c, values, strict=True)) / den
    sigma = (sum(ci * (x - mean) ** 2 for ci, x in zip(c, values, strict=True)) / den) ** 0.5
    return {"mean": mean, "sigma": sigma, "V": sigma / mean * 100 if mean else 0.0, "n": len(values)}


def agreement(v: float | None, zones=(20, 33)) -> str | None:
    """Шкала согласованности по коэффициенту вариации."""
    if v is None:
        return None
    if v <= zones[0]:
        return "high"
    if v <= zones[1]:
        return "medium"
    return "low"


AGREEMENT_NAMES = {"high": "Согласованная", "medium": "Умеренная", "low": "Несогласованная"}


def object_score(scores: list[Score], criteria: dict[int, tuple[int, float]], dept_weights: dict[int, float],
                 competence: dict[int, float], station_id: int | None = None) -> dict:
    """Итоговая оценка объекта S (формула 3).

    criteria: criterion_id -> (department_id, weight);
    dept_weights: department_id -> α; competence: expert_id -> c.
    Критерии без оценок исключаются, их вес перераспределяется внутри отдела;
    отдел без оценок исключается, вес отделов нормируется заново.
    """
    by_crit = defaultdict(list)
    for s in scores:
        if s.station_id == station_id and s.criterion_id in criteria:
            by_crit[s.criterion_id].append(s)
    per_dept = defaultdict(dict)
    crit_means = {}
    for cid, items in by_crit.items():
        mean = weighted_mean([i.score for i in items], [competence.get(i.expert_id, 0.7) for i in items])
        crit_means[cid] = mean
        dept, w = criteria[cid]
        per_dept[dept][cid] = (w, mean)
    dept_scores = {}
    for dept, crits in per_dept.items():
        w = normalize({cid: v[0] for cid, v in crits.items()})
        dept_scores[dept] = sum(w[cid] * crits[cid][1] for cid in crits)
    alpha = normalize({d: dept_weights.get(d, 0) for d in dept_scores})
    total = sum(alpha[d] * dept_scores[d] for d in dept_scores) if dept_scores else None
    missing = sorted(set(dept_weights) - set(dept_scores))
    return {"S": total, "departments": dept_scores, "criteria": crit_means, "missing_departments": missing}


def expert_total(scores: list[Score], criteria, dept_weights, expert_id: int, station_id=None) -> float | None:
    """S_e — итоговая оценка объекта только по баллам одного эксперта (для компетентности и рангов)."""
    own = [s for s in scores if s.expert_id == expert_id]
    res = object_score(own, criteria, dept_weights, {expert_id: 1.0}, station_id)
    return res["S"]
