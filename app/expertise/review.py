"""Итоговая оценка (разбор полёта): план → прогноз → факт, голос гостей и точность экспертов.

Замыкает цикл планирования: насколько прогноз попал в факт, какие станции гости оценили иначе,
чем эксперты, и как изменится компетентность каждого эксперта (формула 10 ВКР).
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.config import METHOD
from app.expertise import competence, scoring, service


@dataclass
class Row:
    metric: str
    unit: str
    plan: float | None
    forecast: float | None
    fact: float | None
    better: str = "more"          # что считать хорошим отклонением: more | less | none

    @property
    def deviation(self) -> float | None:
        """Отклонение факта от прогноза, доля (0.12 = +12 %)."""
        if self.forecast in (None, 0) or self.fact is None:
            return None
        return (self.fact - self.forecast) / abs(self.forecast)

    @property
    def tone(self) -> str:
        d = self.deviation
        if d is None or abs(d) < 0.1 or self.better == "none":
            return "ok"
        good = d > 0 if self.better == "more" else d < 0
        return "good" if good else "bad"


def nps(values: list[int]) -> float | None:
    """NPS = % промоутеров (9–10) − % критиков (0–6)."""
    if not values:
        return None
    return (sum(v >= 9 for v in values) - sum(v <= 6 for v in values)) / len(values) * 100


def accuracy(rows: list[Row]) -> float | None:
    """Точность прогноза = 100 % − средняя абсолютная ошибка в процентах (MAPE) по доступным показателям."""
    errs = [abs(r.deviation) for r in rows if r.deviation is not None and r.metric != "Оценка гостей"]
    if not errs:
        return None
    return max(0.0, 100 * (1 - sum(errs) / len(errs)))


def build(db: Session, ev: m.Event) -> dict:
    res = ev.result
    fc = db.scalar(select(m.Forecast).where(m.Forecast.event_id == ev.id).order_by(m.Forecast.id.desc()))
    fbs = db.scalars(select(m.Feedback).where(m.Feedback.event_id == ev.id, m.Feedback.excluded.is_(False))).all()
    price = float(ev.ticket_price or 0)
    cap = ev.capacity or (ev.venue.capacity if ev.venue else None)
    guest_avg = sum(f.rating for f in fbs) / len(fbs) if fbs else None
    rating_fact = res.avg_rating if res and res.avg_rating is not None else guest_avg

    rows = [
        Row("Гости", "чел.", cap, fc.attendance if fc else None, res.guests_count if res else None),
        Row("Продано билетов", "шт.", cap, fc.tickets_sold if fc else None, res.tickets_sold if res else None),
        Row("Выручка", "₽", price * cap if cap else None, fc.revenue if fc else None,
            float(res.revenue) if res else None),
        Row("Затраты", "₽", float(ev.planned_budget or 0) or None, fc.budget if fc else None,
            float(res.actual_cost) if res else None, better="less"),
        Row("Оценка гостей", "из 5", None, fc.avg_rating if fc else None, rating_fact),
    ]
    in_range = None
    if fc and fc.attendance_low is not None and res:
        in_range = fc.attendance_low <= res.guests_count <= fc.attendance_high

    # станции: оценка экспертов vs оценка гостей
    summ = service.summary(db, ev)
    stations = []
    for s in summ["stations"]:
        vals = db.scalars(select(m.FeedbackStation.rating).where(m.FeedbackStation.station_id == s["station"].id)).all()
        g = sum(vals) / len(vals) if vals else None
        stations.append({**s, "guests": g, "n": len(vals),
                         "gap": (g - s["S"]) if g is not None and s["S"] is not None else None})

    # точность экспертов
    experts = []
    hist = {h.expert_id: h for h in db.scalars(select(m.CompetenceHistory)
                                                .where(m.CompetenceHistory.event_id == ev.id))}
    rnd = summ["round"]
    if rnd and rating_fact is not None:
        criteria, dept_w, _ = service._criteria_maps(db)
        evals = db.scalars(select(m.Evaluation).where(m.Evaluation.round_id == rnd.id,
                                                      m.Evaluation.submitted.is_(True))).all()
        scores = [scoring.Score(e.expert_id, e.criterion_id, e.score, e.station_id) for e in evals]
        for eid in sorted({e.expert_id for e in evals}):
            s_e = scoring.expert_total(scores, criteria, dept_w, eid, None)
            if s_e is None:
                continue
            ex = db.get(m.Expert, eid)
            h = hist.get(eid)
            old = h.old_value if h else ex.competence
            new = h.new_value if h else competence.update(ex.competence, s_e, rating_fact, METHOD["eta"],
                                                          METHOD["competence_bounds"])
            experts.append({"expert": ex, "S_e": s_e, "acc": 1 - abs(s_e - rating_fact) / 4, "old": old, "new": new,
                            "applied": h is not None})

    dist = {k: sum(f.rating == k for f in fbs) for k in range(5, 0, -1)}
    return {"rows": rows, "fc": fc, "accuracy": accuracy(rows), "in_range": in_range,
            "feedback": {"n": len(fbs), "avg": guest_avg, "nps": nps([f.nps for f in fbs if f.nps is not None]),
                         "dist": dist, "comments": [f for f in fbs if f.comment][:8]},
            "rating_fact": rating_fact, "stations": stations, "experts": experts,
            "has_expertise": bool(rnd), "done": bool(res and res.reviewed_at)}
