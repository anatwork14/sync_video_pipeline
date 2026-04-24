import os
import subprocess
import time
import logging
import asyncio
import uuid
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Depends

from app.config import get_settings
from app.database import AsyncSessionLocal, get_db
from app.models import Session, Chunk
from app.ws.manager import manager
from app.workers.tasks import process_chunk_set

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(tags=["live"])
settings = get_settings()

# Directories
RAW_DIR = Path(settings.storage_base) / "raw"
SYNCED_DIR = Path(settings.storage_base) / "synced"
RAW_DIR.mkdir(parents=True, exist_ok=True)
SYNCED_DIR.mkdir(parents=True, exist_ok=True)

# Deprecated/Old Directory for concat
CHUNKS_DIR = Path("video_chunks")
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

# Track connections
active_cameras: list[WebSocket] = []
active_esp32s: list[WebSocket] = []
dashboard_socket: WebSocket | None = None
current_active_session: str | None = None

# chunk_counters[device_id] = next chunk index
chunk_counters: dict[str, int] = {}
# track uploaded devices per chunk index per session: 
# uploaded_chunks[session_id][chunk_idx] = set(device_ids)
uploaded_chunks: dict[str, dict[int, set[str]]] = {}

# ── Session control ───────────────────────────────────────────────────────────

async def handle_trigger_logic(session_id_from_dash: str | None = None):
    global current_active_session
    global chunk_counters
    global uploaded_chunks

    if current_active_session is None:
        # START
        session_id = session_id_from_dash or str(uuid.uuid4())
        current_active_session = session_id
        chunk_counters.clear()
        uploaded_chunks[session_id] = {}

        # The number of expected cameras is the number currently connected, defaulting to 3 if none
        expected_cameras = max(1, len(active_cameras))

        # Create session in DB
        async with AsyncSessionLocal() as db:
            try:
                # Convert string to UUID if possible, else just use the string.
                # Since models.Session.id is a UUID, we should parse it.
                # If session_id_from_dash isn't a valid UUID, generate one.
                try:
                    sess_uuid = uuid.UUID(session_id)
                except ValueError:
                    sess_uuid = uuid.uuid4()
                    session_id = str(sess_uuid)
                    current_active_session = session_id
                
                db_session = Session(
                    id=sess_uuid,
                    name=f"Live Session {session_id[:8]}",
                    camera_count=expected_cameras,
                    status="recording",
                    sync_strategy="multividsynch"
                )
                db.add(db_session)
                await db.commit()
                logger.info(f"▶️  DB SESSION CREATED: {session_id} with {expected_cameras} cameras")
            except Exception as e:
                logger.error(f"❌ Failed to create DB session: {e}")

        # Create per-session chunk dir
        session_dir = RAW_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"▶️  SESSION START: {session_id}  dir={session_dir}")
        await broadcast_status("start", session_id)
        return {"status": "started", "session_id": session_id}

    else:
        # STOP
        stopped_session = current_active_session
        current_active_session = None

        logger.info(f"⏹  SESSION STOP: {stopped_session}")
        await broadcast_status("stop")

        async with AsyncSessionLocal() as db:
            try:
                sess_uuid = uuid.UUID(stopped_session)
                db_session = await db.get(Session, sess_uuid)
                if db_session:
                    db_session.status = "completed"
                    await db.commit()
            except Exception as e:
                logger.error(f"❌ Failed to update DB session status: {e}")

        # Also trigger the old concatenate logic as fallback or secondary output
        asyncio.create_task(concatenate_session(stopped_session))

        return {"status": "stopped", "session_id": stopped_session}


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

    logger.info(f"🎬 Concatenating {len(devices)} device(s) for session {session_id}")

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
        logger.info(f"🎬 FFmpeg concat: {len(chunks)} chunks → {out_file.name}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info(f"✅ Saved: {out_file}")
        else:
            logger.error(f"❌ FFmpeg concat failed for {device_id}:\n{result.stderr[-500:]}")


async def broadcast_status(command: str, session_id: str | None = None):
    payload = {"command": command, "session_id": session_id}

    for cam in list(active_cameras):
        try:
            await cam.send_json(payload)
        except Exception:
            pass

    for esp in list(active_esp32s):
        try:
            await esp.send_json(payload)
        except Exception:
            pass

    if dashboard_socket:
        try:
            msg = "STARTED" if command == "start" else "STOPPED"
            await dashboard_socket.send_json({"type": "info", "message": msg, "session_id": session_id})
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
    logger.info(
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

    original_name = file.filename or ""
    if original_name.lower().endswith(".mp4") or (file.content_type or "").startswith("video/mp4"):
        ext = ".mp4"
    else:
        ext = ".webm"

    # Increment chunk counter for this device
    idx = chunk_counters.get(device_id, 0)
    chunk_counters[device_id] = idx + 1

    # Save to standard struct: storage/raw/{session_id}/chunk_{idx}/{device_id}.ext
    session_dir = RAW_DIR / session_id
    chunk_dir = session_dir / f"chunk_{idx}"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    
    chunk_path = chunk_dir / f"{device_id}{ext}"

    try:
        with open(chunk_path, "wb") as f:
            f.write(content)
        logger.info(f"✅ Saved chunk {idx:04d} for device={device_id}  size={len(content)} bytes  → {chunk_path}")
        
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
        await manager.broadcast(session_id, {
            "type": "chunk_uploaded",
            "session_id": session_id,
            "chunk_index": idx,
            "cam_id": device_id,
        })

        # Check if we should trigger Celery processing
        if session_id not in uploaded_chunks:
            uploaded_chunks[session_id] = {}
        if idx not in uploaded_chunks[session_id]:
            uploaded_chunks[session_id][idx] = set()
            
        uploaded_chunks[session_id][idx].add(device_id)

        # Get expected cameras from DB
        db_session = await db.get(Session, uuid.UUID(session_id))
        expected_cams = db_session.camera_count if db_session else max(1, len(active_cameras))

        if len(uploaded_chunks[session_id][idx]) >= expected_cams:
            all_cam_ids = list(uploaded_chunks[session_id][idx])
            logger.info(f"🚀 Triggering processing for session={session_id} chunk={idx} cams={all_cam_ids}")
            
            # Use sync_strategy from DB or default
            sync_strategy = db_session.sync_strategy if db_session else "multividsynch"
            
            process_chunk_set.delay(
                session_id=session_id,
                chunk_index=idx,
                cam_ids=all_cam_ids,
                sync_strategy=sync_strategy,
            )
            
            await manager.broadcast(session_id, {
                "type": "processing_started",
                "session_id": session_id,
                "chunk_index": idx,
            })

    except Exception as e:
        logger.error(f"❌ Failed to process uploaded chunk for {device_id}: {e}", exc_info=True)
        return {"status": "error", "detail": str(e)}

    return {"status": "success", "chunk": idx, "size": len(content)}


@router.post("/esp32-trigger")
async def esp32_trigger_http():
    logger.info("🤖 ESP32 HTTP trigger received")
    return await handle_trigger_logic()


# ── WebSocket endpoints ───────────────────────────────────────────────────────

@router.websocket("/ws/esp32")
async def websocket_esp32(websocket: WebSocket):
    await websocket.accept()
    active_esp32s.append(websocket)
    logger.info("🤖 Yolo:bit connected via WebSocket")
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("command") == "trigger":
                await handle_trigger_logic()
    except WebSocketDisconnect:
        active_esp32s.remove(websocket)
        logger.info("🤖 Yolo:bit disconnected")


@router.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    global dashboard_socket
    await websocket.accept()
    dashboard_socket = websocket
    client = websocket.client.host if websocket.client else "unknown"
    logger.info(f"🖥  Dashboard connected from {client}")

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("command") == "start":
                await handle_trigger_logic(data.get("session_id"))
            elif data.get("command") == "stop":
                await handle_trigger_logic()
    except WebSocketDisconnect:
        dashboard_socket = None
        logger.info("🖥  Dashboard disconnected")


@router.websocket("/ws/camera")
async def websocket_camera(websocket: WebSocket):
    await websocket.accept()
    active_cameras.append(websocket)
    cam_id = None
    client = websocket.client.host if websocket.client else "unknown"
    logger.info(f"📱 Camera connected from {client} — total: {len(active_cameras)}")

    # If session already active, immediately send start command so late-joining cameras start recording
    if current_active_session:
        try:
            await websocket.send_json({"command": "start", "session_id": current_active_session})
            logger.info(f"📱 Sent active session {current_active_session} to new camera")
        except Exception:
            pass

    try:
        while True:
            data = await websocket.receive_json()
            if not cam_id and "id" in data:
                cam_id = data["id"]
                logger.info(f"📱 Camera identified: id={cam_id}")
            if data.get("type") == "preview" and dashboard_socket:
                try:
                    await dashboard_socket.send_json(data)
                except Exception:
                    pass
    except WebSocketDisconnect:
        if websocket in active_cameras:
            active_cameras.remove(websocket)
        logger.info(f"📱 Camera disconnected: id={cam_id} — total: {len(active_cameras)}")
        if dashboard_socket and cam_id:
            try:
                await dashboard_socket.send_json({"type": "disconnect", "id": cam_id})
            except Exception:
                pass
