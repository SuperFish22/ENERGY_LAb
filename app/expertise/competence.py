"""Уточнение коэффициента компетентности эксперта по факту (формула 10 ВКР)."""


def update(c: float, s_expert: float, r_fact: float, eta: float = 0.2, bounds=(0.5, 1.0)) -> float:
    """c_new = (1 − η)·c + η·(1 − |S_e − r_факт| / 4), с ограничением диапазоном bounds."""
    raw = (1 - eta) * c + eta * (1 - abs(s_expert - r_fact) / 4)
    return max(bounds[0], min(bounds[1], raw))
