import logging
from pathlib import Path

from app.workers.celery_app import celery_app
from app.services.sync_pipeline import run_sync_pipeline
from app.services.stitching import StitchLayout
from app.ws.redis_bridge import publish_event_sync

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def process_chunk_set(
    self,
    session_id: str,
    chunk_index: int,
    cam_ids: list[str],
    layout: str = "hstack",
    sync_strategy: str = "multividsynch",
) -> dict:
    """
    Celery task to process a complete set of camera chunks.

    Triggered automatically when all cameras have uploaded for a given chunk_index.
    On completion, publishes a 'chunk_done' event to Redis so the FastAPI
    WebSocket bridge can forward it to connected browser clients.
    """
    try:
        logger.info(f"[Task] Processing session={session_id} chunk={chunk_index} cams={cam_ids} strategy={sync_strategy}")

        output_path = run_sync_pipeline(
            session_id=session_id,
            chunk_index=chunk_index,
            cam_ids=cam_ids,
            layout=StitchLayout(layout),
            strategy_name=sync_strategy,
        )

        # Build the public-facing URL for the synced video file.
        # Nginx serves /var/www/synced/ → /static/synced/{session_id}/...
        # FastAPI also mounts /static/synced/ as a static directory.
        relative_url = f"/static/synced/{session_id}/{output_path.name}"

        # Publish the event via Redis so the FastAPI WS bridge can forward it.
        publish_event_sync({
            "type": "chunk_done",
            "session_id": session_id,
            "chunk_index": chunk_index,
            "url": relative_url,
        })

        logger.info(f"[Task] ✅ chunk={chunk_index} done → {output_path}")

        return {
            "status": "completed",
            "session_id": session_id,
            "chunk_index": chunk_index,
            "output": str(output_path),
            "strategy_used": sync_strategy,
            "url": relative_url,
        }

    except Exception as exc:
        logger.error(f"[Task] Failed chunk={chunk_index} session={session_id}: {exc}", exc_info=True)
        # Notify frontend of failure as well
        publish_event_sync({
            "type": "error",
            "session_id": session_id,
            "chunk_index": chunk_index,
            "message": str(exc),
        })
        raise self.retry(exc=exc)
