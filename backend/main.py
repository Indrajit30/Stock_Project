import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from backend.routers import stock, peers, export
from backend.services.cache import CacheManager

cache: CacheManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global cache
    cache = CacheManager()
    await cache.connect()
    app.state.cache = cache
    yield
    await cache.close()


app = FastAPI(
    title="StockResearch AI API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stock.router, prefix="/api")
app.include_router(peers.router, prefix="/api")
app.include_router(export.router, prefix="/api")


@app.get("/api/health")
async def health():
    redis_status = "memory"
    qdrant_status = "connected"

    try:
        if getattr(app.state.cache, "redis", None):
            await app.state.cache.redis.ping()
            redis_status = "connected"
    except Exception:
        redis_status = "error"

    try:
        from qdrant_client import AsyncQdrantClient
        qc = AsyncQdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))
        await qc.get_collections()
        await qc.close()
    except Exception:
        qdrant_status = "error"

    return {
        "status": "ok",
        "redis": redis_status,
        "qdrant": qdrant_status,
        "precompute_cache_coverage": "0/50 tickers cached",
        "last_nightly_run": None,
    }


@app.get("/api/cache/stats")
async def cache_stats():
    return await app.state.cache.stats()
