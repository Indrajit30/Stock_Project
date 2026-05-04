# Shared Contracts — StockResearch AI

## Quick Start

### Run mock server (for frontend dev while backend is being built)
```bash
PYTHONPATH=. python shared/mock_server.py
# Serves on http://localhost:8001
```

### Run real backend
```bash
make dev
# Serves on http://localhost:8000
```

### Switch frontend between mock and real
Set `VITE_API_URL` in your frontend `.env.local`:
```
VITE_API_URL=http://localhost:8000
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check — Redis, Qdrant status |
| GET | `/api/stock/{ticker}/report` | Full StockReport (cached or 202+job_id) |
| GET | `/api/stock/{ticker}/report/stream` | SSE stream of report sections |
| GET | `/api/stock/{ticker}/filing-diff` | 10-Q diff vs prior quarter |
| GET | `/api/stock/{ticker}/insider-cluster` | Insider buying cluster signal |
| GET | `/api/stock/{ticker}/congressional-trades` | STOCK Act disclosures |
| GET | `/api/stock/{ticker}/sentiment` | Reddit sentiment pulse |
| GET | `/api/stock/{ticker}/snowflake` | Snowflake scores (0–10 per axis) |
| GET | `/api/stock/{ticker}/price-history?days=365` | OHLCV price history |
| GET | `/api/stock/{ticker}/export/pdf` | Download PDF report |
| GET | `/api/stock/{ticker}/export/excel` | Download Excel workbook |
| GET | `/api/peers/{ticker}` | Peer comparison list |
| GET | `/api/peers/{ticker}/compare?metrics=pe_ratio,ev_ebitda` | Structured peer table |
| GET | `/api/peers/{ticker}/superinvestor-cluster` | 13F superinvestor cluster |
| GET | `/api/jobs/{job_id}/status` | Poll background job status |

## SSE Event Protocol (`/report/stream`)

```
data: {"event": "section_start", "section": "overview"}
data: {"event": "data", "section": "financials", "payload": {...}}
data: {"event": "data", "section": "snowflake", "payload": {...}}
data: {"event": "data", "section": "filing_diff", "payload": {...}}
data: {"event": "data", "section": "insider_cluster", "payload": {...}}
data: {"event": "data", "section": "sentiment", "payload": {...}}
data: {"event": "done"}
```

## OpenAPI Schema

Generated at `shared/openapi.json`. Regenerate with:
```bash
make schema
```
