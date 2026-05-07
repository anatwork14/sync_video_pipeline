import sys
import subprocess
import logging
from pathlib import Path
from collections import defaultdict

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Module-level cache so the YOLO and GCN models are only loaded once per process
_sesyn_dir_cache: Path | None = None
_gcn_model_cache = None
_pose_model_cache = None


def setup_sesyn_net() -> Path:
    """
    Ensures the Sync-Camera repository is cloned and its modules are in the Python path.
    Returns the path to the SeSyn-Net source directory.

    Raises:
        RuntimeError: if cloning fails
        FileNotFoundError: if the expected directory structure is not found
    """
    global _sesyn_dir_cache
    if _sesyn_dir_cache is not None:
        return _sesyn_dir_cache

    base_dir = Path(__file__).resolve().parent
    repo_dir = base_dir / "Sync-Camera"

    if not repo_dir.exists():
        logger.info("Sync-Camera repository not found locally. Attempting to clone...")
        try:
            subprocess.run(
                ["git", "clone", "https://github.com/Cocobaut/Sync-Camera.git", str(repo_dir)],
                check=True,
                capture_output=True,
                timeout=120,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone Sync-Camera repository: {e.stderr.decode('utf-8', errors='replace')}")
            raise RuntimeError(
                "Could not clone Sync-Camera repository. Ensure git is installed and network is available."
            ) from e
        except subprocess.TimeoutExpired:
            raise RuntimeError("Timed out while cloning Sync-Camera repository.")

    # Flexibly locate the SeSyn-Net source — handles both flat and nested layouts
    if (repo_dir / "SeSyn-Net-main" / "network").exists():
        sesyn_main_dir = repo_dir / "SeSyn-Net-main"
    elif (repo_dir / "network").exists():
        sesyn_main_dir = repo_dir
    else:
        subdirs = [d for d in repo_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
        found = [d for d in subdirs if (d / "network").exists()]
        if found:
            sesyn_main_dir = found[0]
        else:
            raise FileNotFoundError(
                f"Could not find SeSyn-Net source code in {repo_dir}. "
                "Expected a 'network' sub-directory."
            )

    if str(sesyn_main_dir) not in sys.path:
        sys.path.insert(0, str(sesyn_main_dir))

    _sesyn_dir_cache = sesyn_main_dir
    return sesyn_main_dir


def _get_models(sesyn_dir: Path):
    """
    Load and cache the YOLO-pose and Adjusted_GCN models.
    Models are loaded only once per process for performance.
    """
    global _gcn_model_cache, _pose_model_cache
    import torch
    from ultralytics import YOLO

    if _pose_model_cache is None:
        yolo_weights = sesyn_dir / "yolo11s-pose.pt"
        if not yolo_weights.exists():
            yolo_weights = Path("yolo11s-pose.pt")  # Let ultralytics auto-download
        logger.info("Initializing YOLO-pose model (first use)...")
        _pose_model_cache = YOLO(str(yolo_weights))

    if _gcn_model_cache is None:
        from network.adjusted_stgcn import Adjusted_GCN

        # Try internal repo path first, then fallback to global services path
        weights_path = sesyn_dir / "model" / "cmu_syn.pth"
        if not weights_path.exists():
            # Fallback: check the parent directory where the wrapper lives
            weights_path = Path(__file__).resolve().parent / "model" / "cmu_syn.pth"
            
        if not weights_path.exists():
            raise FileNotFoundError(
                f"SeSyn-Net model weights not found. Please place cmu_syn.pth at: "
                f"{Path(__file__).resolve().parent}/model/cmu_syn.pth"
            )

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Loading SeSyn-Net Adjusted_GCN model onto {device} (first use)...")
        checkpoint = torch.load(weights_path, map_location=device, weights_only=False)
        gcn_model = Adjusted_GCN(
            in_channels=3,
            layout="coco",
            strategy="spatial",
            edge_importance_weighting=True,
        )
        gcn_model.load_state_dict(checkpoint["model"])
        _gcn_model_cache = gcn_model.to(device).eval()

    return _pose_model_cache, _gcn_model_cache


def extract_keypoints_for_video(video_path: Path, model) -> np.ndarray:
    """
    Extracts pose keypoints using YOLO-pose for every frame in a video.

    Returns:
        np.ndarray of shape (3, 17, T, 1) — (xy+conf, joints, frames, persons)
    """
    import torch
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    results = model(str(video_path), stream=True, device=device, verbose=False)

    all_frames_data = []
    for result in results:
        if result.keypoints is not None and len(result.keypoints.data) > 0:
            kpts = result.keypoints.data[0].cpu().numpy()  # (17, 3)
        else:
            kpts = np.zeros((17, 3), dtype=np.float32)
        all_frames_data.append(kpts)

    if not all_frames_data:
        raise ValueError(f"No frames could be extracted from {video_path}")

    data = np.array(all_frames_data, dtype=np.float32)  # (T, 17, 3)
    data = np.transpose(data, (2, 1, 0))                # (3, 17, T)
    data = np.expand_dims(data, axis=-1)                 # (3, 17, T, 1)
    return data


def compute_sesyn_offsets(chunk_dir: Path, cam_ids: list[str]) -> dict[str, float]:
    """
    Compute temporal offsets using the SeSyn-Net GCN pose-based approach.

    Args:
        chunk_dir: directory containing video files named {cam_id}*.mp4
        cam_ids: ordered list of camera IDs; cam_ids[0] is the reference

    Returns:
        dict mapping cam_id -> offset_seconds (reference cam = 0.0)
    """
    import torch

    logger.info("Setting up SeSyn-Net environment...")
    sesyn_dir = setup_sesyn_net()

    try:
        from test_model import solve_least_squares_general
        from matching import corresponding
    except ImportError as e:
        logger.error(f"Failed to import SeSyn-Net modules: {e}")
        raise

    pose_model, gcn_model = _get_models(sesyn_dir)
    device = next(gcn_model.parameters()).device

    # ── Extract keypoints for every camera ─────────────────────────────────────
    cam_data: dict[str, np.ndarray] = {}
    fps_val = 30.0

    for cid in cam_ids:
        # Find the video file (support multiple extensions)
        video_files = []
        for ext in [".mp4", ".webm", ".mov", ".mkv"]:
            video_files += list(chunk_dir.glob(f"*{cid}*{ext}"))

        if not video_files:
            logger.warning(f"No video file found for camera {cid} — skipping.")
            continue

        video_path = video_files[0]

        cap = cv2.VideoCapture(str(video_path))
        fps_val = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()

        logger.info(f"Extracting keypoints for camera {cid} ({video_path.name})...")
        cam_data[cid] = extract_keypoints_for_video(video_path, pose_model)

    if len(cam_data) < 2:
        raise ValueError(
            f"SeSyn-Net requires at least 2 cameras with video files; "
            f"only found: {list(cam_data.keys())}"
        )

    # ── Sliding window GCN inference ────────────────────────────────────────────
    window_size = 120
    stride = 30
    root_id = cam_ids[0]

    # Use the shortest available sequence to bound the window loop
    total_frames = min(d.shape[2] for d in cam_data.values())
    if total_frames < window_size:
        raise ValueError(
            f"Videos are too short ({total_frames} frames) for SeSyn-Net "
            f"(requires at least {window_size} frames)."
        )

    # Aggregate measurements across ALL windows (mean is more robust than last-write)
    raw_measurements: dict[tuple, list[float]] = defaultdict(list)

    logger.info(f"Running sliding-window GCN inference ({total_frames} frames, window={window_size}, stride={stride})...")
    for start in range(0, total_frames - window_size + 1, stride):
        end = start + window_size

        for i, cid1 in enumerate(cam_ids):
            for j, cid2 in enumerate(cam_ids):
                if i >= j or cid1 not in cam_data or cid2 not in cam_data:
                    continue

                # Slice window: (3, 17, T, 1) -> (1, 3, T, 17, 1) [B, C, T, V, M]
                sub_d1 = cam_data[cid1][:, :, start:end, :]
                sub_d2 = cam_data[cid2][:, :, start:end, :]

                sub_d1 = np.expand_dims(np.transpose(sub_d1, (0, 2, 1, 3)), axis=0)
                sub_d2 = np.expand_dims(np.transpose(sub_d2, (0, 2, 1, 3)), axis=0)

                tensor1 = torch.tensor(sub_d1, dtype=torch.float32).to(device)
                tensor2 = torch.tensor(sub_d2, dtype=torch.float32).to(device)

                with torch.no_grad():
                    out1 = gcn_model(tensor1)
                    out2 = gcn_model(tensor2)

                label = torch.zeros(1).to(device)
                predicted_frames = corresponding(out1, out2, label)
                raw_measurements[(cid1, cid2)].append(predicted_frames.item())

    if not raw_measurements:
        raise ValueError("SeSyn-Net: no sliding window measurements could be computed.")

    # Median across windows for robustness against outlier frames
    measurements = {
        pair: float(np.median(vals)) for pair, vals in raw_measurements.items()
    }

    logger.info("Solving least-squares for global offsets...")
    opt_offsets = solve_least_squares_general(measurements, cam_ids)

    # Convert frames -> seconds
    final_offsets = {cid: float(frames / fps_val) for cid, frames in opt_offsets.items()}
    logger.info(f"SeSyn-Net final offsets (seconds): {final_offsets}")
    return final_offsets
