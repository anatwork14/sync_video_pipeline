"""
Orchestrates the full sync pipeline for a single chunk set.
Called by the Celery task after all cameras have uploaded.
"""
import logging
import subprocess
from pathlib import Path

from app.config import get_settings
from app.services.offset import save_offsets, load_offsets
from app.services.alignment import align_all_chunks
from app.services.stitching import stitch_chunks, StitchLayout
from app.services.strategies import get_sync_strategy

logger = logging.getLogger(__name__)
settings = get_settings()


def _repair_full_stream(raw_combined_path: Path, repaired_path: Path) -> bool:
    """
    Repair a concatenated raw stream into a clean MP4.
    """
    cmd = [
        "ffmpeg", "-y",
        "-fflags", "+genpts+igndts+discardcorrupt",
        "-analyzeduration", "100M", "-probesize", "100M",
        "-i", str(raw_combined_path),
        "-c:v", "libx264", 
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(repaired_path),
    ]
    logger.info(f"Repairing full stream: {raw_combined_path.name} -> {repaired_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        logger.error(f"Full stream repair failed: {result.stderr[-500:]}")
        return False
        
    return repaired_path.exists() and repaired_path.stat().st_size > 0


def _concat_camera_chunks(session_dir: Path, cam_ids: list[str]) -> dict[str, Path]:
    """
    Concatenate all chunks for each camera into full videos.
    Returns dict cam_id -> full_video_path
    """
    full_videos = {}
    for cam_id in cam_ids:
        chunk_paths = []
        chunk_dirs = sorted(
            [d for d in session_dir.glob("chunk_*") if d.is_dir()],
            key=lambda d: int(d.name.split("_")[1]),
        )
        for chunk_dir in chunk_dirs:
            chunk_file = chunk_dir / f"{cam_id}.mp4"
            if chunk_file.exists():
                chunk_paths.append(chunk_file)
        
        if not chunk_paths:
            logger.warning(f"No chunks found for cam {cam_id}")
            continue
        
        raw_combined_path = session_dir / f"raw_combined_{cam_id}.mp4"
        logger.info(f"Binary concatenating {len(chunk_paths)} chunks for {cam_id} -> {raw_combined_path}")
        
        # Binary concat
        with open(raw_combined_path, "wb") as outfile:
            for chunk in chunk_paths:
                with open(chunk, "rb") as infile:
                    outfile.write(infile.read())
        
        # Repair the full stream
        repaired_path = session_dir / f"full_{cam_id}.mp4"
        if _repair_full_stream(raw_combined_path, repaired_path):
            logger.info(f"✅ Repair succeeded for {cam_id} -> {repaired_path}")
            full_videos[cam_id] = repaired_path
        else:
            logger.error(f"Repair failed for {cam_id}, using raw combined")
            full_videos[cam_id] = raw_combined_path
    
    return full_videos


def run_full_sync_pipeline(
    session_id: str,
    cam_ids: list[str],
    layout: StitchLayout = StitchLayout.HSTACK,
    strategy_name: str = "auto",
) -> Path:
    """
    Full pipeline for full videos: concat chunks -> compute offsets -> align -> stitch.
    """
    from app.ws.redis_bridge import publish_event_sync
    storage = Path(settings.storage_base).resolve()
    logger.info(f"[{session_id}] Resolved storage base: {storage}")
    
    session_dir = storage / "raw" / session_id
    aligned_dir = (session_dir / "aligned").resolve()
    synced_dir = (storage / "synced" / session_id).resolve()
    
    synced_dir.mkdir(parents=True, exist_ok=True)
    aligned_dir.mkdir(parents=True, exist_ok=True)

    output_path = synced_dir / "synced_full.mp4"

    # Step 1: Concatenate all chunks for each camera
    logger.info(f"[{session_id}] Concatenating chunks for all cameras...")
    publish_event_sync({
        "type": "concatenating",
        "session_id": session_id,
        "message": "Combining video chunks into full videos...",
    })
    full_videos = _concat_camera_chunks(session_dir, cam_ids)
    if not full_videos:
        raise ValueError("No full videos created")

    # Step 2: Compute offsets using full videos
    logger.info(f"[{session_id}] Computing offsets from full videos using {strategy_name} strategy...")
    publish_event_sync({
        "type": "computing_offsets",
        "session_id": session_id,
        "message": f"Computing offsets using {strategy_name} strategy...",
    })
    strategy = get_sync_strategy(strategy_name)
    
    video_paths = {}
    for cam_id, path in full_videos.items():
        new_path = session_dir / f"{cam_id}.mp4"
        path.rename(new_path)
        video_paths[cam_id] = new_path

    offsets = strategy.compute_offsets(session_dir, cam_ids)
    save_offsets(offsets, session_dir)
    logger.info(f"[{session_id}] Offsets saved: {offsets}")

    # Step 3: Align full videos
    logger.info(f"[{session_id}] Aligning full videos...")
    publish_event_sync({
        "type": "aligning",
        "session_id": session_id,
        "message": "Trimming and aligning video streams...",
    })
    aligned_paths = align_all_chunks(session_dir, aligned_dir, offsets)

    # Step 4: Stitch
    logger.info(f"[{session_id}] Stitching with layout={layout}...")
    publish_event_sync({
        "type": "stitching",
        "session_id": session_id,
        "message": "Stitching videos into combined layout...",
    })
    stitch_chunks(aligned_paths, output_path, layout)

    logger.info(f"[{session_id}] ✅ Full sync done → {output_path}")
    return output_path


def run_sync_pipeline(
    session_id: str,
    chunk_index: int,
    cam_ids: list[str],
    layout: StitchLayout = StitchLayout.HSTACK,
    strategy_name: str = "auto",
) -> Path:
    """
    Full pipeline: offset discovery (chunk 0) → align → stitch.

    Returns:
        Path to the final synced output video.
    """
    from app.ws.redis_bridge import publish_event_sync
    storage = Path(settings.storage_base).resolve()
    logger.info(f"[{session_id}] Resolved storage base: {storage}")
    
    session_dir = storage / "raw" / session_id
    chunk_dir = (session_dir / f"chunk_{chunk_index}").resolve()
    aligned_dir = (session_dir / f"chunk_{chunk_index}_aligned").resolve()
    synced_dir = (storage / "synced" / session_id).resolve()
    
    logger.info(f"[{session_id}] Chunk dir: {chunk_dir}")
    synced_dir.mkdir(parents=True, exist_ok=True)

    output_path = synced_dir / f"synced_chunk_{chunk_index}.mp4"

    # Step 1: Compute offsets — only on the first chunk
    if chunk_index == 0:
        logger.info(f"[{session_id}] Computing offsets from chunk_0 using {strategy_name} strategy...")
        publish_event_sync({
            "type": "computing_offsets",
            "session_id": session_id,
            "chunk_index": chunk_index,
            "message": f"Computing offsets using {strategy_name} strategy...",
        })
        strategy = get_sync_strategy(strategy_name)
        offsets = strategy.compute_offsets(chunk_dir, cam_ids)
        save_offsets(offsets, session_dir)
        logger.info(f"[{session_id}] Offsets saved: {offsets}")
    else:
        offsets = load_offsets(session_dir)
        logger.info(f"[{session_id}] Loaded existing offsets: {offsets}")

    # Step 2: Align chunks
    logger.info(f"[{session_id}] Aligning chunk_{chunk_index}...")
    publish_event_sync({
        "type": "aligning",
        "session_id": session_id,
        "chunk_index": chunk_index,
        "message": "Trimming and aligning video streams...",
    })
    aligned_paths = align_all_chunks(chunk_dir, aligned_dir, offsets)

    # Step 3: Stitch
    logger.info(f"[{session_id}] Stitching chunk_{chunk_index} with layout={layout}...")
    publish_event_sync({
        "type": "stitching",
        "session_id": session_id,
        "chunk_index": chunk_index,
        "message": "Stitching videos into combined layout...",
    })
    stitch_chunks(aligned_paths, output_path, layout)

    logger.info(f"[{session_id}] ✅ chunk_{chunk_index} done → {output_path}")
    return output_path
