import logging
from pathlib import Path

import ffmpeg

logger = logging.getLogger(__name__)


def align_chunk(input_path: Path, output_path: Path, offset_seconds: float) -> None:
    """
    Trim a video chunk to align it with the reference camera.

    Args:
        input_path: path to the raw camera chunk (.mp4)
        output_path: path to save the aligned chunk
        offset_seconds: positive = trim from start (cam started early),
                        negative = pad with silence/black (cam started late)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if offset_seconds >= 0:
        # Camera started before reference → trim the beginning
        stream = ffmpeg.input(str(input_path), ss=offset_seconds)
    else:
        # Camera started after reference → add black video + silent audio at start
        # Pad using tpad/apad filters
        stream = ffmpeg.input(str(input_path))
        stream = stream.filter("tpad", start_duration=abs(offset_seconds))

    (
        stream
        .output(str(output_path), vcodec="libx264", acodec="aac", preset="fast")
        .overwrite_output()
        .run(quiet=True)
    )
    logger.info(f"Aligned {input_path.name} → {output_path.name} (offset={offset_seconds:.3f}s)")


def align_all_chunks(chunk_dir: Path, aligned_dir: Path, offsets: dict[str, float]) -> dict[str, Path]:
    """
    Align all cameras in a chunk directory.

    Returns:
        dict mapping cam_id → aligned file path
    """
    aligned_dir.mkdir(parents=True, exist_ok=True)
    aligned_paths: dict[str, Path] = {}

    for cam_id, offset in offsets.items():
        input_path = chunk_dir / f"{cam_id}.mp4"
        output_path = aligned_dir / f"{cam_id}_aligned.mp4"
        align_chunk(input_path, output_path, offset)
        aligned_paths[cam_id] = output_path

    return aligned_paths
