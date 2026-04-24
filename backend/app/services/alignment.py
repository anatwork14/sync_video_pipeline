import logging
from pathlib import Path

import ffmpeg

logger = logging.getLogger(__name__)

def has_audio(input_path: Path) -> bool:
    try:
        probe = ffmpeg.probe(str(input_path))
        return any(stream.get('codec_type') == 'audio' for stream in probe.get('streams', []))
    except ffmpeg.Error:
        return False


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

    has_a = has_audio(input_path)

    if offset_seconds >= 0:
        # Camera started before reference → trim the beginning from both streams
        inp = ffmpeg.input(str(input_path), ss=offset_seconds)
        video = inp.video
        audio = inp.audio if has_a else None
    else:
        # Camera started after reference → pad start of both video and audio
        pad_duration_ms = int(abs(offset_seconds) * 1000)
        inp = ffmpeg.input(str(input_path))
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
        (
            stream
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        stderr = e.stderr.decode("utf-8") if e.stderr else "Unknown ffmpeg error"
        logger.error(f"FFmpeg Error in alignment:\n{stderr}")
        with open("/app/storage/ffmpeg_error.log", "a") as f:
            f.write(f"=== ALIGNMENT ERROR ({input_path.name}) ===\n{stderr}\n\n")
        raise RuntimeError(f"FFmpeg alignment failed: {stderr}")
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
