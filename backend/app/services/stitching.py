import logging
from pathlib import Path
from enum import Enum

import ffmpeg

logger = logging.getLogger(__name__)


class StitchLayout(str, Enum):
    HSTACK = "hstack"      # All cameras side by side horizontally
    VSTACK = "vstack"      # All cameras stacked vertically
    GRID_2x2 = "grid_2x2"  # 2×2 grid (up to 4 cameras)


def stitch_chunks(
    aligned_paths: dict[str, Path],
    output_path: Path,
    layout: StitchLayout = StitchLayout.HSTACK,
) -> Path:
    """
    Stitch multiple aligned video chunks into a single output video.

    Args:
        aligned_paths: ordered dict of cam_id → aligned file path
        output_path: destination path for stitched video
        layout: how to arrange the camera feeds

    Returns:
        Path to the stitched output file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cam_ids = list(aligned_paths.keys())
    n = len(cam_ids)

    inputs = [ffmpeg.input(str(aligned_paths[cam])) for cam in cam_ids]

    if layout == StitchLayout.HSTACK:
        filter_str = f"{''.join(f'[{i}:v]' for i in range(n))}hstack=inputs={n}[v]"
        audio_filter = f"{''.join(f'[{i}:a]' for i in range(n))}amix=inputs={n}[a]"
        combined = ffmpeg.filter(inputs, "hstack", inputs=n)
        audio = ffmpeg.filter([inp.audio for inp in inputs], "amix", inputs=n)

    elif layout == StitchLayout.VSTACK:
        combined = ffmpeg.filter(inputs, "vstack", inputs=n)
        audio = ffmpeg.filter([inp.audio for inp in inputs], "amix", inputs=n)

    elif layout == StitchLayout.GRID_2x2:
        if n < 4:
            raise ValueError("GRID_2x2 requires exactly 4 camera inputs")
        # Top row
        top = ffmpeg.filter([inputs[0], inputs[1]], "hstack", inputs=2)
        # Bottom row
        bottom = ffmpeg.filter([inputs[2], inputs[3]], "hstack", inputs=2)
        # Combine rows
        combined = ffmpeg.filter([top, bottom], "vstack", inputs=2)
        audio = ffmpeg.filter([inp.audio for inp in inputs], "amix", inputs=n)

    else:
        raise ValueError(f"Unknown layout: {layout}")

    (
        ffmpeg
        .output(combined, audio, str(output_path), vcodec="libx264", acodec="aac", preset="fast")
        .overwrite_output()
        .run(quiet=True)
    )

    logger.info(f"Stitched {n} cameras → {output_path.name} (layout={layout})")
    return output_path
