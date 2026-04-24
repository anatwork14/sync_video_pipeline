import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import engine, Base
from app.routers import upload, sessions, ws, live, simulate
from app.ws.manager import manager
from app.ws.redis_bridge import start_redis_subscriber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables + ensure storage dirs exist
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            try:
                from sqlalchemy import text
                await conn.execute(text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS sync_strategy VARCHAR(50) DEFAULT 'multividsynch'"))
            except Exception as e:
                logger.warning(f"Could not alter sessions table: {e}")
        logger.info("✅ Database tables created/verified")
    except Exception as e:
        logger.warning(
            f"⚠️  Database unavailable at startup ({e.__class__.__name__}: {e}). "
            "Live streaming endpoints will still work. "
            "Session/upload API endpoints require a running PostgreSQL."
        )

    storage = Path(settings.storage_base)
    (storage / "raw").mkdir(parents=True, exist_ok=True)
    (storage / "synced").mkdir(parents=True, exist_ok=True)

    # Start Redis pub/sub → WebSocket bridge
    bridge_task = asyncio.create_task(start_redis_subscriber(manager))
    logger.info("✅ Redis WS bridge started")
    logger.info("✅ VideoSync API started")
    yield
    # Shutdown
    bridge_task.cancel()
    await engine.dispose()
    logger.info("VideoSync API shut down")


app = FastAPI(
    title="VideoSync Pipeline API",
    description="Multi-camera video ingestion, synchronization, and stitching platform",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
cors_raw = settings.cors_origins
origins = cors_raw if isinstance(cors_raw, list) else cors_raw.split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(upload.router)
app.include_router(sessions.router)
app.include_router(live.router) # MP_web live streaming logic
app.include_router(ws.router)
app.include_router(simulate.router)

# ── Static files for synced video playback ────────────────────────────────────
synced_dir = Path(settings.storage_base) / "synced"

synced_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/synced", StaticFiles(directory=str(synced_dir)), name="synced")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
