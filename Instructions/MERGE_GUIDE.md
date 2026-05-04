# Combining All 3 Workstreams — Merge Guide

## When everyone is ready to merge (do this on one device)

### Step 1 — Start infrastructure
```bash
cd infra && docker compose up -d
# Starts: Redis 6379, Qdrant 6333, PostgreSQL 5432
```

### Step 2 — Start backend (Person 1's work)
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# Also start the Arq worker:
python worker.py
```

### Step 3 — Trigger first precompute for top 50 tickers
```bash
# Hit this endpoint once to kick off nightly job manually:
curl -X POST http://localhost:8000/api/admin/precompute/run
# Takes ~5-10 min to cache all 50 tickers
# Watch progress: GET http://localhost:8000/api/health
```

### Step 4 — Start frontend (Person 3's work)
```bash
cd frontend
npm install
echo "VITE_API_URL=http://localhost:8000" > .env.local
npm run dev
# Opens on port 3000
```

### Step 5 — Verify the golden path
```
1. Open http://localhost:3000
2. Type "AAPL" in search bar, press Enter
3. Verify you see the skeleton UI within 1 second
4. Verify you see financials/snowflake fill in within 2 seconds
5. Verify reasoning trace steps appear one by one
6. Verify verdict (BUY/WAIT/AVOID) appears within 30 seconds
7. Click "Download PDF" — verify file downloads
8. Click "Peer Comparison" tab — verify table loads
```

---

## Key integration points (where the 3 workstreams touch)

| Interface | Person 1 provides | Person 2 provides | Person 3 consumes |
|-----------|-------------------|-------------------|-------------------|
| Data schemas | shared/schemas.py (Pydantic) | Same schemas | src/types/stock.ts (TypeScript mirror) |
| SSE events | `/api/stock/{ticker}/report/stream` route | Agent fills the SSE events | useStockStream hook |
| Static data events | financials, snowflake, filing_diff, sentiment | — | Renders immediately from cache |
| AI events | — | verdict, reasoning_steps | Shows verdict banner + trace |
| Export endpoints | `/api/stock/{ticker}/export/pdf` and `/excel` | — | ExportMenu download triggers |
| Peer data | `/api/peers/{ticker}` | peer narrative text | PeerComparison table |

---

## If something breaks at merge time

**CORS error in browser** → Add to backend/main.py:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], 
                   allow_methods=["*"], allow_headers=["*"])
```

**SSE events not reaching frontend** → Check nginx buffering header:
```python
# In the StreamingResponse headers:
"X-Accel-Buffering": "no"
```

**Pydantic validation errors** → shared/schemas.py is the source of truth. 
If Person 2's agent returns a field that doesn't match the schema, fix the agent output,
not the schema.

**TypeScript type errors** → Update src/types/stock.ts to match any schema changes.
Run `npx tsc --noEmit` to check.

**precompute fails for some tickers** → Normal. EDGAR data isn't perfect.
The frontend gracefully handles null sections with skeleton shimmer.
```
