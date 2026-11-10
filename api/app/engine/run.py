"""Publish daily prices from raw reports.

Run by the scheduler at 12:00 (provisional) and 18:00 (final), Lagos time:
    python -m app.engine.run            # today
    python -m app.engine.run 2026-11-10 # a given day (re-runs are safe)
"""
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.engine.model import DailyResult, Report, compute_daily, gap_fill
from app.models import Commodity, DailyPrice, Market, PriceReport, Reporter


def today_lagos() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def is_trading(market: Market, day: date) -> bool:
    if market.trading_days == "daily":
        return True
    return str(day.weekday()) in market.trading_days.split(",")


def _as_result(row: DailyPrice) -> DailyResult:
    return DailyResult(row.price, row.low, row.high, row.n_reports, row.confidence,
                       row.is_estimated, row.reason)


def publish_one(db: Session, market: Market, commodity_id: str, day: date,
                anchor_ratio: float = 1.0) -> DailyPrice | None:
    """Compute and save the price for one market + commodity + day."""
    prev = db.scalar(select(DailyPrice).where(
        DailyPrice.market_id == market.id, DailyPrice.commodity_id == commodity_id,
        DailyPrice.date < day).order_by(DailyPrice.date.desc()).limit(1))

    rows = db.scalars(select(PriceReport).where(
        PriceReport.market_id == market.id, PriceReport.commodity_id == commodity_id,
        PriceReport.trade_date == day)).all()

    trust = {r.id: r.trust for r in db.scalars(select(Reporter).where(
        Reporter.id.in_([x.reporter_id for x in rows if x.reporter_id]))).all()} if rows else {}
    reports = [Report(price=x.price_per_100kg, type=x.reporter_type,
                      trust=trust.get(x.reporter_id, 1.0), id=x.id) for x in rows]

    open_today = is_trading(market, day)
    result = compute_daily(reports, prev.price if prev else None)
    missed = 0
    if result is None:
        if prev is None:
            for x in rows:  # keep statuses even when nothing is published
                x.status = next(r.status for r in reports if r.id == x.id)
            return None
        missed = prev.missed_days + (1 if open_today else 0)
        result = gap_fill(_as_result(prev), anchor_ratio,
                          "noreports" if open_today else "closed", missed)
        if reports and any(r.status == "held" for r in reports):
            result.reason = "held"

    for x in rows:
        x.status = next(r.status for r in reports if r.id == x.id)

    row = db.scalar(select(DailyPrice).where(
        DailyPrice.market_id == market.id, DailyPrice.commodity_id == commodity_id,
        DailyPrice.date == day))
    if row is None:
        row = DailyPrice(market_id=market.id, commodity_id=commodity_id, date=day)
        db.add(row)
    row.price, row.low, row.high = result.price, result.low, result.high
    row.n_reports, row.confidence = result.n_reports, result.confidence
    row.is_estimated, row.reason, row.missed_days = result.is_estimated, result.reason, missed
    return row


def anchor_ratio_for(db: Session, commodity_id: str, day: date) -> float:
    anchor = db.scalar(select(Market).where(Market.is_anchor.is_(True)))
    if not anchor:
        return 1.0
    today_row = db.scalar(select(DailyPrice).where(
        DailyPrice.market_id == anchor.id, DailyPrice.commodity_id == commodity_id,
        DailyPrice.date == day))
    prev_row = db.scalar(select(DailyPrice).where(
        DailyPrice.market_id == anchor.id, DailyPrice.commodity_id == commodity_id,
        DailyPrice.date < day).order_by(DailyPrice.date.desc()).limit(1))
    if today_row and prev_row and prev_row.price:
        return today_row.price / prev_row.price
    return 1.0


def run(day: date | None = None) -> int:
    """Publish every market and commodity for one day. Returns rows written."""
    day = day or today_lagos()
    written = 0
    with SessionLocal() as db:
        # anchor market first, so the others can follow its change
        markets = sorted(db.scalars(select(Market)).all(), key=lambda m: not m.is_anchor)
        commodities = db.scalars(select(Commodity)).all()
        for c in commodities:
            for m in markets:
                ratio = 1.0 if m.is_anchor else anchor_ratio_for(db, c.id, day)
                if publish_one(db, m, c.id, day, ratio) is not None:
                    written += 1
                db.flush()
        db.commit()
    return written


if __name__ == "__main__":
    target = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    n = run(target)
    print(f"Published {n} prices for {target or today_lagos()}.")
