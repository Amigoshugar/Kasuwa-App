"""Load markets and commodities. Safe to run more than once.

Run:  python -m app.seed
Market trading days below are PLACEHOLDERS - replace with each market's real day.
Mudu weights are rough defaults - replace with weights measured in each market.
"""
from app.db import Base, SessionLocal, engine
from app.models import Commodity, Market

MARKETS = [
    # id, name, state, trading_days, is_anchor
    ("dawanau", "Dawanau", "Kano", "daily", True),
    ("singer", "Singer", "Kano", "daily", False),
    ("bichi", "Bichi", "Kano", "2", False),
    ("gwarzo", "Gwarzo", "Kano", "3", False),
    ("kura", "Kura", "Kano", "0", False),
    ("wudil", "Wudil", "Kano", "3", False),
    ("giwa", "Giwa", "Kaduna", "3", False),
    ("makarfi", "Makarfi", "Kaduna", "1", False),
    ("zaria", "Zaria (Sabon Gari)", "Kaduna", "daily", False),
    ("ikara", "Ikara", "Kaduna", "4", False),
    ("saminaka", "Saminaka", "Kaduna", "3", False),
    ("kawo", "Kawo (Kaduna city)", "Kaduna", "daily", False),
    ("charanchi", "Charanchi", "Katsina", "6", False),
    ("funtua", "Funtua", "Katsina", "daily", False),
    ("dandume", "Dandume", "Katsina", "3", False),
    ("malumfashi", "Malumfashi", "Katsina", "5", False),
    ("jibia", "Jibia", "Katsina", "2", False),
    ("katsina", "Katsina central", "Katsina", "daily", False),
]

COMMODITIES = [
    # id, name_en, name_ha, grade_en, grade_ha, kg_per_mudu
    ("maize-white", "Maize", "Masara", "White", "Fara", 1.6),
    ("maize-yellow", "Maize", "Masara", "Yellow", "Rawaya", 1.6),
    ("sorghum-white", "Sorghum", "Dawa", "White", "Fara", 1.6),
    ("sorghum-red", "Sorghum", "Dawa", "Red", "Ja", 1.6),
    ("soybeans", "Soybeans", "Waken soya", "", "", 1.4),
    ("sesame-white", "Sesame", "Ridi", "White", "Fari", 1.3),
    ("sesame-mixed", "Sesame", "Ridi", "Mixed", "Gauraye", 1.3),
    ("beans-white", "Beans", "Wake", "White", "Fari", 1.7),
    ("beans-brown", "Beans", "Wake", "Brown (drum)", "Ja", 1.7),
    ("millet", "Millet", "Gero", "", "", 1.7),
    ("groundnut", "Groundnut", "Gyada", "Shelled", "Ɓararre", 1.1),
    ("rice-paddy", "Rice", "Shinkafa", "Paddy", "Da ɓawo", 1.1),
]


def seed() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for mid, name, state, days, anchor in MARKETS:
            db.merge(Market(id=mid, name=name, state=state, trading_days=days, is_anchor=anchor))
        for cid, n_en, n_ha, g_en, g_ha, mudu in COMMODITIES:
            db.merge(Commodity(id=cid, name_en=n_en, name_ha=n_ha, grade_en=g_en,
                               grade_ha=g_ha, kg_per_mudu=mudu))
        db.commit()
    print(f"Seeded {len(MARKETS)} markets and {len(COMMODITIES)} commodities.")


if __name__ == "__main__":
    seed()
