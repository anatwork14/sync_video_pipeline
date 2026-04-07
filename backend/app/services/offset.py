import json
import logging
from pathlib import Path

import ffmpeg
import numpy as np
from scipy.io import wavfile
from scipy.signal import correlate

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _extract_audio_wav(video_path: Path, out_wav: Path) -> None:
    """Extract mono 16kHz audio from a video file using FFmpeg."""
    (
        ffmpeg
        .input(str(video_path))
        .output(str(out_wav), ar=16000, ac=1, format="wav")
        .overwrite_output()
        .run(quiet=True)
    )


def compute_offsets(chunk_dir: Path, cam_ids: list[str], reference_cam: str = None) -> dict[str, float]:
    """
    Compute time offsets for each camera relative to the reference camera.

    Args:
        chunk_dir: directory containing {cam_id}.mp4 files
        cam_ids: list of camera IDs (e.g. ["camA", "camB", "camC"])
        reference_cam: the reference camera (default: first in list)

    Returns:
        dict mapping cam_id → offset_seconds (positive = this cam is LATE)
    """
    if reference_cam is None:
        reference_cam = cam_ids[0]

    # Extract audio for each camera
    audio_data: dict[str, np.ndarray] = {}
    sample_rate: int = 16000

    for cam_id in cam_ids:
        video_path = chunk_dir / f"{cam_id}.mp4"
        wav_path = chunk_dir / f"{cam_id}_audio.wav"
        _extract_audio_wav(video_path, wav_path)
        sr, data = wavfile.read(str(wav_path))
        sample_rate = sr
        # Normalize to float32
        audio_data[cam_id] = data.astype(np.float32) / np.iinfo(data.dtype).max

    ref_audio = audio_data[reference_cam]
    offsets: dict[str, float] = {}

    for cam_id in cam_ids:
        if cam_id == reference_cam:
            offsets[cam_id] = 0.0
            continue

        cam_audio = audio_data[cam_id]

        # Cross-correlate
        correlation = correlate(ref_audio, cam_audio, mode="full")
        lag_samples = correlation.argmax() - (len(cam_audio) - 1)
        offset_seconds = lag_samples / sample_rate

        # Positive offset means this cam needs to be trimmed by offset_seconds
        # (it started recording BEFORE the reference by that amount)
        offsets[cam_id] = float(offset_seconds)
        logger.info(f"Offset {cam_id} vs {reference_cam}: {offset_seconds:.4f}s")

    return offsets


def save_offsets(offsets: dict[str, float], session_dir: Path) -> Path:
    """Persist offsets to a JSON file in the session directory."""
    offset_file = session_dir / "offset.json"
    offset_file.write_text(json.dumps(offsets, indent=2))
    return offset_file


def load_offsets(session_dir: Path) -> dict[str, float]:
    """Load offsets from the session's offset.json."""
    offset_file = session_dir / "offset.json"
    if not offset_file.exists():
        raise FileNotFoundError(f"No offset.json found in {session_dir}")
    return json.loads(offset_file.read_text())
