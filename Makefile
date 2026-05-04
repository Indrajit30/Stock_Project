.PHONY: backend frontend infra precompute

backend:
	uvicorn backend.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev -- --host 0.0.0.0 --port 3000

infra:
	cd infra && docker compose up -d

precompute:
	curl -X POST http://localhost:8000/api/admin/precompute/run
