
import sqlite3
import os

db_path = "backend/sync_video.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, status, camera_count, created_at FROM sessions ORDER BY created_at DESC LIMIT 5")
        sessions = cursor.fetchall()
        print("Latest Sessions:")
        for s in sessions:
            print(f"ID: {s[0]}, Status: {s[1]}, Cams: {s[2]}, Created: {s[3]}")
            
        cursor.execute("SELECT session_id, status, url, finished_at FROM master_videos ORDER BY finished_at DESC LIMIT 5")
        masters = cursor.fetchall()
        print("\nLatest Master Videos:")
        for m in masters:
            print(f"Session: {m[0]}, Status: {m[1]}, URL: {m[2]}, Finished: {m[3]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
else:
    print(f"DB not found at {db_path}")
