import os
from pathlib import Path

session_id = "959a00e9-0ee7-456c-bc61-37005cc671ad"

# Try to run the pipeline manually
import sys
sys.path.insert(0, str(Path("backend").resolve()))

from app.services.sync_pipeline import run_full_sync_pipeline
from app.services.stitching import StitchLayout

# The camera ids based on the mkv files
cam_ids = ["5t462z", "ai9s53"]

try:
    print(f"Triggering manual sync pipeline for session {session_id}...")
    output_path = run_full_sync_pipeline(
        session_id=session_id,
        cam_ids=cam_ids,
        layout=StitchLayout.HSTACK,
        strategy_name="auto"
    )
    print(f"Success! Output saved to {output_path}")
except Exception as e:
    import traceback
    print(f"Error during manual pipeline run: {e}")
    traceback.print_exc()
