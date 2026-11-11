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


class ReportOut(BaseModel):
    """A report as shown publicly: no phone numbers or reporter ids."""
    id: int
    reporter_type: str
    price_per_100kg: float
    unit: str
    status: str
    reported_at: dt.datetime


class ForecastOut(BaseModel):
    date: dt.date
    price: float
    low: float
    high: float


class QueueItem(BaseModel):
    market_id: str
    commodity_id: str
    date: dt.date
    proposed_price: float
    low: float
    high: float
    confidence: int
    confidence_level: str
    n_reports: int
    n_outliers: int
    is_estimated: bool
    reason: str | None
    big_move: bool
    prev_price: float | None
    prev_date: dt.date | None
    published_price: float | None
    status: Literal["needs_review", "published", "changed"]


class AdminReportOut(BaseModel):
    id: int
    reporter_type: str
    phone: str | None            # masked, e.g. ****5678
    trust: float
    raw_price: float
    unit: str
    price_per_100kg: float
    status: str
    decision: str | None
    reported_at: dt.datetime


class ReviewIn(BaseModel):
    decision: Literal["include", "exclude", "auto"]


class PublishItem(BaseModel):
    market_id: str
    commodity_id: str
    price: float | None = Field(default=None, gt=0, lt=10_000_000, description="Override the proposed price")
    note: str | None = Field(default=None, max_length=200)


class PublishIn(BaseModel):
    day: dt.date | None = None
    items: list[PublishItem] = Field(min_length=1, max_length=500)


class UnpublishIn(BaseModel):
    day: dt.date | None = None
    market_id: str
    commodity_id: str
    note: str | None = Field(default=None, max_length=200)


class LogOut(BaseModel):
    market_id: str
    commodity_id: str
    date: dt.date
    action: str
    price: float | None
    proposed_price: float | None
    note: str | None
    created_at: dt.datetime
