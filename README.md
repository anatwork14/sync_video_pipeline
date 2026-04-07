# 🎥 VideoSync Pipeline

> **Multi-Camera Video Capture, Sync & Delivery Platform**  
> Deadline (IoT Tier): **12/04/2026**

---

## Architecture Overview

```
📱 Phone A ─┐
📱 Phone B ─┼──► POST /upload-chunk ──► FastAPI ──► Celery Worker
📱 Phone C ─┘                                           │
                                                 Audio Cross-Corr
                                                 + FFmpeg Sync
                                                         │
                                              storage/synced/chunk_N.mp4
                                                         │
                                         Next.js Dashboard ◄── WebSocket
                                         (Status / Preview / Playback)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router + TypeScript) |
| Backend API | FastAPI (Python 3.11) |
| Task Queue | Celery + Redis |
| Database | PostgreSQL + SQLAlchemy + Alembic |
| Video Processing | FFmpeg + ffmpeg-python + scipy |
| Storage | Local FS → MinIO/S3 (Phase 3) |
| Real-time | WebSocket (Phase 1) → MediaMTX/HLS (Phase 2) |
| Containers | Docker + Docker Compose |
| Reverse Proxy | Nginx |

---

## Project Structure

```
video_sync_pipeline/
├── backend/          # FastAPI + Celery workers
├── frontend/         # Next.js dashboard
├── nginx/            # Reverse proxy config
├── docker-compose.yml
└── README.md
```

---

## Quick Start (Development)

### Prerequisites
- Docker & Docker Compose
- Node.js 20+
- Python 3.11+

### 1. Clone & Configure

```bash
git clone https://github.com/YOUR_ORG/video_sync_pipeline.git
cd video_sync_pipeline
cp .env.example .env
# Edit .env with your settings
```

### 2. Start All Services

```bash
docker compose up -d
```

Services started:
- `http://localhost:3000` — Next.js Dashboard
- `http://localhost:8000` — FastAPI (docs at `/docs`)
- `http://localhost:8000/ws/{session_id}` — WebSocket
- PostgreSQL on port `5432`
- Redis on port `6379`

### 3. Run without Docker (development)

**Backend:**
```bash
cd backend
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
# In another terminal:
celery -A app.workers.celery_app worker --loglevel=info
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/upload-chunk` | Upload video chunk from camera |
| `POST` | `/api/sessions` | Create recording session |
| `GET` | `/api/sessions` | List sessions |
| `GET` | `/api/sessions/{id}` | Session detail + chunk status |
| `GET` | `/api/sessions/{id}/offsets` | Camera sync offsets |
| `WS` | `/ws/{session_id}` | Real-time status updates |

---

## Development Phases

| Phase | Feature | Status |
|---|---|---|
| **1 — MVP** | Chunk upload + audio sync + FFmpeg stitch | 🚧 In Progress |
| **2 — Live** | Real-time RTMP/HLS streaming | 📋 Planned |
| **3 — Scale** | S3 storage, K8s, auth | 📋 Planned |

---

## Team

| Role | Members |
|---|---|
| IoT / Mobile (CE) | Hào, Tú, Minh Trường |
| Backend / CV (CS) | TBD |
| Frontend (CS) | TBD |

---

## Contributing

1. Branch from `main` → `feature/your-feature`
2. Run tests: `pytest backend/tests/`
3. Open PR with description of changes

---

## License

MIT
