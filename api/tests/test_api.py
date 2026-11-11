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

ADMIN = {"X-Admin-Token": "test-token"}


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    seed()
    yield
    Base.metadata.drop_all(engine)


client = TestClient(app)


def post(market, price, kind="trader", phone=None, unit="bag100", commodity="maize-white"):
    return client.post("/reports", json={"market_id": market, "commodity_id": commodity,
                                         "price": price, "unit": unit, "reporter_type": kind,
                                         "phone": phone})


def queue_item(market, commodity="maize-white"):
    items = client.get("/admin/queue", headers=ADMIN).json()
    return next((i for i in items if i["market_id"] == market and i["commodity_id"] == commodity), None)


def publish(market, price=None, commodity="maize-white"):
    item = {"market_id": market, "commodity_id": commodity}
    if price:
        item["price"] = price
    return client.post("/admin/publish", json={"items": [item]}, headers=ADMIN)


def test_health_and_reference_data():
    assert client.get("/health").json() == {"status": "ok"}
    assert len(client.get("/markets").json()) == 18
    assert len(client.get("/commodities").json()) == 12


def test_report_goes_to_queue_not_public():
    r = post("dawanau", 35000, phone="08011111111")
    assert r.status_code == 201
    assert r.json()["status"] == "received"
    assert r.json()["published"] is None
    # nothing public yet
    assert client.get("/prices/today", params={"commodity": "maize-white"}).json() == []
    # but the admin sees a proposal
    item = queue_item("dawanau")
    assert item["proposed_price"] == 35000
    assert item["status"] == "needs_review"


def test_admin_endpoints_need_the_password():
    assert client.get("/admin/queue").status_code == 401
    assert client.get("/admin/queue", headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert client.get("/admin/check", headers=ADMIN).json() == {"ok": True}
    assert client.post("/engine/run").status_code == 401


def test_publish_makes_price_public_and_logs_it():
    post("dawanau", 35000, phone="08011111111")
    post("dawanau", 35400, phone="08022222222")
    assert publish("dawanau").json()["published"] == 1
    today = client.get("/prices/today", params={"commodity": "maize-white"}).json()
    assert today[0]["market_id"] == "dawanau"
    assert 35000 <= today[0]["price"] <= 35400
    assert queue_item("dawanau")["status"] == "published"
    log = client.get("/admin/log", headers=ADMIN).json()
    assert log[0]["action"] == "publish"


def test_publish_with_override_price():
    post("giwa", 33000, phone="08033333333")
    publish("giwa", price=32500)
    today = client.get("/prices/today", params={"commodity": "maize-white"}).json()
    assert today[0]["price"] == 32500
    log = client.get("/admin/log", headers=ADMIN).json()
    assert log[0]["proposed_price"] == 33000 and log[0]["price"] == 32500


def test_new_report_after_publish_shows_changed():
    post("dawanau", 35000, phone="08011111111")
    publish("dawanau")
    # two higher reports move the weighted median from 35,000 to 38,000
    post("dawanau", 38000, phone="08022222222")
    post("dawanau", 38500, phone="08033333333")
    item = queue_item("dawanau")
    assert item["proposed_price"] == 38000
    assert item["status"] == "changed"


def test_outlier_flagged_and_admin_can_exclude_or_include():
    for i, p in enumerate([35000, 35400, 34800]):
        post("dawanau", p, phone=f"0801000000{i}")
    post("dawanau", 9000, kind="farmer", phone="08044444444")
    reports = client.get("/admin/reports", params={"market": "dawanau", "commodity": "maize-white"},
                         headers=ADMIN).json()
    bad = next(r for r in reports if r["price_per_100kg"] == 9000)
    assert bad["status"] == "outlier"
    assert bad["phone"] == "****4444"
    assert queue_item("dawanau")["n_outliers"] == 1

    good = next(r for r in reports if r["price_per_100kg"] == 35400)
    item = client.post(f"/admin/reports/{good['id']}/review", json={"decision": "exclude"},
                       headers=ADMIN).json()
    assert item["n_reports"] == 2
    item = client.post(f"/admin/reports/{bad['id']}/review", json={"decision": "include"},
                       headers=ADMIN).json()
    assert item["n_reports"] == 3
    item = client.post(f"/admin/reports/{good['id']}/review", json={"decision": "auto"},
                       headers=ADMIN).json()
    assert item["n_reports"] == 4


def test_unpublish_removes_public_price():
    post("dawanau", 35000, phone="08011111111")
    publish("dawanau")
    r = client.post("/admin/unpublish", json={"market_id": "dawanau", "commodity_id": "maize-white"},
                    headers=ADMIN)
    assert r.status_code == 200
    assert client.get("/prices/today", params={"commodity": "maize-white"}).json() == []
    assert client.get("/admin/log", headers=ADMIN).json()[0]["action"] == "unpublish"


def test_mudu_is_converted():
    r = post("giwa", 560, "farmer", "08055555555", unit="mudu")
    assert r.json()["price_per_100kg"] == pytest.approx(35000)


def test_unknown_market_is_rejected():
    assert post("nowhere", 35000).status_code == 404


def test_engine_proposes_gap_fill_from_published_price():
    day = engine_run.today_lagos()
    with SessionLocal() as db:  # yesterday's published price exists, no reports today
        db.add(DailyPrice(market_id="kawo", commodity_id="maize-white",
                          date=day - timedelta(days=1), price=36000, low=35500, high=36500,
                          n_reports=4, confidence=80))
        db.commit()
    r = client.post("/engine/run", headers=ADMIN)
    assert r.status_code == 200 and r.json()["proposed"] >= 1
    item = queue_item("kawo")
    assert item["is_estimated"] is True and item["reason"] == "noreports"
    assert item["prev_price"] == 36000
    fc = client.get("/forecast", params={"market": "kawo", "commodity": "maize-white"}).json()
    assert len(fc) == 7


def test_prices_all_returns_only_published():
    post("dawanau", 35000, phone="08066666666")
    post("giwa", 33000, phone="08077777777")
    publish("dawanau")
    rows = client.get("/prices/all", params={"days": 30}).json()
    assert {r["market_id"] for r in rows} == {"dawanau"}
