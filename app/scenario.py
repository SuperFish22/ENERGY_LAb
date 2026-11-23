"""Сценарий мероприятия: лента блоков по времени (spec 002).

Блок — часть программы со временем начала, длительностью, стоимостью и ответственным. Виды блоков:
* «block»    — блок программы (открытие, основная часть, финал); по умолчанию оценивается экспертами и гостями;
* «service»  — служебный блок (сбор гостей, перерыв, трансфер); по умолчанию не оценивается;
* «carousel» — карусель станций: группы гостей параллельно проходят станции по кругу;
* «station»  — станция внутри карусели.

Время блоков верхнего уровня идёт подряд от времени начала мероприятия. Длительность карусели:
n станций × самая длинная станция + (n − 1) × переход — каждая группа проходит все станции.
Модуль не обращается к БД: работает с любыми объектами, у которых есть нужные атрибуты.
"""
from __future__ import annotations

from dataclasses import dataclass, field

KINDS = {"block": "Блок программы", "service": "Служебный блок", "carousel": "Карусель станций",
         "station": "Станция"}
RATED_BY_DEFAULT = {"block": True, "service": False, "carousel": False, "station": True}


@dataclass
class Row:
    block: object
    start: int                  # минуты от начала мероприятия
    minutes: int
    children: list[Row] = field(default_factory=list)
    warning: str | None = None

    @property
    def end(self) -> int:
        return self.start + self.minutes


def carousel_minutes(stations: list, transition_min: int = 0) -> int:
    n = len(stations)
    if not n:
        return 0
    return n * max(int(s.duration_min or 0) for s in stations) + (n - 1) * max(0, int(transition_min or 0))


def _ordered(items: list) -> list:
    return sorted(items, key=lambda b: (b.order_no or 0, b.id or 0))


def timeline(blocks: list) -> tuple[list[Row], int]:
    """Строки сценария верхнего уровня (с вложенными станциями карусели) и общая длительность, мин."""
    top = _ordered([b for b in blocks if not getattr(b, "parent_id", None)])
    kids: dict[int, list] = {}
    for b in blocks:
        if getattr(b, "parent_id", None):
            kids.setdefault(b.parent_id, []).append(b)
    rows, t = [], 0
    for b in top:
        if b.kind == "carousel":
            st = _ordered(kids.get(b.id, []))
            minutes = carousel_minutes(st, b.transition_min)
            row = Row(b, t, minutes)
            slot = max((int(s.duration_min or 0) for s in st), default=0)
            for s in st:
                row.children.append(Row(s, t, slot))      # станции идут параллельно, каждая — круг по `slot` минут
            groups = int(b.groups or 0)
            if st and groups > len(st):
                row.warning = f"Групп ({groups}) больше, чем станций ({len(st)}): кому-то придётся ждать"
            elif not st:
                row.warning = "В карусели пока нет станций"
        else:
            row = Row(b, t, int(b.duration_min or 0))
        rows.append(row)
        t += row.minutes
    return rows, t


def rated(blocks: list) -> list:
    """Что оценивают эксперты и гости, в порядке сценария: отмеченные блоки и станции каруселей."""
    out = []
    for row in timeline(blocks)[0]:
        if row.block.kind == "carousel":
            out.extend(r.block for r in row.children if r.block.rated)
        elif row.block.rated:
            out.append(row.block)
    return out


def clock(start_time: str | None, minutes: int) -> str | None:
    """«18:00» + 75 → «19:15» (через полночь — по кругу)."""
    if not start_time:
        return None
    try:
        h, m_ = (int(x) for x in start_time.split(":")[:2])
    except ValueError:
        return None
    total = (h * 60 + m_ + minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def fact_minutes(blocks: list) -> tuple[int | None, int]:
    """Фактическая длительность по блокам верхнего уровня: (сумма или None, сколько блоков заполнено)."""
    top = [b for b in blocks if not getattr(b, "parent_id", None)]
    filled = [b for b in top if b.fact_min is not None]
    return (sum(int(b.fact_min) for b in filled) if filled else None), len(filled)
