"""Tests for the price model. Every number here can be checked by hand."""
from datetime import date, timedelta

import pytest

from app.engine.model import (
    DailyResult, Report, compute_daily, confidence_level, forecast, gap_fill,
    to_per_100kg, weighted_quantile,
)


def test_units_convert_to_100kg():
    assert to_per_100kg(35000, "bag100", 1.6) == 35000
    assert to_per_100kg(17500, "bag50", 1.6) == 35000
    assert to_per_100kg(560, "mudu", 1.6) == pytest.approx(35000)
    with pytest.raises(ValueError):
        to_per_100kg(100, "tiya", 1.6)


def test_weighted_median_favours_agents():
    reps = [Report(30000, "farmer"), Report(36000, "agent"), Report(36500, "agent")]
    # weights 0.3, 0.9, 0.9 -> half of 2.1 is reached at the first agent
    assert weighted_quantile(reps, 0.5) == 36000


def test_outlier_is_set_aside():
    reps = [Report(35000, "agent"), Report(35400, "agent"), Report(34800, "trader"),
            Report(12000, "farmer")]
    res = compute_daily(reps, prev_price=35200)
    assert reps[-1].status == "outlier"
    assert all(r.status == "accepted" for r in reps[:3])
    assert 34800 <= res.price <= 35400
    assert res.n_reports == 3


def test_single_bad_report_cannot_move_price_against_yesterday():
    reps = [Report(20000, "trader")]
    res = compute_daily(reps, prev_price=35000)
    assert res is None
    assert reps[0].status == "outlier"


def test_big_move_without_agent_is_held():
    # Two traders agree on +25%. No agent, so held for confirmation.
    reps = [Report(43750, "trader"), Report(43800, "trader")]
    res = compute_daily(reps, prev_price=None)  # no anchor: z-filter passes them
    assert res is not None  # with no yesterday price there is nothing to compare
    reps2 = [Report(43750, "trader"), Report(43800, "trader"), Report(43700, "trader")]
    res2 = compute_daily(reps2, prev_price=35000)
    assert res2 is None or all(r.status in ("held", "outlier") for r in reps2)


def test_big_move_confirmed_by_agent_is_published():
    reps = [Report(43000, "agent"), Report(43500, "agent"), Report(43200, "trader"),
            Report(43400, "trader")]
    res = compute_daily(reps, prev_price=35000)
    assert res is not None
    assert res.price == pytest.approx(43200, rel=0.01)


def test_confidence_levels():
    many = [Report(35000 + i * 50, "agent") for i in range(5)]
    assert compute_daily(many, 35000).confidence >= 70
    one = [Report(35000, "farmer")]
    res = compute_daily(one, 35000)
    assert res.confidence == round(100 * (1 / 5) ** 0.5 * 0.7)  # 31
    assert confidence_level(res.confidence) == "low"


def test_gap_fill_follows_anchor_and_goes_stale():
    prev = DailyResult(price=30000, low=29000, high=31000, n_reports=3, confidence=80)
    est = gap_fill(prev, anchor_ratio=1.02, reason="noreports", missed_days=1)
    assert est.price == pytest.approx(30600)
    assert est.is_estimated and est.reason == "noreports"
    assert est.confidence == 48
    assert gap_fill(prev, 1.0, "noreports", missed_days=4).reason == "stale"


def test_forecast_follows_trend():
    start = date(2026, 10, 1)
    falling = [(start + timedelta(days=i), 40000 * (0.995 ** i), False) for i in range(30)]
    fc = forecast(falling)
    assert len(fc) == 7
    assert fc[-1].price < falling[-1][1]
    assert all(p.low < p.price < p.high for p in fc)


def test_admin_can_force_include_an_outlier():
    reps = [Report(35000, "agent", id=1), Report(35400, "agent", id=2), Report(12000, "farmer", id=3)]
    compute_daily(reps, prev_price=35200, force_accept=frozenset({3}))
    assert reps[2].status == "accepted"


def test_big_move_not_held_when_admin_reviews():
    reps = [Report(43750, "trader"), Report(43800, "trader"), Report(43700, "trader")]
    res = compute_daily(reps, prev_price=35000, hold_big_moves=False)
    assert res is not None and res.price == pytest.approx(43750, rel=0.01)
