.PHONY: help setup up down logs clean restart shell-backend shell-frontend tunnel

help:
	@echo "🎥 VideoSync Pipeline - Management Commands"
	@echo ""
	@echo "Usage:"
	@echo "  make setup           - Initialize environment (.env) and create storage folders"
	@echo "  make up              - Build and start all services in detached mode"
	@echo "  make down            - Stop and remove all containers"
	@echo "  make logs            - Tail logs for all services"
	@echo "  make clean           - Wipe all raw and synced video data (CAUTION)"
	@echo "  make restart         - Restart all containers"
	@echo "  make tunnel          - Start Cloudflare Tunnel (primary)"
	@echo "  make lt              - Start LocalTunnel (fallback if Cloudflare is down)"
	@echo "  make shell-backend   - Open a shell in the backend container"
	@echo "  make shell-frontend  - Open a shell in the frontend container"

setup:
	@echo "Setting up environment..."
	@if [ ! -f .env ]; then cp .env.example .env; echo ".env created from .env.example"; fi
	@mkdir -p backend/storage/raw backend/storage/synced backend/video_chunks
	@echo "Storage directories initialized."

up: setup
	docker-compose up -d --build

down:
	docker-compose down

logs:
	docker-compose logs -f

restart:
	docker-compose restart

clean:
	@echo "Cleaning storage directories..."
	rm -rf backend/storage/raw/* backend/storage/synced/*
	@echo "Done."

tunnel:
	python3 run_tunnel.py

lt:
	python3 run_localtunnel.py

shell-backend:
	docker-compose exec backend /bin/bash

shell-frontend:
	docker-compose exec frontend /bin/sh
