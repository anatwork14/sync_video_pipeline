import logging
import asyncio
import uuid
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

import aiofiles

from app.config import get_settings
from app.database import get_db
from app.models import Session, Chunk
from app.ws.manager import manager
from app.workers.tasks import process_chunk_set

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/simulate", tags=["simulate"])
settings = get_settings()

import subprocess

async def segment_video(input_path: Path, output_dir: Path, cam_id: str, segment_time: int = 10):
    """
    Split a video into segments using ffmpeg.
    Generates files like: chunk_0_cam1.mp4, chunk_1_cam1.mp4, etc.
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-f", "segment", "-segment_time", str(segment_time),
        "-reset_timestamps", "1",
        "-c", "copy",
        str(output_dir / f"chunk_%04d_{cam_id}.mp4")
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
    session_id: uuid.UUID = Form(...),
    cam1_id: str = Form(...),
    cam1_file: UploadFile = File(...),
    cam2_id: str = Form(None),
    cam2_file: UploadFile = File(None),
    cam3_id: str = Form(None),
    cam3_file: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload full video files for multiple cameras to simulate a live sync session.
    """
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    inputs = []
    if cam1_file: inputs.append((cam1_id, cam1_file))
    if cam2_file: inputs.append((cam2_id, cam2_file))
    if cam3_file: inputs.append((cam3_id, cam3_file))

    if not inputs:
        raise HTTPException(status_code=400, detail="No files uploaded")

    # Update camera count to match uploaded files
    session.camera_count = len(inputs)
    await db.commit()

    # 1. Save uploaded full videos to a temporary location
    temp_dir = Path(settings.storage_base) / "temp" / str(session_id)
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    seg_dir = temp_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    try:
        for cam_id, file in inputs:
            temp_path = temp_dir / f"{cam_id}.mp4"
            async with aiofiles.open(temp_path, "wb") as f:
                while chunk := await file.read(1024 * 1024):
                    await f.write(chunk)
            
            # Segment the video
            await segment_video(temp_path, seg_dir, cam_id, segment_time=10)

        # 2. Re-organize segments into chunk folders and insert DB records
        # Count max chunks across cameras
        chunk_files = list(seg_dir.glob("*.mp4"))
        if not chunk_files:
            raise HTTPException(status_code=500, detail="No segments generated")

        # Find unique chunk indices based on file names: chunk_0000_cam1.mp4
        chunk_indices = set()
        for p in chunk_files:
            # name format: chunk_0000_cam1.mp4
            parts = p.stem.split("_")
            idx = int(parts[1])
            chunk_indices.add(idx)

        all_cam_ids = [cam_id for cam_id, _ in inputs]

        for chunk_idx in sorted(list(chunk_indices)):
            chunk_dir = Path(settings.storage_base) / "raw" / str(session_id) / f"chunk_{chunk_idx}"
            chunk_dir.mkdir(parents=True, exist_ok=True)

            # Copy files for this chunk
            valid_cams = 0
            for cam_id in all_cam_ids:
                src_file = seg_dir / f"chunk_{chunk_idx:04d}_{cam_id}.mp4"
                if src_file.exists():
                    dest_file = chunk_dir / f"{cam_id}.mp4"
                    shutil.copy(src_file, dest_file)
                    
                    chunk_record = Chunk(
                        session_id=session_id,
                        chunk_index=chunk_idx,
                        cam_id=cam_id,
                        file_path=str(dest_file),
                        status="uploaded",
                    )
                    db.add(chunk_record)
                    valid_cams += 1

                    await manager.broadcast(str(session_id), {
                        "type": "chunk_uploaded",
                        "session_id": str(session_id),
                        "chunk_index": chunk_idx,
                        "cam_id": cam_id,
                    })

            await db.commit()

            # Trigger processing if all cameras have this chunk
            if valid_cams == len(all_cam_ids):
                process_chunk_set.delay(
                    session_id=str(session_id),
                    chunk_index=chunk_idx,
                    cam_ids=all_cam_ids,
                    sync_strategy=session.sync_strategy,
                )
                await manager.broadcast(str(session_id), {
                    "type": "processing_started",
                    "session_id": str(session_id),
                    "chunk_index": chunk_idx,
                })
                logger.info(f"Triggered processing for session={session_id} chunk={chunk_idx}")

    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    return {"message": "Simulation upload successful"}
