import os
import subprocess
import time
import logging
import asyncio
import uuid
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Depends, HTTPException

from app.config import get_settings
from app.database import AsyncSessionLocal, get_db
from app.models import Session, Chunk
from app.ws.manager import manager
from app.workers.tasks import process_chunk_set, produce_master_video
from app.diag_logger import log_diag

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live", tags=["live"])
ws_router = APIRouter(tags=["live-ws"])
settings = get_settings()

# Directories
RAW_DIR = Path(settings.storage_base) / "raw"
SYNCED_DIR = Path(settings.storage_base) / "synced"
CHUNKS_DIR = Path("video_chunks")

def ensure_directories():
    """Safely create required directories."""
    try:
        print(f"!!! DEBUG: Ensuring directories in {settings.storage_base}", flush=True)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        SYNCED_DIR.mkdir(parents=True, exist_ok=True)
        CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
        print("!!! DEBUG: Directories verified/created successfully", flush=True)
    except Exception as e:
        print(f"!!! ERROR: Failed to create directories: {e}", flush=True)
        # We don't raise here so the app can at least start and show health errors

# Track connections
active_cameras: dict[WebSocket, str] = {} # websocket -> cam_id
active_esp32s: list[WebSocket] = []
active_dashboards: list[WebSocket] = []
current_active_session: str | None = None

# chunk_counters[session_id][device_id] = next chunk index
chunk_counters: dict[str, dict[str, int]] = {}
# track uploaded devices per chunk index per session: 
# uploaded_chunks[session_id][chunk_idx] = set(device_ids)
uploaded_chunks: dict[str, dict[int, set[str]]] = {}

# track all unique cameras that participated in a session
# session_cameras[session_id] = set(device_ids)
session_cameras: dict[str, set[str]] = {}

async def recover_active_session():
    """Attempt to recover an active recording session from the database on startup."""
    global current_active_session
    global chunk_counters
    global session_cameras

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        try:
            # Look for the most recent session that is still in 'recording' status
            result = await db.execute(
                select(Session).where(Session.status == "recording").order_by(Session.created_at.desc()).limit(1)
            )
            active = result.scalar_one_or_none()
            if active:
                current_active_session = str(active.id)
                if current_active_session not in chunk_counters:
                    chunk_counters[current_active_session] = {}
                if current_active_session not in uploaded_chunks:
                    uploaded_chunks[current_active_session] = {}
                if current_active_session not in session_cameras:
                    session_cameras[current_active_session] = set()
                
                log_diag(f"🔄 Recovered active session from DB: {current_active_session}")
            else:
                log_diag("ℹ️ No active recording sessions found in DB to recover.")
        except Exception as e:
            log_diag(f"⚠️ Failed to recover active session: {e}")

# ── Session control ───────────────────────────────────────────────────────────

async def handle_trigger_logic(session_id_from_dash: str | None = None, layout: str = "hstack"):
    global current_active_session
    global chunk_counters
    global uploaded_chunks
    global session_cameras

    if current_active_session is None:
        # START
        # 1. Determine session_id and generate UUID
        temp_id = session_id_from_dash or str(uuid.uuid4())
        try:
            sess_uuid = uuid.UUID(temp_id)
        except (ValueError, TypeError):
            sess_uuid = uuid.uuid4()
        
        final_session_id = str(sess_uuid)
        
        # 2. Determine expected cameras (currently connected)
        expected_cameras = max(1, len(active_cameras))

        # 3. Create session in DB
        async with AsyncSessionLocal() as db:
            try:
                db_session = Session(
                    id=sess_uuid,
                    name=f"Live Session {final_session_id[:8]}",
                    camera_count=expected_cameras,
                    status="recording",
                    sync_strategy="multividsynch",
                    layout=layout
                )
                db.add(db_session)
                await db.commit()
                
                # 4. SUCCESS: Now initialize global state
                current_active_session = final_session_id
                chunk_counters[final_session_id] = {}
                uploaded_chunks[final_session_id] = {}
                session_cameras[final_session_id] = set(active_cameras.values())
                
                # Create per-session chunk dir
                session_dir = RAW_DIR / final_session_id
                session_dir.mkdir(parents=True, exist_ok=True)

                log_diag(f"▶️  SESSION START: {final_session_id} with {expected_cameras} cameras")
                
                # Broadcast start to everyone
                # Match frontend: data.type === "info" and data.message === "STARTED"
                await broadcast_info("STARTED", final_session_id)
                await broadcast_status("start", final_session_id)
                return {"status": "started", "session_id": final_session_id}

            except Exception as e:
                log_diag(f"❌ Failed to create DB session: {e}")
                # Ensure global state remains clean
                current_active_session = None
                
                # Notify dashboard directly and via manager
                error_payload = {
                    "type": "error",
                    "message": f"Failed to initialize database session: {str(e)}"
                }
                for dash in list(active_dashboards):
                    try:
                        await dash.send_json(error_payload)
                    except Exception:
                        pass
                await manager.broadcast_all(error_payload)
                return {"status": "error", "detail": "Database failure"}
    else:
        # STOP
        stopped_session = current_active_session
        current_active_session = None

        log_diag(f"⏹  SESSION STOP: {stopped_session}")
        
        # Determine cameras that actually participated (uploaded chunks) or are active
        captured_set = session_cameras.get(stopped_session, set())
        # Add currently connected cameras just in case they were active but didn't upload a chunk yet
        captured_set.update(active_cameras.values())
        
        captured = list(captured_set)
        
        # Update DB status
        async with AsyncSessionLocal() as db:
            try:
                sess_uuid = uuid.UUID(stopped_session)
                db_session = await db.get(Session, sess_uuid)
                if db_session:
                    db_session.status = "completed"
                    await db.commit()
            except Exception as e:
                log_diag(f"❌ Failed to update DB session status: {e}")

        # Broadcast stop with captured cameras
        await broadcast_info("STOPPED", session_id=stopped_session)
        await broadcast_status("stop", session_id=stopped_session, captured_cameras=captured)

        return {
            "status": "stopped", 
            "session_id": stopped_session,
            "captured_cameras": captured
        }

async def concatenate_session(session_id: str):
    """FFmpeg-concatenate all saved chunks per device into one final MP4."""
    # We still use CHUNKS_DIR here if any chunks were saved there,
    # but now we save them in RAW_DIR. We can iterate RAW_DIR to concat full streams.
    session_dir = RAW_DIR / session_id
    if not session_dir.exists():
        return

    # Find devices based on chunk_0 if available
    devices = set()
    for chunk_dir in session_dir.glob("chunk_*"):
        if chunk_dir.is_dir():
            devices.update([p.stem for p in chunk_dir.glob("*.*") if p.is_file()])
            
    if not devices:
        return

    log_diag(f"🎬 Concatenating {len(devices)} device(s) for session {session_id}")

    for device_id in devices:
        # Collect chunks in order by iterating chunk_dirs
        chunks = []
        chunk_dirs = sorted([d for d in session_dir.glob("chunk_*") if d.is_dir()],
                            key=lambda d: int(d.name.split("_")[1]))
        
        for d in chunk_dirs:
            # Look for device_id.mp4 or .webm
            device_files = list(d.glob(f"{device_id}.*"))
            if device_files:
                chunks.append(device_files[0])

        if not chunks:
            continue

        ext = chunks[0].suffix

        concat_list = session_dir / f"{device_id}_concat.txt"
        with open(concat_list, "w") as f:
            for c in chunks:
                f.write(f"file '{c.resolve()}'\n")

        out_file = SYNCED_DIR / f"session_{session_id}_cam_{device_id}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(out_file),
        ]
        log_diag(f"🎬 FFmpeg concat: {len(chunks)} chunks → {out_file.name}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            log_diag(f"✅ Saved: {out_file}")
        else:
            log_diag(f"❌ FFmpeg concat failed for {device_id}:\n{result.stderr[-500:]}")

async def broadcast_info(message: str, session_id: str | None = None):
    """Specific broadcaster for 'info' type messages that the dashboard expects."""
    payload = {
        "type": "info",
        "message": message,
        "session_id": session_id or current_active_session
    }
    for dash in list(active_dashboards):
        try:
            await dash.send_json(payload)
        except Exception:
            pass

async def broadcast_status(command: str, session_id: str | None = None, **kwargs):
    payload = {
        "type": "status",
        "command": command,
        "session_id": session_id or current_active_session,
        **kwargs
    }
    
    # Notify cameras and ESP32s
    for ws in list(active_cameras.keys()):
        try:
            await ws.send_json({"command": command, "session_id": payload["session_id"]})
        except Exception:
            pass
    for esp in list(active_esp32s):
        try:
            await esp.send_json({"command": command, "session_id": payload["session_id"]})
        except Exception:
            pass

    # Notify dashboards
    for dash in list(active_dashboards):
        try:
            await dash.send_json(payload)
        except Exception:
            pass

    # Notify dashboard via manager (for session specific listeners)
    if payload["session_id"]:
        await manager.broadcast(payload["session_id"], payload)
        
    # Also notify all active dashboards (global monitoring)
    for dash in list(active_dashboards):
        try:
            await dash.send_json(payload)
        except Exception:
            pass


# ── HTTP endpoints ────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_chunk(
    file: UploadFile = File(...),
    device_id: str = Form(...),
    session_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Receive a media chunk from a live camera and process it."""
    log_diag(
        f"📥 /upload  device={device_id!r}  session={session_id!r}  "
        f"filename={file.filename!r}  active={current_active_session!r}"
    )

    if session_id != current_active_session:
        logger.warning(
            f"⚠️  Ignored chunk: session mismatch "
            f"(got {session_id!r}, expected {current_active_session!r})"
        )
        return {"status": "ignored"}

    content = await file.read()

    # Force use .mkv for live chunks to avoid VP8 in MP4 container issues
    ext = ".mkv"

    # Increment chunk counter for this device (per session)
    if session_id not in chunk_counters:
        chunk_counters[session_id] = {}
    
    if device_id not in chunk_counters[session_id]:
        # Recover from DB if not in memory (handle restarts)
        from sqlalchemy import select, func
        async with AsyncSessionLocal() as db_session:
            try:
                sess_uuid = uuid.UUID(session_id)
                result = await db_session.execute(
                    select(func.max(Chunk.chunk_index))
                    .where(Chunk.session_id == sess_uuid, Chunk.cam_id == device_id)
                )
                max_idx = result.scalar()
                chunk_counters[session_id][device_id] = (max_idx + 1) if max_idx is not None else 0
            except Exception as e:
                logger.warning(f"Failed to recover chunk index from DB: {e}")
                chunk_counters[session_id][device_id] = 0

    idx = chunk_counters[session_id][device_id]
    chunk_counters[session_id][device_id] += 1

    # Save to standard struct: storage/raw/{session_id}/chunk_{idx}/{device_id}.ext
    session_dir = RAW_DIR / session_id
    chunk_dir = session_dir / f"chunk_{idx}"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    
    chunk_path = chunk_dir / f"{device_id}{ext}"

    try:
        with open(chunk_path, "wb") as f:
            f.write(content)
        log_diag(f"✅ Saved chunk {idx:04d} for device={device_id}  size={len(content)} bytes  → {chunk_path}")
        
        # Insert into DB
        try:
            chunk_record = Chunk(
                session_id=uuid.UUID(session_id),
                chunk_index=idx,
                cam_id=device_id,
                file_path=str(chunk_path),
                status="uploaded",
            )
            db.add(chunk_record)
            await db.commit()
        except Exception as db_err:
            logger.error(f"❌ Failed to insert Chunk record to DB: {db_err}")

        # Broadcast that a chunk was uploaded
        upload_event = {
            "type": "chunk_uploaded",
            "session_id": session_id,
            "chunk_index": idx,
            "cam_id": device_id,
        }
        await manager.broadcast(session_id, upload_event)
        
        # Also notify all active dashboards for real-time progress
        for dash in list(active_dashboards):
            try:
                await dash.send_json(upload_event)
            except Exception:
                pass

        # Track participating cameras
        if session_id not in session_cameras:
            session_cameras[session_id] = set()
        session_cameras[session_id].add(device_id)

        # Check if we should trigger Celery processing
        if session_id not in uploaded_chunks:
            uploaded_chunks[session_id] = {}
        if idx not in uploaded_chunks[session_id]:
            uploaded_chunks[session_id][idx] = set()
            
        uploaded_chunks[session_id][idx].add(device_id)

        # Get expected cameras from DB
        db_session = await db.get(Session, uuid.UUID(session_id))
        expected_cams = db_session.camera_count if db_session else max(1, len(active_cameras))

        # Automatic background processing disabled. 
        # We now wait for the user to "Finalize" the session and select which cameras to sync.
        # This prevents partial/incorrect syncs during active recording and gives users control.
        pass

    except Exception as e:
        log_diag(f"❌ Failed to process uploaded chunk for {device_id}: {e}")
        return {"status": "error", "detail": str(e)}

    return {"status": "success", "chunk": idx, "size": len(content)}


@router.post("/esp32-trigger")
async def esp32_trigger_http():
    log_diag("🤖 ESP32 HTTP trigger received")
    return await handle_trigger_logic()


@router.post("/finalize")
async def finalize_session(
    session_id: str = Form(...),
    selected_cameras: str = Form(...), # comma-separated list
    layout: str = Form("hstack"),
    sync_strategy: str = Form("auto"),
    db: AsyncSession = Depends(get_db)
):
    """
    Finalize a live recording by choosing a subset of cameras to process.
    Triggers sync pipeline for all recorded chunks.
    """
    log_diag(f"🏁 Finalizing session {session_id} with cameras: {selected_cameras} using strategy: {sync_strategy}")
    
    try:
        try:
            sess_uuid = uuid.UUID(session_id)
        except (ValueError, TypeError):
            logger.error(f"❌ Invalid session ID format: {session_id}")
            raise HTTPException(status_code=400, detail=f"Invalid session ID format: {session_id}. Expected UUID.")

        db_session = await db.get(Session, sess_uuid)
        if not db_session:
            logger.error(f"❌ Session {session_id} not found in database")
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        cam_list = [c.strip() for c in selected_cameras.split(",") if c.strip()]
        if not cam_list:
            raise HTTPException(status_code=400, detail="No cameras selected")

        # Update session with selected camera count, layout and sync strategy
        db_session.camera_count = len(cam_list)
        db_session.layout = layout
        db_session.sync_strategy = sync_strategy
        db_session.status = "processing"
        await db.commit()

        # Trigger processing for every chunk index we have recorded
        indices_to_process = []
        if session_id in uploaded_chunks:
            indices_to_process = sorted(uploaded_chunks[session_id].keys())
        
        # If in-memory is empty, try to recover from DB
        if not indices_to_process:
            from sqlalchemy import select
            result = await db.execute(
                select(Chunk.chunk_index).where(Chunk.session_id == sess_uuid).distinct()
            )
            indices_to_process = sorted([r[0] for r in result.all()])
            logger.info(f"🔄 Recovered {len(indices_to_process)} chunk indices from DB for session {session_id}")

        if not indices_to_process:
            logger.warning(f"⚠️ No chunks found for session {session_id}. Nothing to process.")
            return {"status": "success", "session_id": session_id, "message": "No chunks found"}

        for idx in indices_to_process:
            process_chunk_set.delay(
                session_id=session_id,
                chunk_index=idx,
                cam_ids=cam_list,
                sync_strategy=sync_strategy,
                layout=layout,
            )
            
            processing_event = {
                "type": "processing_started",
                "session_id": session_id,
                "chunk_index": idx
            }
            await manager.broadcast(session_id, processing_event)
            
            # Also notify all active dashboards
            for dash in list(active_dashboards):
                try:
                    await dash.send_json(processing_event)
                except Exception:
                    pass

        # ── Schedule the Phase-2 master render ──────────────────────────────
        # This runs in the background AFTER all chunk tasks complete.
        # It concatenates raw chunks → aligns once → stitches the final master.
        produce_master_video.apply_async(
            kwargs={
                "session_id": session_id,
                "cam_ids": cam_list,
                "layout": layout,
            },
            countdown=5,  # Small delay so chunk tasks can start first
        )
        log_diag(f"🎬 Master render task queued for session {session_id}")

        return {"status": "success", "session_id": session_id, "processed_count": len(indices_to_process)}
    except Exception as e:
        logger.error(f"❌ Failed to finalize session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/master-status/{session_id}")
async def master_status(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Poll the Phase-2 master render status.

    Returns:
        {
            "status": "pending" | "processing" | "completed" | "failed",
            "url":    "/static/master/{session_id}/master.mp4" (if completed),
            "error":  "..."  (if failed)
        }
    """
    from app.models import MasterVideo
    import uuid as _uuid
    try:
        sess_uuid = _uuid.UUID(session_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    from sqlalchemy import select as sa_select
    result = await db.execute(
        sa_select(MasterVideo).where(MasterVideo.session_id == sess_uuid)
    )
    mv = result.scalar_one_or_none()
    if not mv:
        return {"status": "pending", "url": None, "error": None}

    return {
        "status": mv.status,
        "url": mv.url,
        "error": mv.error,
    }

# ── WebSocket endpoints ───────────────────────────────────────────────────────
# Using ws_router (no prefix) to match frontend paths /ws/...

@ws_router.websocket("/ws/esp32")
async def websocket_esp32(websocket: WebSocket):
    await websocket.accept()
    active_esp32s.append(websocket)
    log_diag("🤖 Yolo:bit connected via WebSocket")
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("command") == "trigger":
                await handle_trigger_logic(layout=data.get("layout", "hstack"))
    except WebSocketDisconnect:
        active_esp32s.remove(websocket)
        log_diag("🤖 Yolo:bit disconnected")


@ws_router.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    await websocket.accept()
    active_dashboards.append(websocket)
    client = websocket.client.host if websocket.client else "unknown"
    log_diag(f"🖥  Dashboard connected from {client} — total: {len(active_dashboards)}")

    try:
        # On connection, if there's an active session, let the dashboard know
        if current_active_session:
            await websocket.send_json({
                "type": "info",
                "message": "STARTED",
                "session_id": current_active_session
            })

        while True:
            data = await websocket.receive_json()
            if data.get("command") == "start":
                await handle_trigger_logic(data.get("session_id"), layout=data.get("layout", "hstack"))
            elif data.get("command") == "stop":
                await handle_trigger_logic()
    except WebSocketDisconnect:
        if websocket in active_dashboards:
            active_dashboards.remove(websocket)
        log_diag(f"🖥  Dashboard disconnected — total: {len(active_dashboards)}")


@ws_router.websocket("/ws/camera")
async def websocket_camera(websocket: WebSocket):
    await websocket.accept()
    cam_id = None
    client = websocket.client.host if websocket.client else "unknown"
    log_diag(f"📱 Camera connection attempt from {client}")

    try:
        while True:
            data = await websocket.receive_json()
            if not cam_id and "id" in data:
                cam_id = data["id"]
                active_cameras[websocket] = cam_id
                log_diag(f"📱 Camera identified: id={cam_id} — total: {len(active_cameras)}")
                
                # Notify dashboards that a new camera connected
                # Send a preview with empty image to make it show up in the list immediately
                for dash in list(active_dashboards):
                    try:
                        await dash.send_json({"type": "preview", "id": cam_id, "image": ""})
                    except Exception:
                        pass

                # If session already active, immediately send start command
                if current_active_session:
                    try:
                        await websocket.send_json({"command": "start", "session_id": current_active_session})
                        log_diag(f"📱 Sent active session {current_active_session} to new camera {cam_id}")
                        if current_active_session in session_cameras:
                            session_cameras[current_active_session].add(cam_id)
                    except Exception:
                        pass

            if data.get("type") == "preview":
                # Broadcast preview to all dashboards
                for dash in list(active_dashboards):
                    try:
                        await dash.send_json(data)
                    except Exception:
                        pass
    except WebSocketDisconnect:
        if websocket in active_cameras:
            del active_cameras[websocket]
        log_diag(f"📱 Camera disconnected: id={cam_id} — total: {len(active_cameras)}")
        if cam_id:
            # Notify dashboards
            for dash in list(active_dashboards):
                try:
                    await dash.send_json({"type": "disconnect", "id": cam_id})
                except Exception:
                    pass
