"""Database tables. Raw reports are never edited, so every price can be traced back."""
import datetime as dt

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer, String,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Market(Base):
    __tablename__ = "markets"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)        # e.g. "dawanau"
    name: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(40))
    lga: Mapped[str | None] = mapped_column(String(80))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    # "daily" or weekday numbers Mon=0 ... Sun=6, comma-separated, e.g. "3" or "0,3"
    trading_days: Mapped[str] = mapped_column(String(20), default="daily")
    is_anchor: Mapped[bool] = mapped_column(Boolean, default=False)


class Commodity(Base):
    __tablename__ = "commodities"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)        # e.g. "maize-white"
    name_en: Mapped[str] = mapped_column(String(60))
    name_ha: Mapped[str] = mapped_column(String(60))
    grade_en: Mapped[str] = mapped_column(String(60), default="")
    grade_ha: Mapped[str] = mapped_column(String(60), default="")
    kg_per_mudu: Mapped[float] = mapped_column(Float, default=1.6)       # default, overridden per market


class UnitConversion(Base):
    """Measured weight of a unit (mudu, tiya) for one commodity in one market."""
    __tablename__ = "unit_conversions"
    market_id: Mapped[str] = mapped_column(ForeignKey("markets.id"), primary_key=True)
    commodity_id: Mapped[str] = mapped_column(ForeignKey("commodities.id"), primary_key=True)
    unit: Mapped[str] = mapped_column(String(20), primary_key=True)
    kg_per_unit: Mapped[float] = mapped_column(Float)
    measured_on: Mapped[dt.date | None] = mapped_column(Date)


class Reporter(Base):
    __tablename__ = "reporters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(10))                        # agent | trader | farmer
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    market_id: Mapped[str | None] = mapped_column(ForeignKey("markets.id"))
    trust: Mapped[float] = mapped_column(Float, default=1.0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class PriceReport(Base):
    __tablename__ = "price_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_id: Mapped[int | None] = mapped_column(ForeignKey("reporters.id"))
    reporter_type: Mapped[str] = mapped_column(String(10))
    market_id: Mapped[str] = mapped_column(ForeignKey("markets.id"), index=True)
    commodity_id: Mapped[str] = mapped_column(ForeignKey("commodities.id"), index=True)
    raw_price: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(10))                        # bag100 | bag50 | mudu
    price_per_100kg: Mapped[float] = mapped_column(Float)
    trade_date: Mapped[dt.date] = mapped_column(Date, index=True)           # market day in Lagos time
    reported_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(10), default="pending")   # accepted | outlier | held


class DailyPrice(Base):
    __tablename__ = "daily_prices"
    __table_args__ = (UniqueConstraint("market_id", "commodity_id", "date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[str] = mapped_column(ForeignKey("markets.id"), index=True)
    commodity_id: Mapped[str] = mapped_column(ForeignKey("commodities.id"), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    price: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    n_reports: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(String(12))
    missed_days: Mapped[int] = mapped_column(Integer, default=0)
    model_version: Mapped[str] = mapped_column(String(10), default="v1")
