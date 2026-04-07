import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import engine, Base
from app.routers import upload, sessions, ws

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables + ensure storage dirs exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    storage = Path(settings.storage_base)
    (storage / "raw").mkdir(parents=True, exist_ok=True)
    (storage / "synced").mkdir(parents=True, exist_ok=True)
    logger.info("✅ VideoSync API started")
    yield
    # Shutdown
    await engine.dispose()
    logger.info("VideoSync API shut down")


app = FastAPI(
    title="VideoSync Pipeline API",
    description="Multi-camera video ingestion, synchronization, and stitching platform",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(upload.router)
app.include_router(sessions.router)
app.include_router(ws.router)

# ── Static files for synced video playback ────────────────────────────────────
synced_dir = Path(settings.storage_base) / "synced"
synced_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/synced", StaticFiles(directory=str(synced_dir)), name="synced")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
