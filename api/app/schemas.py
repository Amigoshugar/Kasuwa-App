import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class MarketOut(BaseModel):
    id: str
    name: str
    state: str
    trading_days: str
    is_anchor: bool


class CommodityOut(BaseModel):
    id: str
    name_en: str
    name_ha: str
    grade_en: str
    grade_ha: str
    kg_per_mudu: float


class ReportIn(BaseModel):
    market_id: str
    commodity_id: str
    price: float = Field(gt=0, lt=10_000_000, description="Price as seen, in naira")
    unit: Literal["bag100", "bag50", "mudu"] = "bag100"
    reporter_type: Literal["agent", "trader", "farmer"] = "farmer"
    phone: str | None = Field(default=None, max_length=20)
    lat: float | None = None
    lng: float | None = None


class PriceOut(BaseModel):
    market_id: str
    commodity_id: str
    date: dt.date
    price: float
    low: float
    high: float
    n_reports: int
    confidence: int
    confidence_level: str
    is_estimated: bool
    reason: str | None


class ReportResult(BaseModel):
    report_id: int
    price_per_100kg: float
    status: str
    published: PriceOut | None


class ForecastOut(BaseModel):
    date: dt.date
    price: float
    low: float
    high: float
