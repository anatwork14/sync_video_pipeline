"""
POST /api/upload-chunk

Receives a video chunk from a camera node (mobile phone).
Saves the file, records it in DB, and triggers processing when all cameras
have uploaded for the given chunk_index.
"""
import logging
import mimetypes
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import aiofiles

from app.config import get_settings
from app.database import get_db
from app.models import Session, Chunk
from app.schemas import UploadResponse
from app.ws.manager import manager
from app.workers.tasks import process_chunk_set

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["upload"])
settings = get_settings()

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
MAX_UPLOAD_BYTES = settings.max_upload_size_mb * 1024 * 1024


@router.post("/upload-chunk", response_model=UploadResponse)
async def upload_chunk(
    file: UploadFile = File(...),
    cam_id: str = Form(..., min_length=1, max_length=50),
    chunk_index: int = Form(..., ge=0),
    session_id: UUID = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # ── Validate session ──────────────────────────────────────────────────────
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status == "completed":
        raise HTTPException(status_code=400, detail="Session is already completed")

    # ── Validate file ─────────────────────────────────────────────────────────
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    # ── Save file ─────────────────────────────────────────────────────────────
    chunk_dir = (
        Path(settings.storage_base) / "raw" / str(session_id) / f"chunk_{chunk_index}"
    )
    chunk_dir.mkdir(parents=True, exist_ok=True)
    dest = chunk_dir / f"{cam_id}.mp4"

    total_bytes = 0
    async with aiofiles.open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):  # 1 MB chunks
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="File too large")
            await f.write(chunk)

    logger.info(f"Saved {dest} ({total_bytes / 1024 / 1024:.1f} MB)")

    # ── Record in DB ──────────────────────────────────────────────────────────
    chunk_record = Chunk(
        session_id=session_id,
        chunk_index=chunk_index,
        cam_id=cam_id,
        file_path=str(dest),
        status="uploaded",
    )
    db.add(chunk_record)
    await db.commit()

    # ── Broadcast upload event ────────────────────────────────────────────────
    await manager.broadcast(str(session_id), {
        "type": "chunk_uploaded",
        "session_id": str(session_id),
        "chunk_index": chunk_index,
        "cam_id": cam_id,
    })

    # ── Check if all cameras have uploaded this chunk ─────────────────────────
    uploaded_count = await db.scalar(
        select(func.count())
        .where(Chunk.session_id == session_id)
        .where(Chunk.chunk_index == chunk_index)
        .where(Chunk.status == "uploaded")
    )

    processing_triggered = False
    if uploaded_count >= session.camera_count:
        # Fetch cam_ids for this chunk
        result = await db.execute(
            select(Chunk.cam_id)
            .where(Chunk.session_id == session_id)
            .where(Chunk.chunk_index == chunk_index)
        )
        cam_ids = [row[0] for row in result.all()]

        # Dispatch Celery task
        process_chunk_set.delay(
            session_id=str(session_id),
            chunk_index=chunk_index,
            cam_ids=cam_ids,
            sync_strategy=session.sync_strategy,
        )
        processing_triggered = True

        await manager.broadcast(str(session_id), {
            "type": "processing_started",
            "session_id": str(session_id),
            "chunk_index": chunk_index,
        })
        logger.info(f"Triggered processing for session={session_id} chunk={chunk_index}")

    return UploadResponse(
        message="Chunk uploaded successfully",
        session_id=session_id,
        chunk_index=chunk_index,
        cam_id=cam_id,
        processing_triggered=processing_triggered,
    )
