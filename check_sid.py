
import sqlite3
import os

db_path = "backend/sync_video.db"
# If the path is different in the container, it might be mapped differently.
# But let's try the common locations.
paths = ["backend/sync_video.db", "sync_video.db", "backend/app/sync_video.db"]
for db_path in paths:
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            sid = "959a00e9-0ee7-456c-bc61-37005cc671ad"
            cursor.execute("SELECT status, url FROM master_videos WHERE session_id = ?", (sid,))
            res = cursor.fetchone()
            if res:
                print(f"Session {sid} Master Status: {res[0]}, URL: {res[1]}")
            else:
                print(f"Session {sid} not found in master_videos table.")
                
            cursor.execute("SELECT status FROM sessions WHERE id = ?", (sid,))
            res = cursor.fetchone()
            if res:
                print(f"Session {sid} Status: {res[0]}")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            conn.close()
        break
else:
    print("DB not found.")
