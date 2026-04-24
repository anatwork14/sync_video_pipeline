import cv2
import json
import os
import sys
import numpy as np

def render_sync_video(results_dir, videos_dir, cam_a, cam_b, output_path=None):
    results_dir = os.path.abspath(results_dir)
    videos_dir = os.path.abspath(videos_dir)
    
    # 1. Load sync results
    json_path = os.path.join(results_dir, 'sync_results.json')
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)

    sync_dict = data.get('sync', {})
    metrics = data.get('metrics', {})

    if "cam01" not in sync_dict:
        sync_dict["cam01"] = 0

    if cam_a not in sync_dict or cam_b not in sync_dict:
        print(f"Error: One or both cameras ({cam_a}, {cam_b}) not found in sync results.")
        return

    # 2. Get video paths
    video_a_path = os.path.join(videos_dir, f"{cam_a}.mp4")
    video_b_path = os.path.join(videos_dir, f"{cam_b}.mp4")

    cap_a = cv2.VideoCapture(video_a_path)
    cap_b = cv2.VideoCapture(video_b_path)

    if not cap_a.isOpened() or not cap_b.isOpened():
         print(f"Error: Could not open videos. CapA: {cap_a.isOpened()}, CapB: {cap_b.isOpened()}")
         return

    # 3. Synchronize Logic
    offset_a = sync_dict[cam_a]
    offset_b = sync_dict[cam_b]
    delta_frames = offset_b - offset_a

    fps = int(cap_a.get(cv2.CAP_PROP_FPS)) or 30
    render_w, render_h = 640, 480
    out_width, out_height = render_w * 2, render_h + 100

    if output_path is None:
        output_path = os.path.join(results_dir, f"synced_{cam_a}_{cam_b}.mp4")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (out_width, out_height))

    # To START in sync, we skip the leading un-overlapped frames.
    start_a = max(0, offset_b - offset_a)
    start_b = max(0, offset_a - offset_b)

    print(f"Syncing: {cam_a} from frame {start_a} with {cam_b} from frame {start_b}")
    print(f"Relative Delta: {delta_frames} frames")

    cap_a.set(cv2.CAP_PROP_POS_FRAMES, start_a)
    cap_b.set(cv2.CAP_PROP_POS_FRAMES, start_b)

    frame_count = 0
    total_frames_a = int(cap_a.get(cv2.CAP_PROP_FRAME_COUNT))
    total_frames_b = int(cap_b.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # If the required start offset is larger than the video length, the videos don't actually overlap!
    # In this case, we'll force them to start from 0 so you can at least see both, but we'll show a warning.
    no_overlap_warning = False
    if start_a >= total_frames_a or start_b >= total_frames_b:
        print(f"WARNING: The calculated offset ({delta_frames}) is larger than the videos themselves!")
        print(f"They do not mathematically overlap. Force-playing both from frame 0.")
        start_a = 0
        start_b = 0
        cap_a.set(cv2.CAP_PROP_POS_FRAMES, start_a)
        cap_b.set(cv2.CAP_PROP_POS_FRAMES, start_b)
        no_overlap_warning = True

    while True:
        ret_a, frame_a = cap_a.read()
        ret_b, frame_b = cap_b.read()

        # If both videos are completely finished playing
        if not ret_a and not ret_b:
            break

        # If one video finishes before the other, format a black square for its side
        if ret_a:
            frame_a = cv2.resize(frame_a, (render_w, render_h))
        else:
            frame_a = np.zeros((render_h, render_w, 3), dtype=np.uint8)

        if ret_b:
            frame_b = cv2.resize(frame_b, (render_w, render_h))
        else:
            frame_b = np.zeros((render_h, render_w, 3), dtype=np.uint8)

        # Compose Canvas
        canvas = np.zeros((out_height, out_width, 3), dtype=np.uint8)
        canvas[0:render_h, 0:render_w] = frame_a
        canvas[0:render_h, render_w:out_width] = frame_b

        # Overlays
        cv2.putText(canvas, f"Cam: {cam_a}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(canvas, f"Cam: {cam_b}", (render_w + 20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        if no_overlap_warning:
            cv2.putText(canvas, "WARNING: OFFSET EXCEEDS VIDEO LENGTH (NO OVERLAP)", (out_width // 2 - 300, render_h + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        delta_seconds = delta_frames / fps
        cv2.putText(canvas, f"Calculated Delta: {delta_frames} frames ({delta_seconds:.3f}s)", (out_width // 2 - 200, render_h + 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        metrics_text = f"Synced: {metrics.get('cameras_successfully_synced', 'N/A')}/{metrics.get('total_cameras_found', 'N/A')} | Avg Matches: {metrics.get('average_matched_trajectories', 0):.1f}"
        cv2.putText(canvas, metrics_text, (out_width // 2 - 250, render_h + 85), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 1)

        out.write(canvas)
        frame_count += 1
        
        if frame_count % 300 == 0:
            print(f"Processed {frame_count} frames...")

    cap_a.release()
    cap_b.release()
    out.release()
    print(f"Successfully rendered {frame_count} frames to {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python render_2cam_sync.py <results_dir> <videos_dir> <cam_name_a> <cam_name_b>")
    else:
        render_sync_video(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
