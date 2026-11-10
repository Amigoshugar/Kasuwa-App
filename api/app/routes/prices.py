from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.engine import run as engine_run
from app.engine.model import confidence_level, forecast
from app.models import DailyPrice, Market
from app.schemas import ForecastOut, PriceOut

router = APIRouter()


def to_out(row: DailyPrice) -> PriceOut:
    return PriceOut(market_id=row.market_id, commodity_id=row.commodity_id, date=row.date,
                    price=row.price, low=row.low, high=row.high, n_reports=row.n_reports,
                    confidence=row.confidence, confidence_level=confidence_level(row.confidence),
                    is_estimated=row.is_estimated, reason=row.reason)


@router.get("/prices/today", response_model=list[PriceOut])
def prices_today(commodity: str, state: str | None = None, db: Session = Depends(get_db)):
    """Latest published price for every market, for one commodity."""
    latest = (select(DailyPrice.market_id, func.max(DailyPrice.date).label("d"))
              .where(DailyPrice.commodity_id == commodity)
              .group_by(DailyPrice.market_id).subquery())
    q = (select(DailyPrice).join(latest, (DailyPrice.market_id == latest.c.market_id)
                                 & (DailyPrice.date == latest.c.d))
         .where(DailyPrice.commodity_id == commodity))
    if state:
        q = q.join(Market, Market.id == DailyPrice.market_id).where(Market.state == state)
    return [to_out(r) for r in db.scalars(q.order_by(DailyPrice.price)).all()]


@router.get("/prices/history", response_model=list[PriceOut])
def prices_history(market: str, commodity: str, days: int = Query(90, ge=1, le=730),
                   db: Session = Depends(get_db)):
    since = engine_run.today_lagos() - timedelta(days=days)
    rows = db.scalars(select(DailyPrice).where(
        DailyPrice.market_id == market, DailyPrice.commodity_id == commodity,
        DailyPrice.date > since).order_by(DailyPrice.date)).all()
    return [to_out(r) for r in rows]


@router.get("/forecast", response_model=list[ForecastOut])
def get_forecast(market: str, commodity: str, db: Session = Depends(get_db)):
    rows = db.scalars(select(DailyPrice).where(
        DailyPrice.market_id == market, DailyPrice.commodity_id == commodity)
        .order_by(DailyPrice.date.desc()).limit(60)).all()
    history = [(r.date, r.price, r.is_estimated) for r in reversed(rows)]
    return [ForecastOut(date=p.date, price=p.price, low=p.low, high=p.high)
            for p in forecast(history)]


@router.post("/engine/run")
def run_engine(day: date | None = None, x_admin_token: str = Header(default="")):
    """Re-publish all prices for a day. Needs the X-Admin-Token header."""
    if x_admin_token != settings.admin_token or settings.admin_token == "change-me":
        raise HTTPException(status_code=401, detail="Admin token missing or wrong")
    n = engine_run.run(day)
    return {"published": n, "day": str(day or engine_run.today_lagos())}
