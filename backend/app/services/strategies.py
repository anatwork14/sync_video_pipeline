from typing import Protocol
from pathlib import Path
import logging

from app.services.offset import compute_offsets as audio_compute_offsets

logger = logging.getLogger(__name__)

class SyncStrategy(Protocol):
    def compute_offsets(self, chunk_dir: Path, cam_ids: list[str]) -> dict[str, float]:
        """
        Compute time offsets for each camera relative to the reference camera (cam_ids[0]).
        Returns:
            dict mapping cam_id → offset_seconds (positive = this cam is LATE)
        """
        ...

class AudioSyncStrategy:
    def compute_offsets(self, chunk_dir: Path, cam_ids: list[str]) -> dict[str, float]:
        logger.info("Using Audio-Based Synchronization Strategy")
        return audio_compute_offsets(chunk_dir, cam_ids)

class FeatureSyncStrategy:
    def compute_offsets(self, chunk_dir: Path, cam_ids: list[str]) -> dict[str, float]:
        logger.info("Using Feature-Based (MultiVidSynch) Synchronization Strategy")
        from app.services.feature_based_approach.wrapper import compute_feature_offsets
        return compute_feature_offsets(chunk_dir, cam_ids)

def get_sync_strategy(name: str) -> SyncStrategy:
    if name.lower() == "audio":
        return AudioSyncStrategy()
    elif name.lower() == "feature" or name.lower() == "multividsynch":
        return FeatureSyncStrategy()
    else:
        logger.warning(f"Unknown sync strategy '{name}', falling back to Feature (MultiVidSynch)")
        return FeatureSyncStrategy()
