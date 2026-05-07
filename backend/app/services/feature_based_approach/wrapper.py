import os
import cv2
from pathlib import Path
import logging
from tqdm import tqdm

from app.services.feature_based_approach.utils import load_video, get_total_frames
from app.services.feature_based_approach.OTP import (
    detect_features,
    extract_features_from_frame,
    match_features,
    construct_trajectories,
    compute_fundamental_matrix,
    filter_trajectories,
    match_trajectories,
    synchronize_videos
)

logger = logging.getLogger(__name__)

def compute_feature_offsets(chunk_dir: Path, cam_ids: list[str]) -> dict[str, float]:
    """
    Computes offsets using a feature-based (CV) alignment approach.
    This method analyzes visual landmarks across cameras to determine temporal shifts.
    Since the core algorithm calculates offset in frames, we convert it to seconds
    based on the video's framerate.
    """
    if not cam_ids:
        return {}

    CAPTURE_FILES = []
    for cam_id in cam_ids:
        # Try multiple extensions
        video_path = None
        for ext in [".webm", ".mp4", ".mov", ".mkv"]:
            test_path = (chunk_dir / f"{cam_id}{ext}").resolve()
            if test_path.exists():
                video_path = test_path
                break
        
        if video_path:
            CAPTURE_FILES.append(video_path)
        else:
            logger.warning(f"No input file found for camera {cam_id} in {chunk_dir}")
    
    # Check if files exist
    valid_files = [f for f in CAPTURE_FILES if f.exists()]
    if len(valid_files) < 2:
        logger.warning("Not enough valid video files for feature sync.")
        return {cam_id: 0.0 for cam_id in cam_ids}
    
    # Fallback FPS to 30.0, will try to read from actual video
    fps = 30.0
    cap_for_fps = cv2.VideoCapture(str(valid_files[0]))
    if cap_for_fps.isOpened():
        fps = cap_for_fps.get(cv2.CAP_PROP_FPS) or 30.0
    cap_for_fps.release()

    total_frames = [get_total_frames(str(path)) for path in valid_files]
    videos = [load_video(str(path)) for path in valid_files]

    SEARCH_FRAMES = min(30, min(total_frames))

    first_frames = []
    first_frames_keypoints = []
    first_frames_descriptors = []
    trajectories_data = {}

    for i, (video_generator, frames_count) in enumerate(zip(videos, total_frames)):
        cam_name = cam_ids[i]
        
        cap_for_metadata = cv2.VideoCapture(str(valid_files[i]))
        height = int(cap_for_metadata.get(cv2.CAP_PROP_FRAME_HEIGHT))
        width = int(cap_for_metadata.get(cv2.CAP_PROP_FRAME_WIDTH))
        cap_for_metadata.release()

        left_percent = 0.15 
        roi_height = height
        roi_start_x = int(width * left_percent)
        roi_width = width - roi_start_x
        roi_start = (0, roi_start_x)
        roi_size = (roi_height, roi_width)

        best_frame = None
        best_kp = None
        best_desc = None
        max_kp = -1

        temp_cap = cv2.VideoCapture(str(valid_files[i]))
        for f_idx in range(SEARCH_FRAMES):
            ret, frame = temp_cap.read()
            if not ret:
                break
            kp, desc = detect_features(frame)
            if kp and len(kp) > max_kp:
                max_kp = len(kp)
                best_frame = frame.copy()
                best_kp = kp
                best_desc = desc
        temp_cap.release()
        
        if best_frame is None:
            temp_cap = cv2.VideoCapture(str(valid_files[i]))
            _, best_frame = temp_cap.read()
            best_kp, best_desc = detect_features(best_frame)
            temp_cap.release()

        first_frames.append(best_frame)
        first_frames_keypoints.append(best_kp)
        first_frames_descriptors.append(best_desc)

        trajectories = {}
        match_map = {} 

        p0 = best_kp
        desc0 = best_desc

        for frame_idx, frame in enumerate(video_generator):
            # To speed up, we might not need all frames if this takes too long,
            # but for 10s chunks, 300 frames should be okay.
            p1, desc1 = extract_features_from_frame(frame, roi_start, roi_size)
            matches = match_features(desc0, desc1)
            
            if len(matches) > 1:
                trajectories, match_map = construct_trajectories(matches, p0, p1, trajectories, match_map)

            p0 = p1
            desc0 = desc1

        if i > 0:
            F, fund_matches, p1, p2 = compute_fundamental_matrix(first_frames_keypoints[0], first_frames_descriptors[0], first_frames_keypoints[i], first_frames_descriptors[i])
            if F is None or F.shape != (3, 3):
                logger.warning(f"Failed to compute fundamental matrix for {cam_name}")
                filtered_trajectories = filter_trajectories(list(trajectories.values()), None)
            else:
                filtered_trajectories = filter_trajectories(list(trajectories.values()), F)
        else:
            filtered_trajectories = filter_trajectories(list(trajectories.values()), None)

        trajectories_data[cam_name] = filtered_trajectories

    ref_name = cam_ids[0]
    if len(trajectories_data) > 1:
        other_cams = [name for name in trajectories_data.keys() if name != ref_name]
        if other_cams:
            target_cam = other_cams[0]
            target_idx = cam_ids.index(target_cam)
            F, fund_matches, p1, p2 = compute_fundamental_matrix(first_frames_keypoints[0], first_frames_descriptors[0], first_frames_keypoints[target_idx], first_frames_descriptors[target_idx])
            if F is not None and F.shape == (3, 3):
                trajectories_data[ref_name] = filter_trajectories(trajectories_data[ref_name], F)

    sync_dict = {ref_name: 0.0}

    for i in range(1, len(cam_ids)):
        cam_name = cam_ids[i]
        if cam_name not in trajectories_data or not trajectories_data[cam_name]:
            sync_dict[cam_name] = 0.0
            continue

        matched_trajectories = match_trajectories(trajectories_data[ref_name], trajectories_data[cam_name])
        
        if not matched_trajectories:
            sync_dict[cam_name] = 0.0
            continue

        offsets = synchronize_videos(matched_trajectories)
        if isinstance(offsets, list) and len(offsets) >= 2:
            ref_offset = offsets[0]
            adjusted_offset = offsets[1] - ref_offset
            # offset is in frames, convert to seconds
            sync_dict[cam_name] = float(adjusted_offset / fps)
        else:
            sync_dict[cam_name] = 0.0

    return sync_dict
