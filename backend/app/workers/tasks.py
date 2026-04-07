import logging
from pathlib import Path

from app.workers.celery_app import celery_app
from app.services.sync_pipeline import run_sync_pipeline
from app.services.stitching import StitchLayout

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def process_chunk_set(
    self,
    session_id: str,
    chunk_index: int,
    cam_ids: list[str],
    layout: str = "hstack",
) -> dict:
    """
    Celery task to process a complete set of camera chunks.

    Triggered automatically when all cameras have uploaded for a given chunk_index.
    """
    try:
        logger.info(f"[Task] Processing session={session_id} chunk={chunk_index} cams={cam_ids}")

        output_path = run_sync_pipeline(
            session_id=session_id,
            chunk_index=chunk_index,
            cam_ids=cam_ids,
            layout=StitchLayout(layout),
        )

        return {
            "status": "completed",
            "session_id": session_id,
            "chunk_index": chunk_index,
            "output": str(output_path),
        }

    except Exception as exc:
        logger.error(f"[Task] Failed chunk={chunk_index} session={session_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc)
