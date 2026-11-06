"""Метод В — матрица рисков станций (формулы 5–6 ВКР)."""
import math


def level(p: float, i: float) -> float:
    """R_s = P̄_s · Ī_s."""
    return p * i


def zone(r: float, zones=(6, 14)) -> str:
    green, yellow = zones
    if r <= green:
        return "green"
    if r <= yellow:
        return "yellow"
    return "red"


ZONE_NAMES = {"green": "Зелёная", "yellow": "Жёлтая", "red": "Красная"}


def event_risk(levels: list[float], kappa: float = 1.0) -> float:
    """Q = 1 − Π (1 − κ·R_s/25)."""
    if not levels:
        return 0.0
    return 1 - math.prod(1 - min(1.0, kappa * r / 25) for r in levels)
