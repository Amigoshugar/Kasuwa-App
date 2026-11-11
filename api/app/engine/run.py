"""Propose daily prices from raw reports. An admin reviews and publishes them.

Run by the scheduler at 12:00 and 18:00 Lagos time, and after every new report:
    python -m app.engine.run            # today
    python -m app.engine.run 2026-11-10 # a given day (re-runs are safe)

Nothing here makes a price public. Publishing happens in app/routes/admin.py.
"""
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.engine.model import STALE_AFTER, DailyResult, Report, compute_daily, gap_fill, is_big_move
from app.models import (Commodity, DailyPrice, Market, PriceProposal, PriceReport, Reporter,
                        ReportReview)


def today_lagos() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def is_trading(market: Market, day: date) -> bool:
    if market.trading_days == "daily":
        return True
    return str(day.weekday()) in market.trading_days.split(",")


def last_published(db: Session, market_id: str, commodity_id: str, before: date) -> DailyPrice | None:
    return db.scalar(select(DailyPrice).where(
        DailyPrice.market_id == market_id, DailyPrice.commodity_id == commodity_id,
        DailyPrice.date < before).order_by(DailyPrice.date.desc()).limit(1))


def trading_days_missed(market: Market, since: date, day: date) -> int:
    """Trading days after `since` up to and including `day`."""
    return sum(1 for k in range(1, (day - since).days + 1) if is_trading(market, since + timedelta(days=k)))


def anchor_ratio_for(db: Session, commodity_id: str, day: date) -> float:
    """Today's change at the anchor market (Dawanau): its proposal today vs its last published price."""
    anchor = db.scalar(select(Market).where(Market.is_anchor.is_(True)))
    if not anchor:
        return 1.0
    today_row = db.scalar(select(PriceProposal).where(
        PriceProposal.market_id == anchor.id, PriceProposal.commodity_id == commodity_id,
        PriceProposal.date == day))
    prev_row = last_published(db, anchor.id, commodity_id, day)
    if today_row and prev_row and prev_row.price and not today_row.is_estimated:
        return today_row.price / prev_row.price
    return 1.0


def propose_one(db: Session, market: Market, commodity_id: str, day: date,
                anchor_ratio: float = 1.0) -> PriceProposal | None:
    """Compute and save the proposed price for one market + commodity + day."""
    prev = last_published(db, market.id, commodity_id, day)

    rows = db.scalars(select(PriceReport).where(
        PriceReport.market_id == market.id, PriceReport.commodity_id == commodity_id,
        PriceReport.trade_date == day)).all()
    ids = [x.id for x in rows]
    decisions = {r.report_id: r.decision for r in db.scalars(
        select(ReportReview).where(ReportReview.report_id.in_(ids))).all()} if ids else {}
    trust_ids = [x.reporter_id for x in rows if x.reporter_id]
    trust = {r.id: r.trust for r in db.scalars(
        select(Reporter).where(Reporter.id.in_(trust_ids))).all()} if trust_ids else {}

    active = [Report(price=x.price_per_100kg, type=x.reporter_type,
                     trust=trust.get(x.reporter_id, 1.0), id=x.id)
              for x in rows if decisions.get(x.id) != "exclude"]
    forced = frozenset(i for i, d in decisions.items() if d == "include")

    result: DailyResult | None = compute_daily(active, prev.price if prev else None,
                                               force_accept=forced, hold_big_moves=False)
    status = {r.id: r.status for r in active}
    for x in rows:
        x.status = "excluded" if decisions.get(x.id) == "exclude" else status.get(x.id, "pending")

    if result is None and prev is not None:
        missed = trading_days_missed(market, prev.date, day)
        prev_result = DailyResult(prev.price, prev.low, prev.high, prev.n_reports, prev.confidence,
                                  prev.is_estimated, prev.reason)
        open_today = is_trading(market, day)
        result = gap_fill(prev_result, anchor_ratio, "noreports" if open_today else "closed",
                          missed if missed > STALE_AFTER else 0)

    existing = db.scalar(select(PriceProposal).where(
        PriceProposal.market_id == market.id, PriceProposal.commodity_id == commodity_id,
        PriceProposal.date == day))
    if result is None:
        if existing is not None:
            db.delete(existing)
        return None

    row = existing or PriceProposal(market_id=market.id, commodity_id=commodity_id, date=day)
    if existing is None:
        db.add(row)
    row.price, row.low, row.high = result.price, result.low, result.high
    row.n_reports, row.confidence = result.n_reports, result.confidence
    row.n_outliers = sum(1 for x in rows if x.status == "outlier")
    row.is_estimated, row.reason = result.is_estimated, result.reason
    row.big_move = (not result.is_estimated) and is_big_move(result.price, prev.price if prev else None)
    row.updated_at = datetime.now(ZoneInfo(settings.timezone))
    return row


def propose_for(db: Session, market: Market, commodity_id: str, day: date) -> PriceProposal | None:
    ratio = 1.0 if market.is_anchor else anchor_ratio_for(db, commodity_id, day)
    return propose_one(db, market, commodity_id, day, ratio)


def run(day: date | None = None) -> int:
    """Propose every market and commodity for one day. Returns proposals written."""
    day = day or today_lagos()
    written = 0
    with SessionLocal() as db:
        # anchor market first, so the others can follow its change
        markets = sorted(db.scalars(select(Market)).all(), key=lambda m: not m.is_anchor)
        commodities = db.scalars(select(Commodity)).all()
        for c in commodities:
            for m in markets:
                if propose_for(db, m, c.id, day) is not None:
                    written += 1
                db.flush()
        db.commit()
    return written


if __name__ == "__main__":
    target = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    n = run(target)
    print(f"Proposed {n} prices for {target or today_lagos()}. Review them in the admin dashboard.")
