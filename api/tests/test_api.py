"""End-to-end API tests on a throwaway SQLite database."""
import os
from datetime import timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_kasuwa.db"
os.environ["ADMIN_TOKEN"] = "test-token"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.engine import run as engine_run  # noqa: E402
from app.main import app  # noqa: E402
from app.models import DailyPrice  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    seed()
    yield
    Base.metadata.drop_all(engine)


client = TestClient(app)


def post(market, price, kind="agent", phone=None, unit="bag100"):
    return client.post("/reports", json={"market_id": market, "commodity_id": "maize-white",
                                         "price": price, "unit": unit, "reporter_type": kind,
                                         "phone": phone})


def test_health_and_reference_data():
    assert client.get("/health").json() == {"status": "ok"}
    assert len(client.get("/markets").json()) == 18
    assert len(client.get("/commodities").json()) == 12


def test_report_publishes_price_and_flags_outlier():
    r1 = post("dawanau", 35000, "trader", "08011111111")
    assert r1.status_code == 201
    assert r1.json()["published"]["price"] == 35000
    post("dawanau", 35400, "trader", "08022222222")
    post("dawanau", 34800, "trader", "08033333333")
    bad = post("dawanau", 9000, "farmer", "08044444444")
    assert bad.json()["status"] == "outlier"
    today = client.get("/prices/today", params={"commodity": "maize-white"}).json()
    assert today[0]["market_id"] == "dawanau"
    assert 34800 <= today[0]["price"] <= 35400


def test_mudu_is_converted():
    r = post("giwa", 560, "farmer", "08055555555", unit="mudu")
    assert r.json()["price_per_100kg"] == pytest.approx(35000)


def test_unknown_market_is_rejected():
    assert post("nowhere", 35000).status_code == 404


def test_engine_needs_token_and_fills_gaps():
    day = engine_run.today_lagos()
    with SessionLocal() as db:  # yesterday's price exists, no reports today
        db.add(DailyPrice(market_id="kawo", commodity_id="maize-white",
                          date=day - timedelta(days=1), price=36000, low=35500, high=36500,
                          n_reports=4, confidence=80))
        db.commit()
    assert client.post("/engine/run").status_code == 401
    r = client.post("/engine/run", headers={"X-Admin-Token": "test-token"})
    assert r.status_code == 200
    hist = client.get("/prices/history", params={"market": "kawo", "commodity": "maize-white"}).json()
    assert hist[-1]["is_estimated"] is True
    assert hist[-1]["reason"] == "noreports"
    fc = client.get("/forecast", params={"market": "kawo", "commodity": "maize-white"}).json()
    assert len(fc) == 7
