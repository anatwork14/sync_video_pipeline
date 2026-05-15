import os
import glob

raw_dir = "backend/storage/raw"
synced_dir = "backend/storage/synced"

if not os.path.exists(raw_dir):
    print("No raw directory.")
    exit(0)

# Get the most recent session directory in raw
sessions = [os.path.join(raw_dir, d) for d in os.listdir(raw_dir) if os.path.isdir(os.path.join(raw_dir, d))]
if not sessions:
    print("No sessions found.")
    exit(0)

latest_session_raw = max(sessions, key=os.path.getmtime)
session_id = os.path.basename(latest_session_raw)

print(f"Latest Session ID: {session_id}")

# Check chunks
chunk_dirs = glob.glob(f"{latest_session_raw}/chunk_*")
print(f"Found {len(chunk_dirs)} chunks in raw.")

# Check for TS files or full mp4s
for f in os.listdir(latest_session_raw):
    if f.endswith(".ts") or f.endswith(".mp4"):
        path = os.path.join(latest_session_raw, f)
        size_mb = os.path.getsize(path) / (1024 * 1024)
        print(f"Intermediate/Full file: {f} - {size_mb:.2f} MB")

# Check synced
synced_file = os.path.join(synced_dir, session_id, "synced_full.mp4")
if os.path.exists(synced_file):
    size_mb = os.path.getsize(synced_file) / (1024 * 1024)
    print(f"\nFinal Master Video: {synced_file} - {size_mb:.2f} MB")
else:
    print(f"\nNo final master video found at {synced_file}")
