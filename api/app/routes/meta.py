from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Commodity, Market
from app.schemas import CommodityOut, MarketOut

router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/markets", response_model=list[MarketOut])
def markets(db: Session = Depends(get_db)):
    return db.scalars(select(Market).order_by(Market.state, Market.name)).all()


@router.get("/commodities", response_model=list[CommodityOut])
def commodities(db: Session = Depends(get_db)):
    return db.scalars(select(Commodity).order_by(Commodity.name_en, Commodity.grade_en)).all()
