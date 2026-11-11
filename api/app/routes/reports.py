from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine import run as engine
from app.engine.model import to_per_100kg
from app.models import Commodity, Market, PriceReport, Reporter, UnitConversion
from app.schemas import ReportIn, ReportResult

router = APIRouter()


@router.post("/reports", response_model=ReportResult, status_code=201)
def submit_report(body: ReportIn, db: Session = Depends(get_db)):
    """Store a price report and update that market's proposal for the admin to review.

    Nothing becomes public here: an admin publishes prices from the dashboard.
    The reporter is not told whether their report looked like an outlier,
    so nobody can learn how to game the filter.
    """
    market = db.get(Market, body.market_id)
    commodity = db.get(Commodity, body.commodity_id)
    if not market or not commodity:
        raise HTTPException(status_code=404, detail="Unknown market or commodity")

    kg = commodity.kg_per_mudu
    override = db.get(UnitConversion, (market.id, commodity.id, "mudu"))
    if override:
        kg = override.kg_per_unit
    per_100kg = to_per_100kg(body.price, body.unit, kg)

    reporter_id, reporter_type = None, body.reporter_type
    if body.phone:
        reporter = db.scalar(select(Reporter).where(Reporter.phone == body.phone))
        if reporter is None:
            # New phones start as unverified farmers/traders; agents are created by admins.
            reporter = Reporter(phone=body.phone, market_id=market.id,
                                type="farmer" if body.reporter_type == "agent" else body.reporter_type)
            db.add(reporter)
            db.flush()
        reporter_id, reporter_type = reporter.id, reporter.type
    elif body.reporter_type == "agent":
        reporter_type = "farmer"  # an agent must identify themselves to get agent weight

    day = engine.today_lagos()
    report = PriceReport(reporter_id=reporter_id, reporter_type=reporter_type,
                         market_id=market.id, commodity_id=commodity.id, raw_price=body.price,
                         unit=body.unit, price_per_100kg=round(per_100kg, 2), trade_date=day,
                         lat=body.lat, lng=body.lng)
    db.add(report)
    db.flush()
    engine.propose_for(db, market, commodity.id, day)
    db.commit()
    return ReportResult(report_id=report.id, price_per_100kg=report.price_per_100kg,
                        status="received", published=None)
