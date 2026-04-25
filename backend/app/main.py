from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.utils.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_db()
    yield


app = FastAPI(
    title="Immo",
    description="Real estate listing aggregator",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from app.api.listings import router as listings_router
from app.api.scrape import router as scrape_router
from app.api.stats import router as stats_router

app.include_router(listings_router)
app.include_router(scrape_router)
app.include_router(stats_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
