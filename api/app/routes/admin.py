"""Admin dashboard API: review proposed prices and reports, then publish.

Every endpoint here needs the X-Admin-Token header (the ADMIN_TOKEN setting).
"""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.engine import run as engine
from app.engine.model import confidence_level
from app.models import (DailyPrice, Market, PriceProposal, PriceReport, PublishLog, Reporter,
                        ReportReview)
from app.schemas import (AdminReportOut, LogOut, PublishIn, QueueItem, ReviewIn, UnpublishIn)

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def _queue_item(db: Session, p: PriceProposal) -> QueueItem:
    prev = engine.last_published(db, p.market_id, p.commodity_id, p.date)
    pub = db.scalar(select(DailyPrice).where(
        DailyPrice.market_id == p.market_id, DailyPrice.commodity_id == p.commodity_id,
        DailyPrice.date == p.date))
    status = "needs_review"
    if pub is not None:
        last_log = db.scalar(select(PublishLog).where(
            PublishLog.market_id == p.market_id, PublishLog.commodity_id == p.commodity_id,
            PublishLog.date == p.date, PublishLog.action == "publish")
            .order_by(PublishLog.id.desc()).limit(1))
        changed = last_log is not None and last_log.proposed_price is not None \
            and abs(last_log.proposed_price - p.price) > 0.5
        status = "changed" if changed else "published"
    return QueueItem(market_id=p.market_id, commodity_id=p.commodity_id, date=p.date,
                     proposed_price=p.price, low=p.low, high=p.high, confidence=p.confidence,
                     confidence_level=confidence_level(p.confidence), n_reports=p.n_reports,
                     n_outliers=p.n_outliers, is_estimated=p.is_estimated, reason=p.reason,
                     big_move=p.big_move, prev_price=prev.price if prev else None,
                     prev_date=prev.date if prev else None,
                     published_price=pub.price if pub else None, status=status)


def _mask(phone: str | None) -> str | None:
    if not phone:
        return None
    return "****" + phone[-4:] if len(phone) > 4 else "****"


@router.get("/check")
def check() -> dict:
    """Used by the dashboard login: 200 means the password is right."""
    return {"ok": True}


@router.get("/queue", response_model=list[QueueItem])
def queue(day: dt.date | None = None, db: Session = Depends(get_db)):
    day = day or engine.today_lagos()
    rows = db.scalars(select(PriceProposal).where(PriceProposal.date == day)
                      .order_by(PriceProposal.commodity_id, PriceProposal.market_id)).all()
    return [_queue_item(db, p) for p in rows]


@router.post("/propose")
def propose(day: dt.date | None = None):
    """Recompute every proposal for a day (the scheduled job calls this too)."""
    day = day or engine.today_lagos()
    return {"proposed": engine.run(day), "day": str(day)}


@router.get("/reports", response_model=list[AdminReportOut])
def reports(market: str, commodity: str, day: dt.date | None = None, db: Session = Depends(get_db)):
    day = day or engine.today_lagos()
    rows = db.scalars(select(PriceReport).where(
        PriceReport.market_id == market, PriceReport.commodity_id == commodity,
        PriceReport.trade_date == day).order_by(PriceReport.id.desc())).all()
    ids = [r.id for r in rows]
    decisions = {r.report_id: r.decision for r in db.scalars(
        select(ReportReview).where(ReportReview.report_id.in_(ids))).all()} if ids else {}
    rep_ids = [r.reporter_id for r in rows if r.reporter_id]
    reporters = {r.id: r for r in db.scalars(
        select(Reporter).where(Reporter.id.in_(rep_ids))).all()} if rep_ids else {}
    out = []
    for r in rows:
        who = reporters.get(r.reporter_id)
        out.append(AdminReportOut(id=r.id, reporter_type=r.reporter_type,
                                  phone=_mask(who.phone) if who else None,
                                  trust=who.trust if who else 1.0, raw_price=r.raw_price, unit=r.unit,
                                  price_per_100kg=r.price_per_100kg, status=r.status,
                                  decision=decisions.get(r.id), reported_at=r.reported_at))
    return out


@router.post("/reports/{report_id}/review", response_model=QueueItem | None)
def review(report_id: int, body: ReviewIn, db: Session = Depends(get_db)):
    """Include or exclude one report, then recompute that market's proposal."""
    rep = db.get(PriceReport, report_id)
    if rep is None:
        raise HTTPException(status_code=404, detail="Report not found")
    existing = db.get(ReportReview, report_id)
    if body.decision == "auto":
        if existing is not None:
            db.delete(existing)
    elif existing is None:
        db.add(ReportReview(report_id=report_id, decision=body.decision))
    else:
        existing.decision = body.decision
    db.flush()
    market = db.get(Market, rep.market_id)
    proposal = engine.propose_for(db, market, rep.commodity_id, rep.trade_date)
    db.commit()
    return _queue_item(db, proposal) if proposal else None


@router.post("/publish")
def publish(body: PublishIn, db: Session = Depends(get_db)):
    """Copy proposals into the public daily prices. A given price overrides the proposal."""
    day = body.day or engine.today_lagos()
    done = []
    for item in body.items:
        p = db.scalar(select(PriceProposal).where(
            PriceProposal.market_id == item.market_id, PriceProposal.commodity_id == item.commodity_id,
            PriceProposal.date == day))
        if p is None:
            raise HTTPException(status_code=404,
                                detail=f"No proposal for {item.market_id} / {item.commodity_id} on {day}")
        price = item.price or p.price
        row = db.scalar(select(DailyPrice).where(
            DailyPrice.market_id == p.market_id, DailyPrice.commodity_id == p.commodity_id,
            DailyPrice.date == day))
        if row is None:
            row = DailyPrice(market_id=p.market_id, commodity_id=p.commodity_id, date=day)
            db.add(row)
        row.price, row.low, row.high = round(price, 2), min(p.low, price), max(p.high, price)
        row.n_reports, row.confidence = p.n_reports, p.confidence
        row.is_estimated, row.reason = p.is_estimated, p.reason
        db.add(PublishLog(market_id=p.market_id, commodity_id=p.commodity_id, date=day,
                          action="publish", price=row.price, proposed_price=p.price, note=item.note))
        done.append(f"{p.market_id}/{p.commodity_id}")
    db.commit()
    return {"published": len(done), "day": str(day), "items": done}


@router.post("/unpublish")
def unpublish(body: UnpublishIn, db: Session = Depends(get_db)):
    day = body.day or engine.today_lagos()
    row = db.scalar(select(DailyPrice).where(
        DailyPrice.market_id == body.market_id, DailyPrice.commodity_id == body.commodity_id,
        DailyPrice.date == day))
    if row is None:
        raise HTTPException(status_code=404, detail="Nothing published for that market and day")
    db.add(PublishLog(market_id=body.market_id, commodity_id=body.commodity_id, date=day,
                      action="unpublish", price=row.price, proposed_price=None, note=body.note))
    db.delete(row)
    db.commit()
    return {"unpublished": 1, "day": str(day)}


@router.get("/log", response_model=list[LogOut])
def log(days: int = Query(14, ge=1, le=365), db: Session = Depends(get_db)):
    since = engine.today_lagos() - dt.timedelta(days=days)
    rows = db.scalars(select(PublishLog).where(PublishLog.date > since)
                      .order_by(PublishLog.id.desc()).limit(500)).all()
    return [LogOut(market_id=r.market_id, commodity_id=r.commodity_id, date=r.date, action=r.action,
                   price=r.price, proposed_price=r.proposed_price, note=r.note, created_at=r.created_at)
            for r in rows]
