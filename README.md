# StockResearch AI

Merged app from the three workstreams:

- `backend/` FastAPI API, SSE report streaming, exports, cache and data services
- `agent/` OpenAI-backed report synthesis, reasoning trace, citation guard
- `shared/` Pydantic contracts
- `frontend/` React + Vite UI
- `infra/` optional Redis, Qdrant, and Postgres docker compose

## Run Locally

```bash
cd /Users/arunnair/Desktop/AI_llm_project
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

In another terminal:

```bash
cd /Users/arunnair/Desktop/AI_llm_project/frontend
npm install
npm run dev -- --port 3000
```

Open `http://localhost:3000` and search a ticker.

If port `8000` is already in use, start the backend on another port and update
`frontend/.env.local` to match, for example `VITE_API_URL=http://localhost:8002`.

## Environment

Copy `.env.example` to `.env` and add `OPENAI_API_KEY` before generating reports:

```bash
cd /Users/arunnair/Desktop/AI_llm_project
cp .env.example .env
```

Then edit `.env`:

```bash
OPENAI_API_KEY=your_key_here
```

The app no longer falls back to mock stock reports. The backend fetches fundamentals from SEC Company Facts, price history from Stooq, and uses OpenAI for the final report synthesis. If the key is missing, the UI shows a setup error instead of fake data.

Redis, Qdrant, and Postgres are optional for local UI testing. If Redis is not running, the backend falls back to an in-memory cache.
