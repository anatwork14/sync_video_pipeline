# 🎥 VideoSync Pipeline

> **Multi-Camera Real-Time Video Capture, Synchronization & Processing Platform**

The **VideoSync Pipeline** is an advanced IoT/Cloud platform designed for multi-perspective video capture. It enables multiple devices (mobile phones, ESP32s, or web cams) to record synchronized video chunks, which are then aligned in real-time using audio cross-correlation and visual feature matching.

---

## 🏗 Architecture & Data Flow

### 1. Live Synchronization Flow
Unlike traditional video processing that waits for a recording to finish, this pipeline uses a **per-chunk synchronization** strategy:

1.  **Orchestration**: The Next.js Dashboard or an ESP32 trigger sends a `start` command via WebSockets to all connected cameras.
2.  **Capture**: Each camera records small video chunks (e.g., 5-10 seconds) and uploads them immediately.
3.  **State Management**: The FastAPI backend tracks incoming chunks in a PostgreSQL database.
4.  **Automatic Trigger**: As soon as all expected cameras have uploaded the same chunk index (e.g., `chunk_0`), a Celery task is dispatched.
5.  **Processing**:
    *   **Audio Sync**: Discovery of precise temporal offsets using audio fingerprinting.
    *   **FFmpeg Stitch**: Trimming and aligning videos based on discovered offsets.
6.  **Delivery**: The synchronized chunk is saved to `storage/synced/` and can be previewed immediately on the dashboard.

### 2. Storage Hierarchy
```text
backend/storage/
├── raw/
│   └── {session_id}/
│       └── chunk_{index}/
│           ├── cam_1.mp4
│           └── cam_2.mp4
├── synced/
│   ├── chunk_{index}_synced.mp4  # Real-time output
│   └── session_{id}_final.mp4    # Fallback full session
└── temp/                         # Intermediate processing files
```

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Next.js 15 (App Router, TypeScript, Tailwind CSS) |
| **Backend API** | FastAPI (Python 3.11, Pydantic v2) |
| **Task Queue** | Celery + Redis |
| **Database** | PostgreSQL + SQLAlchemy + Alembic |
| **Video Engine** | FFmpeg + Scipy (Audio Analysis) + MultiVidSynch (CV) |
| **Infrastructure** | Docker + Docker Compose + Nginx |

---

## 🚀 Quick Start

### 1. Prerequisites
- [Docker & Docker Compose](https://www.docker.com/)
- [FFmpeg](https://ffmpeg.org/) (for local development without Docker)

### 2. Environment Setup
```bash
# Clone the repository
git clone https://github.com/teobun/sync_video_pipeline.git
cd sync_video_pipeline

# Create your environment file
cp .env.example .env
```
*Edit `.env` to configure your database credentials and storage paths if necessary.*

### 3. Launching the Services
The easiest way to run the entire pipeline is via Docker Compose:
```bash
docker compose up -d --build
```

**Services will be available at:**
- **Dashboard**: `http://localhost:3000`
- **Backend API**: `http://localhost:8000`
- **Interactive Docs**: `http://localhost:8000/docs`
- **Nginx Entry**: `http://localhost:80` (Proxies to frontend/backend)

---

## 📱 Using the System

### Starting a Session
1.  Open the **Dashboard** (`localhost:3000`).
2.  Connect your cameras (using the Camera view on mobile or secondary tabs).
3.  Click **"Start Recording"** on the dashboard.
4.  Cameras will begin uploading chunks. Monitor the **Celery Logs** to see real-time processing:
    ```bash
    docker compose logs -f worker
    ```

### WebSocket Events
The system communicates state changes via `ws://localhost:8000/ws/{session_id}`:
- `chunk_uploaded`: Fired when a camera finishes uploading a segment.
- `processing_started`: Fired when a full set of chunks is ready for sync.
- `chunk_done`: Fired when the synchronized segment is ready for viewing.

---

## 🛠 Troubleshooting

- **Connection Refused**: Ensure Docker services are healthy (`docker compose ps`).
- **FFmpeg Error**: Check if the uploaded chunks have audio tracks; the `multividsynch` strategy relies on audio for initial alignment.
- **WebSocket Timeout**: If using a tunnel (like Cloudflare or Ngrok), ensure the WebSocket protocol is enabled in the tunnel configuration.

---

## 👨‍💻 Project Structure
- `backend/`: FastAPI application, Celery tasks, and database models.
- `frontend/`: Next.js 15 dashboard for monitoring and session control.
- `MultiVidSynch/`: Submodule containing core computer vision alignment algorithms.
- `nginx/`: Configuration for the reverse proxy.

---

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.
