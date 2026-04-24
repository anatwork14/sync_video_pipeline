import cv2
import json
import os
import glob
import numpy as np

def create_synced_video(scene_dir):
    json_path = os.path.join(scene_dir, 'sync_results.json')
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return

    with open(json_path, 'r') as f:
        results = json.load(f)
    
    sync_dict = results.get('sync', {})
    if not sync_dict:
        print("No sync data found.")
        return
        
    videos_dir = os.path.join(os.path.dirname(os.path.dirname(scene_dir)), "videos")
    # if it's running from feature_based_approach but the target directory is scene297 in results:
    # Actually, let's just find the source videos.
    # We'll pass the source videos directory when calling.
    pass

import sys
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python evaluate_sync.py <path_to_scene_results_dir> <path_to_scene_videos_dir>")
        sys.exit(1)
        
    results_dir = sys.argv[1]
    videos_dir = sys.argv[2]
    
    json_path = os.path.join(results_dir, 'sync_results.json')
    if not os.path.exists(json_path):
        print(f"Cannot find {json_path}")
        sys.exit(1)
        
    with open(json_path, 'r') as f:
        data = json.load(f)
        
    sync_dict = data.get('sync', {})
    
    # Identify reference camera. It is usually cam01 with offset 0, implicitly.
    # Let's see what's in sync_dict
    all_cam_files = sorted(glob.glob(os.path.join(videos_dir, "*.mp4")))
    if not all_cam_files:
        print("No videos found.")
        sys.exit(1)
        
    # include ref cam
    ref_name = "cam01"
    sync_dict[ref_name] = 0
    
    # filter files available in sync_dict
    cam_names = []
    caps = {}
    offsets = {}
    fps = 30
    width, height = None, None
    for path in all_cam_files:
        c_name = os.path.splitext(os.path.basename(path))[0]
        if c_name in sync_dict:
            cam_names.append(c_name)
            cap = cv2.VideoCapture(path)
            caps[c_name] = cap
            offsets[c_name] = sync_dict[c_name]
            if width is None:
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = int(cap.get(cv2.CAP_PROP_FPS))
    
    if not caps:
        print("No matching videos found.")
        sys.exit(1)
        
    # The offset for camX means: when reference is at frame 0, camX is at frame `offset`.
    # To start them all at the same absolute time, we must start rendering at:
    # max_offset = max(0, -min_offset) ... wait.
    # Let's say cam01 = 0, cam03 = 230.
    # ref = f, cam03 = f - 230? Or f + 230?
    # In OTP.py: adjusted_offsets[1] = offsets[1] - ref_offset.
    # For now, let's treat offset as: frame_idx_of_camera = global_time + offset.
    # To avoid negative frames, we need global_time >= -min(offset) => global_start = max(0, -min(offset))
    # Actually, just set each camera's starting frame to max(0, offset - min_offset).
    min_offset = min(offsets.values())
    
    for c_name in cam_names:
        start_frame = offsets[c_name] - min_offset
        caps[c_name].set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        print(f"{c_name} start frame: {start_frame}")
        
    # Determine grid size
    n = len(cam_names)
    cols = int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / cols))
    
    # Resize frames to a smaller dimension so the grid isn't huge
    out_w, out_h = 320, 240
    
    out_path = os.path.join(results_dir, "synced_video.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(out_path, fourcc, fps, (cols * out_w, rows * out_h))
    
    print(f"Writing to {out_path} ...")
    
    frame_count = 0
    max_frames_to_write = 300 # Write 10 seconds worth
    while frame_count < max_frames_to_write:
        grid = np.zeros((rows * out_h, cols * out_w, 3), dtype=np.uint8)
        all_read = True
        
        for idx, c_name in enumerate(cam_names):
            ret, frame = caps[c_name].read()
            if not ret:
                all_read = False
                break
            
            frame_resized = cv2.resize(frame, (out_w, out_h))
            
            # Put text
            cv2.putText(frame_resized, c_name, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            r = idx // cols
            c = idx % cols
            
            grid[r * out_h: (r + 1) * out_h, c * out_w: (c + 1) * out_w] = frame_resized
            
        if not all_read and frame_count > 0:
            pass # Keep going if some streams finished? Or just break. Let's break.
            break
            
        out.write(grid)
        frame_count += 1
        if frame_count % 50 == 0:
            print(f"Processed {frame_count} frames...")
            
    out.release()
    for cap in caps.values():
        cap.release()
        
    print(f"Finished writing {out_path}!")
