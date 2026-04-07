"""
Orchestrates the full sync pipeline for a single chunk set.
Called by the Celery task after all cameras have uploaded.
"""
import logging
from pathlib import Path

from app.config import get_settings
from app.services.offset import compute_offsets, save_offsets, load_offsets
from app.services.alignment import align_all_chunks
from app.services.stitching import stitch_chunks, StitchLayout

logger = logging.getLogger(__name__)
settings = get_settings()


def run_sync_pipeline(
    session_id: str,
    chunk_index: int,
    cam_ids: list[str],
    layout: StitchLayout = StitchLayout.HSTACK,
) -> Path:
    """
    Full pipeline: offset discovery (chunk 0) → align → stitch.

    Returns:
        Path to the final synced output video.
    """
    storage = Path(settings.storage_base)
    session_dir = storage / "raw" / session_id
    chunk_dir = session_dir / f"chunk_{chunk_index}"
    aligned_dir = session_dir / f"chunk_{chunk_index}_aligned"
    synced_dir = storage / "synced" / session_id
    synced_dir.mkdir(parents=True, exist_ok=True)

    output_path = synced_dir / f"synced_chunk_{chunk_index}.mp4"

    # Step 1: Compute offsets — only on the first chunk
    if chunk_index == 0:
        logger.info(f"[{session_id}] Computing offsets from chunk_0 (clap sync)...")
        offsets = compute_offsets(chunk_dir, cam_ids)
        save_offsets(offsets, session_dir)
        logger.info(f"[{session_id}] Offsets saved: {offsets}")
    else:
        offsets = load_offsets(session_dir)
        logger.info(f"[{session_id}] Loaded existing offsets: {offsets}")

    # Step 2: Align chunks
    logger.info(f"[{session_id}] Aligning chunk_{chunk_index}...")
    aligned_paths = align_all_chunks(chunk_dir, aligned_dir, offsets)

    # Step 3: Stitch
    logger.info(f"[{session_id}] Stitching chunk_{chunk_index} with layout={layout}...")
    stitch_chunks(aligned_paths, output_path, layout)

    logger.info(f"[{session_id}] ✅ chunk_{chunk_index} done → {output_path}")
    return output_path
