import os
import subprocess
import time
import logging
import asyncio
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["live"])

# Directories
CHUNKS_DIR = Path("video_chunks")
SYNCED_DIR = Path("storage/synced")
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
SYNCED_DIR.mkdir(parents=True, exist_ok=True)

# Track connections
active_cameras: list[WebSocket] = []
active_esp32s: list[WebSocket] = []
dashboard_socket: WebSocket | None = None
current_active_session: str | None = None

# chunk_counters[device_id] = next chunk index
chunk_counters: dict[str, int] = {}


# ── Session control ───────────────────────────────────────────────────────────

async def handle_trigger_logic(session_id_from_dash: str | None = None):
    global current_active_session

    if current_active_session is None:
        # START
        session_id = session_id_from_dash or str(int(time.time()))
        current_active_session = session_id
        chunk_counters.clear()

        # Create per-session chunk dir
        session_dir = CHUNKS_DIR / session_id
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

        # Concatenate chunks for each device in the background
        asyncio.create_task(concatenate_session(stopped_session))

        return {"status": "stopped", "session_id": stopped_session}


async def concatenate_session(session_id: str):
    """FFmpeg-concatenate all saved chunks per device into one final MP4."""
    session_dir = CHUNKS_DIR / session_id
    if not session_dir.exists():
        return

    devices = set(p.stem.rsplit("_chunk_", 1)[0] for p in session_dir.glob("*_chunk_*.*"))
    logger.info(f"🎬 Concatenating {len(devices)} device(s) for session {session_id}")

    for device_id in devices:
        # Collect chunks in order
        chunks = sorted(session_dir.glob(f"{device_id}_chunk_*.*"),
                        key=lambda p: int(p.stem.rsplit("_chunk_", 1)[1]))
        if not chunks:
            continue

        # Detect extension from first chunk
        ext = chunks[0].suffix  # .mp4 or .webm

        # Write FFmpeg concat list
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
        logger.info(f"🎬 FFmpeg concat: {[str(c.name) for c in chunks]} → {out_file.name}")
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
):
    """Receive a media chunk from a camera and save it directly to disk."""
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

    # Determine extension from the MIME type / filename — works for Safari MP4 and Chrome WebM
    original_name = file.filename or ""
    if original_name.lower().endswith(".mp4") or (file.content_type or "").startswith("video/mp4"):
        ext = ".mp4"
    else:
        ext = ".webm"

    # Increment chunk counter for this device
    idx = chunk_counters.get(device_id, 0)
    chunk_counters[device_id] = idx + 1

    session_dir = CHUNKS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = session_dir / f"{device_id}_chunk_{idx:04d}{ext}"

    try:
        with open(chunk_path, "wb") as f:
            f.write(content)
        logger.info(f"✅ Saved chunk {idx:04d} for device={device_id}  size={len(content)} bytes  → {chunk_path.name}")
    except Exception as e:
        logger.error(f"❌ Failed to save chunk for {device_id}: {e}")
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
