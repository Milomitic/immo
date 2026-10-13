from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.listings import router as listings_router
from app.api.scrape import router as scrape_router
from app.api.stats import router as stats_router
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

_ROUTERS = (listings_router, scrape_router, stats_router)

# /api/v1 is the canonical, documented API. /api is kept as an unversioned
# alias so older clients and bookmarked URLs keep working; it's hidden from
# the OpenAPI schema to steer new code to v1.
for _router in _ROUTERS:
    app.include_router(_router, prefix="/api/v1")
    app.include_router(_router, prefix="/api", include_in_schema=False)


@app.get("/health")
async def health():
    return {"status": "ok"}
