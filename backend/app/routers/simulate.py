import logging
import asyncio
import uuid
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

import aiofiles
import subprocess

from app.config import get_settings
from app.database import get_db
from app.models import Session, Chunk
from app.ws.manager import manager
from app.workers.tasks import process_chunk_set

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/simulate", tags=["simulate"])
settings = get_settings()

async def segment_video(input_path: Path, output_dir: Path, cam_id: str, segment_time: int = 10):
    """
    Split a video into segments using ffmpeg.
    Generates files like: chunk_0_cam1.mkv, chunk_1_cam1.mkv, etc.
    Using .mkv as it supports almost any codec with '-c copy'.
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-f", "segment", "-segment_time", str(segment_time),
        "-reset_timestamps", "1",
        "-c", "copy",
        str(output_dir / f"chunk_%04d_{cam_id}.mkv")
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        logger.error(f"FFmpeg failed: {stderr.decode()}")
        raise Exception(f"FFmpeg failed for {cam_id}")


@router.post("/upload")
async def simulate_upload(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Upload full video files for multiple cameras to simulate a live sync session.
    Supports dynamic number of cameras (cam1, cam2, ..., camN).
    """
    try:
        form_data = await request.form()
        logger.info(f"📥 /simulate/upload Received form keys: {list(form_data.keys())}")
        
        session_id_str = form_data.get("session_id")
        layout = form_data.get("layout", "hstack")
        sync_strategy = form_data.get("sync_strategy", "auto")
        selected_cameras_str = form_data.get("selected_cameras", "")

        if not session_id_str:
            raise HTTPException(status_code=400, detail="Missing session_id")
        
        try:
            session_id = uuid.UUID(session_id_str)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail=f"Invalid session_id format: {session_id_str}")

        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        # ── Discovery Phase ────────────────────────────────────────────────────────
        inputs = [] # list of (cam_id, UploadFile)
        processed_prefixes = set()
        
        # 1. Primary discovery: structured camN_id / camN_file pairs
        for key in list(form_data.keys()):
            if key.startswith("cam") and key.endswith("_id"):
                prefix = key[:-3] # e.g. "cam1"
                cam_id = form_data.get(key)
                file_key = f"{prefix}_file"
                cam_file = form_data.get(file_key)
                
                if cam_id and cam_file and hasattr(cam_file, "filename"):
                    inputs.append((str(cam_id), cam_file))
                    processed_prefixes.add(prefix)
                    logger.info(f"✅ Discovered: {prefix} -> ID={cam_id}, File={cam_file.filename}")

        # 2. Secondary discovery: files without explicit camN_id in form (fallback)
        for key in list(form_data.keys()):
            if key.startswith("cam") and key.endswith("_file"):
                prefix = key[:-5] # e.g. "cam1"
                if prefix not in processed_prefixes:
                    cam_file = form_data.get(key)
                    if cam_file and hasattr(cam_file, "filename"):
                        # Fallback ID is the prefix itself
                        cam_id = prefix
                        inputs.append((cam_id, cam_file))
                        logger.info(f"⚠️ Discovered (fallback): {prefix} -> ID={cam_id}, File={cam_file.filename}")

        if not inputs:
            msg = f"No valid camera files found. Use keys cam1_id/cam1_file, etc. Received keys: {list(form_data.keys())}"
            logger.error(f"❌ {msg}")
            raise HTTPException(status_code=400, detail=msg)

        # ── Selection Phase ────────────────────────────────────────────────────────
        # Parse selected_cameras from form
        selected_cam_ids = [c.strip() for c in selected_cameras_str.split(",") if c.strip()]
        if not selected_cam_ids:
            # Default to all discovered inputs if none specified
            selected_cam_ids = [cam_id for cam_id, _ in inputs]
            logger.info(f"ℹ️ No selected_cameras provided, defaulting to all: {selected_cam_ids}")
        else:
            logger.info(f"🎯 User selected cameras: {selected_cam_ids}")

        # Update session record
        session.camera_count = len(selected_cam_ids)
        session.layout = layout
        session.sync_strategy = sync_strategy
        session.status = "processing"
        await db.commit()

        # ── Processing Phase ───────────────────────────────────────────────────────
        storage_base = Path(settings.storage_base).resolve()
        temp_dir = storage_base / "temp" / str(session_id)
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        seg_dir = temp_dir / "segments"
        seg_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Save and segment all uploaded videos
            for cam_id, file in inputs:
                ext = Path(file.filename).suffix if file.filename else ".mp4"
                temp_path = temp_dir / f"{cam_id}{ext}"
                
                async with aiofiles.open(temp_path, "wb") as f:
                    while chunk := await file.read(1024 * 1024):
                        await f.write(chunk)
                
                logger.info(f"✂️  Segmenting {cam_id}...")
                await segment_video(temp_path, seg_dir, cam_id, segment_time=10)

            # 2. Re-organize segments into chunk folders and insert DB records
            chunk_files = list(seg_dir.glob("*.mkv"))
            if not chunk_files:
                raise Exception("No segments generated by FFmpeg. Check input video validity.")

            # Find unique chunk indices from generated filenames
            chunk_indices = set()
            for p in chunk_files:
                # name format: chunk_0000_cam1.mkv
                parts = p.stem.split("_")
                try:
                    idx = int(parts[1])
                    chunk_indices.add(idx)
                except (ValueError, IndexError):
                    continue

            logger.info(f"📦 Found {len(chunk_indices)} chunks across {len(inputs)} cameras.")

            for chunk_idx in sorted(list(chunk_indices)):
                chunk_dir = storage_base / "raw" / str(session_id) / f"chunk_{chunk_idx}"
                chunk_dir.mkdir(parents=True, exist_ok=True)

                # Move/Copy files for this chunk and record in DB
                for cam_id, _ in inputs:
                    src_file = seg_dir / f"chunk_{chunk_idx:04d}_{cam_id}.mkv"
                    if src_file.exists():
                        dest_file = chunk_dir / f"{cam_id}.mkv"
                        shutil.copy(src_file, dest_file)
                        
                        chunk_record = Chunk(
                            session_id=session_id,
                            chunk_index=chunk_idx,
                            cam_id=cam_id,
                            file_path=str(dest_file),
                            status="uploaded",
                        )
                        db.add(chunk_record)

                        await manager.broadcast(str(session_id), {
                            "type": "chunk_uploaded",
                            "session_id": str(session_id),
                            "chunk_index": chunk_idx,
                            "cam_id": cam_id,
                        })

                await db.commit()

                # Trigger processing if ALL selected cameras are present in this chunk
                present_selected = []
                for cam_id in selected_cam_ids:
                    if (chunk_dir / f"{cam_id}.mkv").exists():
                        present_selected.append(cam_id)
                
                if len(present_selected) == len(selected_cam_ids):
                    logger.info(f"🚀 Triggering sync for chunk {chunk_idx} with cameras {selected_cam_ids}")
                    process_chunk_set.delay(
                        session_id=str(session_id),
                        chunk_index=chunk_idx,
                        cam_ids=selected_cam_ids,
                        layout=layout,
                        sync_strategy=session.sync_strategy,
                    )
                    await manager.broadcast(str(session_id), {
                        "type": "processing_started",
                        "session_id": str(session_id),
                        "chunk_index": chunk_idx,
                    })
                else:
                    logger.warning(f"⚠️ Chunk {chunk_idx} skipped: only {len(present_selected)}/{len(selected_cam_ids)} selected cameras present.")

            return {"status": "success", "session_id": str(session_id), "chunks": len(chunk_indices)}

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Simulation upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

