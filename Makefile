.PHONY: all dev backend frontend clean

# Default target
all: dev

# Run both backend and frontend concurrently
dev:
	@echo "======================================"
	@echo " Starting Sluice Dev Environment "
	@echo "======================================"
	@trap 'echo "\nShutting down dev servers..."; kill 0' SIGINT SIGTERM EXIT; \
	$(MAKE) backend & \
	sleep 2 && \
	$(MAKE) frontend & \
	wait

# Run just the backend
backend:
	@echo "[1] Booting FastAPI backend (Port 8000)..."
	bash -c "source engine/.venv/bin/activate && uvicorn engine.api.server:app --port 8000 --reload"

# Run just the frontend
frontend:
	@echo "[2] Booting Tauri UI frontend..."
	cd frontend && pnpm tauri dev

# Clean up dev artifacts
clean:
	rm -rf .pytest_cache .ruff_cache __pycache__ engine/__pycache__ engine/api/__pycache__
	cd frontend && rm -rf node_modules src-tauri/target
