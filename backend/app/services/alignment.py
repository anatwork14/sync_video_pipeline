import logging
import subprocess
from pathlib import Path

import ffmpeg
from app.config import get_settings

logger = logging.getLogger(__name__)


def _remux_to_clean_mp4(input_path: Path, output_path: Path, header_path: Path = None) -> bool:
    """
    WHY THIS EXISTS:
        iOS Safari's MediaRecorder produces fragmented MP4/MKV containers
        where the 'moov' atom (metadata box) is only in the first chunk (chunk_0).
        Subsequent chunks (chunk_1, chunk_2...) are unplayable in isolation.

        This function remuxes the raw chunk into a standard MP4.
        If a 'header_path' is provided, we prepend it to the input data
        to restore the missing metadata.
    """
    temp_input = input_path
    cleanup_temp = False

    # If this is a non-zero chunk and we have a header, try to prepend it
    if header_path and header_path.exists() and header_path != input_path:
        try:
            logger.info(f"Injecting header from {header_path.name} into {input_path.name}")
            temp_input = input_path.with_suffix(".combined.tmp")
            with open(temp_input, "wb") as outfile:
                outfile.write(header_path.read_bytes())
                outfile.write(input_path.read_bytes())
            cleanup_temp = True
        except Exception as e:
            logger.error(f"Failed to create combined temp file for header injection: {e}")
            temp_input = input_path

    # We use -fflags +genpts+igndts+discardcorrupt to be as tolerant as possible
    cmd = [
        "ffmpeg", "-y",
        "-fflags", "+genpts+igndts+discardcorrupt",
        "-analyzeduration", "100M",
        "-probesize", "100M",
        "-i", str(temp_input),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(output_path),
    ]

    logger.info(f"Remuxing {input_path.name} (repair_mode={'header' if header_path else 'standalone'})")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if cleanup_temp and temp_input.exists():
        temp_input.unlink(missing_ok=True)

    # Some fragmented files cause FFmpeg to return non-zero even if output is fine.
    # We check if output file exists and has content.
    success = output_path.exists() and output_path.stat().st_size > 1000
    
    if not success:
        logger.warning(
            f"Remux failed for {input_path.name} (rc={result.returncode}).\n"
            f"stderr: {result.stderr[-500:]}"
        )
    elif result.returncode != 0:
        logger.info(f"Remux produced output but FFmpeg returned {result.returncode}. Continuing.")

    return success


def has_audio(input_path: Path) -> bool:
    if not input_path.exists():
        logger.error(f"Cannot probe audio: file does not exist: {input_path}")
        return False
    try:
        probe = ffmpeg.probe(
            str(input_path),
            analyzeduration="100M",
            probesize="100M",
        )
        return any(stream.get("codec_type") == "audio" for stream in probe.get("streams", []))
    except ffmpeg.Error as e:
        logger.warning(f"FFmpeg probe failed for {input_path}: {e}")
        return False


def is_valid_video(input_path: Path) -> bool:
    """
    Returns True if the file is a valid, decodable video with known pixel format.
    """
    if not input_path.exists() or input_path.stat().st_size < 1000: # Ignore tiny files
        return False
    try:
        # Use short timeout for probe
        probe = ffmpeg.probe(
            str(input_path),
            analyzeduration="50M",
            probesize="50M",
        )
        for stream in probe.get("streams", []):
            if stream.get("codec_type") == "video":
                # Check for valid pixel format
                pix_fmt = stream.get("pix_fmt")
                if pix_fmt and pix_fmt != "none":
                    return True
        return False
    except ffmpeg.Error:
        return False


def align_chunk(input_path: Path, output_path: Path, offset_seconds: float, chunk_index: int = 0) -> None:
    """
    Trim a video chunk to align it with the reference camera.
    """
    storage_base = Path(get_settings().storage_base).resolve()
    input_path = input_path.resolve()
    output_path = output_path.resolve()

    logger.info(f"Preparing to align: input={input_path}, output={output_path}, idx={chunk_index}")

    # ── Step 1: Repair fragmented/truncated file ──────────────────────────────
    working_path = input_path
    if not is_valid_video(input_path):
        logger.warning(f"⚠️ {input_path.name} is invalid/fragmented. Attempting repair...")
        
        # Try to find the header (chunk_0) for this device
        header_path = None
        if chunk_index > 0:
            # chunk_dir is session/chunk_N/
            # header is in session/chunk_0/
            session_dir = input_path.parent.parent
            for ext in [".mkv", ".webm", ".mp4", ".mov"]:
                hp = session_dir / "chunk_0" / f"{input_path.stem}{ext}"
                if hp.exists():
                    header_path = hp
                    break

        repaired_path = input_path.with_suffix(".repaired.mp4")
        if _remux_to_clean_mp4(input_path, repaired_path, header_path=header_path):
            logger.info(f"✅ Remux repair succeeded → {repaired_path.name}")
            working_path = repaired_path
            
            # If we injected a header, we MUST skip the injected part (chunk_0 duration)
            # Each chunk is approximately 2 seconds. 
            # A more robust way would be to probe the header_path duration.
            if header_path:
                try:
                    probe = ffmpeg.probe(str(header_path))
                    header_duration = float(probe["format"]["duration"])
                    logger.info(f"Header duration detected: {header_duration}s. Adjusting offset.")
                    # We need to skip the header duration PLUS apply the original offset
                    offset_seconds += header_duration
                except Exception as e:
                    logger.warning(f"Could not determine header duration, guessing 2.0s: {e}")
                    offset_seconds += 2.0
        else:
            raise RuntimeError(
                f"FFmpeg alignment failed for {input_path.name}: "
                f"File is broken and remux repair (header_injection={bool(header_path)}) failed."
            )

    # ── Step 2: Align (trim or pad) ───────────────────────────────────────────
    has_a = has_audio(working_path)
    logger.info(f"Processing alignment for {working_path.name} (has_audio={has_a}, offset={offset_seconds:.3f}s)")

    if offset_seconds >= 0:
        # Camera started before reference → trim the beginning
        inp = ffmpeg.input(str(working_path), ss=offset_seconds)
        video = inp.video
        audio = inp.audio if has_a else None
    else:
        # Camera started after reference → pad start
        pad_duration_ms = int(abs(offset_seconds) * 1000)
        inp = ffmpeg.input(str(working_path))
        video = inp.video.filter("tpad", start_duration=abs(offset_seconds))
        if has_a:
            audio = inp.audio.filter("adelay", f"{pad_duration_ms}|{pad_duration_ms}").filter("apad")
        else:
            audio = None

    out_kwargs = {"vcodec": "libx264", "preset": "fast"}
    if has_a:
        out_kwargs["acodec"] = "aac"
        stream = ffmpeg.output(video, audio, str(output_path), **out_kwargs)
    else:
        stream = ffmpeg.output(video, str(output_path), **out_kwargs)

    try:
        stream.overwrite_output().run(capture_stdout=True, capture_stderr=True)
    except ffmpeg.Error as e:
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else "Unknown ffmpeg error"
        logger.error(f"FFmpeg Error in alignment for {input_path.name}:\n{stderr}")

        # Persist for debugging
        log_file = storage_base / "ffmpeg_error.log"
        with open(log_file, "a") as lf:
            lf.write(f"=== ALIGNMENT ERROR ({input_path.name}) ===\nPath: {input_path}\n{stderr}\n\n")

        raise RuntimeError(f"FFmpeg alignment failed for {input_path.name}: {stderr[:500]}...")

    logger.info(f"Aligned {working_path.name} → {output_path.name} (offset={offset_seconds:.3f}s)")


def align_all_chunks(chunk_dir: Path, aligned_dir: Path, offsets: dict[str, float]) -> dict[str, Path]:
    """
    Align all cameras in a chunk directory.

    Returns:
        dict mapping cam_id → aligned file path
    """
    aligned_dir.mkdir(parents=True, exist_ok=True)
    aligned_paths: dict[str, Path] = {}

    # Extract chunk_index from directory name (e.g., "chunk_5" -> 5)
    try:
        chunk_index = int(chunk_dir.name.split("_")[1])
    except (IndexError, ValueError):
        chunk_index = 0

    for cam_id in offsets:
        # Try multiple extensions
        input_path = None
        for ext in [".mkv", ".webm", ".mp4", ".mov"]:
            test_path = (chunk_dir / f"{cam_id}{ext}").resolve()
            if test_path.exists():
                input_path = test_path
                break

        if not input_path:
            logger.warning(f"No input file for camera {cam_id} in {chunk_dir}. Skipping this camera for this chunk.")
            continue

        output_path = (aligned_dir / f"{cam_id}_aligned.mp4").resolve()
        try:
            align_chunk(input_path, output_path, offsets[cam_id], chunk_index=chunk_index)
            aligned_paths[cam_id] = output_path
        except Exception as e:
            logger.error(f"Failed to align camera {cam_id}: {e}")
            # Don't fail the whole session, just skip this camera for this chunk
            continue

    if not aligned_paths:
        raise RuntimeError(f"No cameras could be aligned in {chunk_dir}")

    return aligned_paths
