"""
Phase 2 — "Final Master" Pipeline
=================================
Concatenates ALL raw chunks per device into one long file, applies the
already-computed chunk-0 sync offset once, and stitches a single
high-bitrate master video.

This runs *after* the live preview pipeline has already processed every
chunk individually. It produces the final export-quality file.
"""
import logging
import subprocess
from pathlib import Path

import ffmpeg

from app.config import get_settings
from app.services.offset import load_offsets
from app.services.stitching import stitch_chunks, StitchLayout

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Step 1: Repair a continuous raw stream ───────────────────────────────────

def _repair_full_stream(raw_combined_path: Path, repaired_path: Path) -> bool:
    """
    WHY THIS EXISTS:
        After concatenating raw fragments (binary concat), the file has 
        one header at the start but might have timestamp discontinuities 
        or missing metadata at the fragment boundaries.
        
        This runs FFmpeg once on the entire multi-minute stream to 
        produce a clean, indexed, and seekable MP4.
    """
    cmd = [
        "ffmpeg", "-y",
        "-fflags", "+genpts+igndts+discardcorrupt",
        "-analyzeduration", "100M", "-probesize", "100M",
        "-i", str(raw_combined_path),
        "-c:v", "libx264", 
        "-preset", "medium", # Better quality for master
        "-crf", "18",        # High quality
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(repaired_path),
    ]
    logger.info(f"[master] Repairing full stream: {raw_combined_path.name} -> {repaired_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        logger.error(f"[master] Full stream repair failed: {result.stderr[-500:]}")
        return False
        
    return repaired_path.exists() and repaired_path.stat().st_size > 0


# ── Step 2: Concatenate all raw chunks for one device ───────────────────────────

def _concat_device_chunks(
    session_dir: Path,
    device_id: str,
    tmp_dir: Path,
) -> Path | None:
    """
    Gather chunk_{N}/{device_id}.* in order and perform binary concatenation.
    
    WHY BINARY CONCAT?
        Browser MediaRecorder fragments (especially MKV/WebM) are designed 
        to be appendable. Prepending chunk_0 (which has the header) to 
        all subsequent chunks creates a single continuous stream that 
        standard decoders can handle in one pass.
    """
    EXTS = [".mkv", ".webm", ".mp4", ".mov"]
    chunk_dirs = sorted(
        [d for d in session_dir.glob("chunk_*") if d.is_dir()],
        key=lambda d: int(d.name.split("_")[1]),
    )

    chunk_paths: list[Path] = []
    for chunk_dir in chunk_dirs:
        found = False
        for ext in EXTS:
            candidate = chunk_dir / f"{device_id}{ext}"
            if candidate.exists() and candidate.stat().st_size > 100:
                chunk_paths.append(candidate)
                found = True
                break
        if not found:
            logger.warning(f"[master] Missing chunk {chunk_dir.name} for device {device_id}")

    if not chunk_paths:
        logger.warning(f"[master] No raw chunks found for device={device_id}")
        return None

    logger.info(f"[master] Binary concatenating {len(chunk_paths)} raw chunks for device={device_id}")

    raw_combined = tmp_dir / f"{device_id}_raw_combined.tmp"
    try:
        with open(raw_combined, "wb") as outfile:
            for p in chunk_paths:
                with open(p, "rb") as infile:
                    outfile.write(infile.read())
    except Exception as e:
        logger.error(f"[master] Binary concat failed for {device_id}: {e}")
        return None

    repaired_mp4 = tmp_dir / f"{device_id}_full.mp4"
    if _repair_full_stream(raw_combined, repaired_mp4):
        # Clean up the large raw temp file
        raw_combined.unlink(missing_ok=True)
        return repaired_mp4
    
    return None


# ── Step 3: Align the long file using the stored offset ──────────────────────

def _align_full_video(
    input_path: Path,
    output_path: Path,
    offset_seconds: float,
) -> bool:
    """
    Apply the sync offset to the full-length video.
    Positive offset  → trim the start (camera started before reference).
    Negative offset  → pad the start (camera started after reference).

    WHY WE CAN DO THIS CLEANLY HERE:
        Unlike chunk-by-chunk alignment, we operate on one continuous file.
        There are no inter-chunk boundary discontinuities, so there are no
        audio pops or video freeze-frames at the seams.
    """
    has_audio_stream = False
    try:
        probe = ffmpeg.probe(str(input_path))
        has_audio_stream = any(
            s.get("codec_type") == "audio" for s in probe.get("streams", [])
        )
    except Exception:
        pass

    if offset_seconds >= 0:
        inp = ffmpeg.input(str(input_path), ss=offset_seconds)
        video = inp.video
        audio = inp.audio if has_audio_stream else None
    else:
        pad_ms = int(abs(offset_seconds) * 1000)
        inp = ffmpeg.input(str(input_path))
        video = inp.video.filter("tpad", start_duration=abs(offset_seconds))
        if has_audio_stream:
            audio = inp.audio.filter("adelay", f"{pad_ms}|{pad_ms}").filter("apad")
        else:
            audio = None

    out_kwargs = {"vcodec": "libx264", "preset": "fast", "crf": 18, "pix_fmt": "yuv420p"}
    if audio is not None:
        out_kwargs["acodec"] = "aac"
        stream = ffmpeg.output(video, audio, str(output_path), **out_kwargs)
    else:
        stream = ffmpeg.output(video, str(output_path), **out_kwargs)

    try:
        stream.overwrite_output().run(capture_stdout=True, capture_stderr=True)
        return output_path.exists() and output_path.stat().st_size > 0
    except ffmpeg.Error as e:
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
        logger.error(f"[master] Alignment FFmpeg error for {input_path.name}: {stderr[-400:]}")
        return False


import shutil
import os

# ── Maintenance Utilities ───────────────────────────────────────────────────

def _get_free_space_gb(path: Path) -> float:
    """Return free disk space in GB."""
    stat = os.statvfs(path)
    return (stat.f_bfree * stat.f_frsize) / (1024**3)

def _cleanup_master_tmp(tmp_dir: Path):
    """Remove temporary files after successful master render."""
    try:
        if tmp_dir.exists():
            logger.info(f"[master] Cleaning up temporary directory: {tmp_dir}")
            shutil.rmtree(tmp_dir)
    except Exception as e:
        logger.warning(f"[master] Cleanup failed for {tmp_dir}: {e}")


# ── Public entry point ────────────────────────────────────────────────────────

def run_master_pipeline(
    session_id: str,
    cam_ids: list[str],
    layout: StitchLayout = StitchLayout.HSTACK,
) -> Path:
    """
    Full Phase-2 "Final Master" pipeline.

    Steps:
      1. Load stored offsets (from Phase 1 chunk-0 processing).
      2. Concatenate ALL raw chunks per device into one long video.
      3. Apply the offset to each device's long video.
      4. Stitch all aligned long videos side by side into the master.

    Args:
        session_id: UUID string of the session.
        cam_ids:    list of device/camera IDs that participated.
        layout:     StitchLayout enum for the final composition.

    Returns:
        Path to the finished master video file.

    Raises:
        FileNotFoundError: if no offset.json was found (Phase 1 never completed).
        RuntimeError:      if no cameras could be aligned or disk space is low.
    """
    storage = Path(settings.storage_base).resolve()
    
    # -- Pre-flight check: Disk space --
    free_gb = _get_free_space_gb(storage)
    if free_gb < 2.0:  # Require at least 2GB free
        raise RuntimeError(f"[master] Disk space critical: only {free_gb:.2f}GB free on storage. Aborting render.")
    
    session_dir = storage / "raw" / session_id
    master_dir = (storage / "master" / session_id).resolve()
    master_dir.mkdir(parents=True, exist_ok=True)

    tmp_dir = master_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # -- Load offsets computed during Phase 1 (chunk_0) --
    offsets = load_offsets(session_dir)
    logger.info(f"[master] Loaded offsets for session {session_id}: {offsets} (Free Space: {free_gb:.2f}GB)")

    aligned_paths: dict[str, Path] = {}

    for cam_id in cam_ids:
        if cam_id not in offsets:
            logger.warning(f"[master] No offset for cam={cam_id}, skipping.")
            continue

        # Step A: Concatenate all chunks for this camera
        full_video = _concat_device_chunks(session_dir, cam_id, tmp_dir)
        if not full_video:
            logger.error(f"[master] Could not produce full video for cam={cam_id}. Skipping.")
            continue

        # Step B: Align the long video using the offset
        aligned_out = master_dir / f"{cam_id}_aligned.mp4"
        ok = _align_full_video(full_video, aligned_out, offsets[cam_id])
        if ok:
            aligned_paths[cam_id] = aligned_out
            logger.info(f"[master] ✅ cam={cam_id} aligned → {aligned_out.name}")
        else:
            logger.error(f"[master] Alignment failed for cam={cam_id}. Skipping.")

    if not aligned_paths:
        _cleanup_master_tmp(tmp_dir)
        raise RuntimeError(f"[master] No cameras could be aligned for session {session_id}")

    # Step C: Stitch all aligned videos into the final master
    master_output = storage / "master" / session_id / "master.mp4"
    try:
        stitch_chunks(aligned_paths, master_output, layout=layout)
        logger.info(f"[master] 🎬 Master video ready → {master_output}")
        
        # Step D: Final cleanup of temporary fragments
        _cleanup_master_tmp(tmp_dir)
        
    except Exception as e:
        logger.error(f"[master] Stitching failed: {e}")
        # Keep tmp files for debugging if it failed
        raise

    return master_output
