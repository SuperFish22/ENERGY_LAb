"""Контрольный пример ЧТЗ-3, раздел 4: значения должны совпасть с точностью до 0,01."""
import pytest

from app.expertise import competence, delphi, forecast, risk, scoring


def test_weighted_mean_control():
    assert scoring.weighted_mean([4, 3, 5], [1.0, 0.8, 0.7]) == pytest.approx(3.96, abs=0.005)


def test_kendall_w_control():
    # 3 эксперта × 3 станции; ранги (1,2,3), (1,2,3), (2,1,3) → W = 0,78
    matrix = [[4.2, 3.1, 2.5], [3.9, 3.4, 2.8], [3.0, 4.1, 2.2]]
    assert delphi.ranks(matrix[2]) == [2, 1, 3]
    assert delphi.kendall_w(matrix) == pytest.approx(0.7778, abs=0.005)


def test_kendall_w_needs_data():
    assert delphi.kendall_w([[1, 2, 3]]) is None          # один эксперт
    assert delphi.kendall_w([[1, 2], [2, 1]]) is None      # две станции


def test_ties_get_average_rank():
    assert delphi.ranks([5, 5, 3]) == [1.5, 1.5, 3]


def test_risk_control():
    levels = [risk.level(2, 2), risk.level(3, 4), risk.level(4, 4)]
    assert levels == [4, 12, 16]
    assert [risk.zone(x) for x in levels] == ["green", "yellow", "red"]
    assert risk.event_risk(levels) == pytest.approx(0.84, abs=0.005)
    assert risk.event_risk(levels, kappa=0.5) < risk.event_risk(levels)


def test_idw_control():
    assert forecast.idw([58, 40, 38], [0.21, 0.34, 0.47]) == pytest.approx(48.29, abs=0.01)
    assert forecast.idw([58, 40], [0.0, 0.3]) == 58      # совпадающий аналог


def test_budget_control():
    assert forecast.budget_forecast([3000, 5500, 4000], [0.05, 0.12, 0.08]) == pytest.approx(13541.67, abs=0.01)


def test_competence_control():
    assert competence.update(0.8, 4.1, 4.4) == pytest.approx(0.825, abs=1e-6)
    assert competence.update(0.5, 1.0, 5.0) == 0.5        # нижняя граница


def test_normalize():
    assert scoring.normalize({"a": 2, "b": 2}) == {"a": 0.5, "b": 0.5}
    assert scoring.normalize({"a": 0, "b": 0}) == {"a": 0.5, "b": 0.5}


def test_object_score_redistributes_missing_department():
    criteria = {1: (10, 0.5), 2: (10, 0.5), 3: (20, 1.0)}
    dept_w = {10: 0.5, 20: 0.5}
    scores = [scoring.Score(1, 1, 4), scoring.Score(1, 2, 2)]          # отдел 20 не оценил
    res = scoring.object_score(scores, criteria, dept_w, {1: 1.0})
    assert res["S"] == pytest.approx(3.0)
    assert res["missing_departments"] == [20]


def test_recommendation_rules():
    assert forecast.recommend(2.9, False, 0.8, 1, 2, 100, 200)[0].startswith("Отклонить")
    assert forecast.recommend(4.0, True, 0.8, 1, 2, 100, 200)[0] == "Доработать"
    assert forecast.recommend(4.0, False, 0.3, 2, 2, 100, 200)[0] == "Доработать"
    rec, reasons = forecast.recommend(4.2, False, 0.7, 1, 2, 300, 200)
    assert rec == "Утвердить" and "не окупается" in reasons[0]


def test_predict_uses_capacity_and_caps():
    hist = [forecast.EventFeatures(1, "A", "21", 1000, 50, 5, 4.0, guests=40, tickets=40, planned_budget=1000,
                                   actual_cost=1100, rating=4.5),
            forecast.EventFeatures(2, "B", "11", 500, 100, 2, 3.5, guests=60, tickets=60, planned_budget=2000,
                                   actual_cost=2000, rating=4.0)]
    target = forecast.EventFeatures(3, "C", "21", 1000, 60, 5, 4.0)
    res = forecast.predict(target, hist, {"format": 0.35, "price": 0.2, "capacity": 0.15, "season": 0.1,
                                          "score": 0.2}, 3, [500, 500])
    assert res["analogs"][0]["title"] == "A"                 # ближе по формату и цене
    assert 0 < res["attendance"] <= 60
    assert res["revenue"] == pytest.approx(res["tickets_sold"] * 1000, rel=0.01)


def test_review_metrics():
    from app.expertise.review import Row, accuracy, nps
    assert nps([10, 9, 8, 6, 3]) == (2 - 2) / 5 * 100
    assert nps([]) is None
    rows = [Row("Гости", "чел.", 60, 50, 55), Row("Затраты", "₽", 9000, 10000, 9000, better="less"),
            Row("Оценка гостей", "из 5", None, 4.5, 4.0)]
    assert abs(rows[0].deviation - 0.1) < 1e-9 and rows[0].tone == "good"
    assert rows[1].tone == "good"                       # затраты ниже прогноза — хорошо
    assert abs(accuracy(rows) - 90) < 1e-9              # оценка гостей в MAPE не входит
    assert Row("x", "", None, None, 5).deviation is None
