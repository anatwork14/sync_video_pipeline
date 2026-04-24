import logging
from pathlib import Path
from enum import Enum

import ffmpeg

logger = logging.getLogger(__name__)

def has_audio(input_path: Path) -> bool:
    try:
        probe = ffmpeg.probe(str(input_path))
        return any(stream.get('codec_type') == 'audio' for stream in probe.get('streams', []))
    except ffmpeg.Error:
        return False


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
    audio_inputs = [inp.audio for cam, inp in zip(cam_ids, inputs) if has_audio(aligned_paths[cam])]

    if layout == StitchLayout.HSTACK:
        combined = ffmpeg.filter(inputs, "hstack", inputs=n)
    elif layout == StitchLayout.VSTACK:
        combined = ffmpeg.filter(inputs, "vstack", inputs=n)
    elif layout == StitchLayout.GRID_2x2:
        if n < 4:
            raise ValueError("GRID_2x2 requires exactly 4 camera inputs")
        # Top row
        top = ffmpeg.filter([inputs[0], inputs[1]], "hstack", inputs=2)
        # Bottom row
        bottom = ffmpeg.filter([inputs[2], inputs[3]], "hstack", inputs=2)
        # Combine rows
        combined = ffmpeg.filter([top, bottom], "vstack", inputs=2)
    else:
        raise ValueError(f"Unknown layout: {layout}")

    out_kwargs = {"vcodec": "libx264", "preset": "fast"}
    if audio_inputs:
        audio = ffmpeg.filter(audio_inputs, "amix", inputs=len(audio_inputs))
        out_kwargs["acodec"] = "aac"
        stream = ffmpeg.output(combined, audio, str(output_path), **out_kwargs)
    else:
        stream = ffmpeg.output(combined, str(output_path), **out_kwargs)

    try:
        (
            stream
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        stderr = e.stderr.decode("utf-8") if e.stderr else "Unknown ffmpeg error"
        logger.error(f"FFmpeg Error in stitching:\n{stderr}")
        with open("/app/storage/ffmpeg_error.log", "a") as f:
            f.write(f"=== STITCHING ERROR ({output_path.name}) ===\n{stderr}\n\n")
        raise RuntimeError(f"FFmpeg stitching failed: {stderr}")

    logger.info(f"Stitched {n} cameras → {output_path.name} (layout={layout})")
    return output_path
