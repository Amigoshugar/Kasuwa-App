from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import Base, engine
from app.routes import admin, meta, prices, reports


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Creates missing tables on start. Move to Alembic migrations before the pilot.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Kasuwa API", version="0.1.0",
              description="Daily grain prices for Kano, Kaduna and Katsina markets.",
              lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(prices.router)
app.include_router(reports.router)
app.include_router(admin.router)
