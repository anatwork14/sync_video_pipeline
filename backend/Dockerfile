FROM python:3.11-slim

# Install system deps:
#  - ffmpeg: video processing
#  - libmagic1: python-magic file type detection
#  - git: needed to auto-clone Sync-Camera for SeSyn-Net
#  - libgl1 / libglib2.0-0: required by OpenCV headless at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libmagic1 \
    git \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create storage directories
RUN mkdir -p storage/raw storage/synced

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
