from pathlib import Path
from datetime import datetime

# Diagnostic logging to the storage directory (mapped to host)
ERROR_LOG_PATH = Path("/app/storage/error.log")

def log_diag(message: str):
    """Fallback to standard print to avoid file lock issues."""
    print(f"DIAG: {message}", flush=True)
