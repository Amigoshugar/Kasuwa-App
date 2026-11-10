"""Kasuwa price model.

Pure functions with no database access, so they are easy to test.
Prices are always naira per 100 kg bag.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

# How much each kind of reporter counts towards the published price.
SOURCE_WEIGHT = {"sale": 1.0, "agent": 0.9, "trader": 0.6, "farmer": 0.3}

OUTLIER_Z = 3.5          # robust z-score above which a report is set aside
MAX_DAILY_MOVE = 0.20    # moves above 20% need an agent + 2 reporters
MAD_FLOOR = 0.02         # MAD never below 2% of the centre (avoids rejecting everything)
STALE_AFTER = 3          # trading days without reports before "No recent data"


@dataclass
class Report:
    price: float                      # naira per 100 kg
    type: str                         # sale | agent | trader | farmer
    trust: float = 1.0                # reporter's own track record, 0.2 - 1.2
    id: int | None = None
    status: str = "pending"           # accepted | outlier | held
    z: float = 0.0

    @property
    def weight(self) -> float:
        return SOURCE_WEIGHT[self.type] * self.trust


@dataclass
class DailyResult:
    price: float
    low: float
    high: float
    n_reports: int
    confidence: int
    is_estimated: bool = False
    reason: str | None = None          # closed | noreports | stale | held


def to_per_100kg(price: float, unit: str, kg_per_mudu: float) -> float:
    """Convert a reported price to naira per 100 kg bag."""
    if unit == "bag100":
        return price
    if unit == "bag50":
        return price * 2
    if unit == "mudu":
        if kg_per_mudu <= 0:
            raise ValueError("kg_per_mudu must be positive")
        return price / kg_per_mudu * 100
    raise ValueError(f"unknown unit: {unit}")


def weighted_quantile(reports: list[Report], q: float) -> float:
    items = sorted(reports, key=lambda r: r.price)
    total = sum(r.weight for r in items)
    running = 0.0
    for r in items:
        running += r.weight
        if running >= total * q:
            return r.price
    return items[-1].price


def compute_daily(reports: list[Report], prev_price: float | None) -> DailyResult | None:
    """Turn one day's reports for one market and commodity into a published price.

    Sets each report's status. Returns None when nothing can be published
    (no reports, all outliers, or a large move that is not confirmed).
    """
    if not reports:
        return None

    prices = [r.price for r in reports]
    # Yesterday's price joins the centre twice so one or two bad reports cannot move it.
    base = prices + ([prev_price, prev_price] if prev_price else [])
    centre = median(base)
    mad = max(median([abs(p - centre) for p in base]), MAD_FLOOR * centre)

    for r in reports:
        r.z = 0.6745 * (r.price - centre) / mad
        r.status = "outlier" if abs(r.z) > OUTLIER_Z else "accepted"

    accepted = [r for r in reports if r.status == "accepted"]
    if not accepted:
        return None

    price = weighted_quantile(accepted, 0.5)
    low = min(weighted_quantile(accepted, 0.25), price)
    high = max(weighted_quantile(accepted, 0.75), price)

    if prev_price and abs(price / prev_price - 1) > MAX_DAILY_MOVE:
        has_agent = any(r.type in ("agent", "sale") for r in accepted)
        if not (has_agent and len(accepted) >= 2):
            for r in accepted:
                r.status = "held"
            return None

    return DailyResult(
        price=round(price, 2),
        low=round(low, 2),
        high=round(high, 2),
        n_reports=len(accepted),
        confidence=confidence(accepted, price, low, high),
    )


def confidence(accepted: list[Report], price: float, low: float, high: float) -> int:
    """0-100. More reporters and closer agreement raise it; no agent lowers it."""
    n = len(accepted)
    spread = (high - low) / (0.3 * price) if price else 1
    has_trusted = any(r.type in ("agent", "sale") for r in accepted)
    score = 100 * math.sqrt(min(1, n / 5)) * (1 - min(1, spread)) * (1.0 if has_trusted else 0.7)
    return round(score)


def confidence_level(score: int) -> str:
    return "high" if score >= 70 else "medium" if score >= 40 else "low"


def gap_fill(prev: DailyResult, anchor_ratio: float, reason: str, missed_days: int) -> DailyResult:
    """Estimate a price when a market has no usable reports.

    Carries yesterday's price forward, moved by today's change at the anchor market (Dawanau).
    """
    half_spread = max((prev.high - prev.low) / prev.price / 2, 0.03) * 1.15
    price = prev.price * anchor_ratio
    return DailyResult(
        price=round(price, 2),
        low=round(price * (1 - half_spread), 2),
        high=round(price * (1 + half_spread), 2),
        n_reports=0,
        confidence=max(5, round(prev.confidence * 0.6)),
        is_estimated=True,
        reason="stale" if missed_days > STALE_AFTER else reason,
    )


@dataclass
class ForecastPoint:
    date: date
    price: float
    low: float
    high: float


def forecast(history: list[tuple[date, float, bool]], days: int = 7) -> list[ForecastPoint]:
    """Phase-1 forecast: damped trend of the last 28 days with a 90% band.

    history: list of (date, price, is_estimated), oldest first.
    """
    if not history:
        return []
    recent = history[-28:]
    use = [h for h in recent if not h[2]] or recent
    last_date, last_price = history[-1][0], history[-1][1]

    xs = [(d - last_date).days for d, _, _ in use]
    ys = [math.log(p) for _, p, _ in use]
    slope = 0.0
    if len(xs) >= 2:
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        den = sum((x - mx) ** 2 for x in xs)
        if den:
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den

    prices = [p for _, p, _ in recent]
    diffs = [math.log(b / a) for a, b in zip(prices, prices[1:])]
    sd = math.sqrt(sum(d * d for d in diffs) / len(diffs)) if diffs else 0.01
    sd = sd or 0.01

    out = []
    for k in range(1, days + 1):
        p = last_price * math.exp(slope * 0.7 * k)
        band = 1.64 * sd * math.sqrt(k)
        out.append(ForecastPoint(last_date + timedelta(days=k), round(p, 2),
                                 round(p * math.exp(-band), 2), round(p * math.exp(band), 2)))
    return out
