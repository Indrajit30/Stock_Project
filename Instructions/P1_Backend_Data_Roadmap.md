# Person 1 — Backend, Data Pipeline & Speed Layer
## Claude Code Prompt Roadmap

> Feed each section to Claude Code in order. Complete one before starting the next.
> Your job: own everything the other two people consume. You are the engine.

---

## CONTEXT (paste this at the start of every Claude Code session)

```
We are building an AI stock research web app. I own the backend — FastAPI server, all data
ingestion, caching, database, and the nightly pre-compute pipeline. The stack is:
- Python 3.11+, FastAPI, asyncio, httpx
- defeatbeta-api (pip install defeatbeta-api) — free, no API key, no rate limits
- SEC EDGAR full-text search (free)
- Qdrant for vector search
- Redis for caching
- Arq for async job queues
- PostgreSQL for structured storage
- Anthropic API (claude-haiku-4-5 for subagents, claude-sonnet-4-6 for synthesis)

Two other devs are building the AI agent layer (Person 2) and the React frontend (Person 3).
They will consume my FastAPI endpoints. I must publish OpenAPI schemas so they can mock
against them while I build. All shared data shapes live in shared/schemas.py as Pydantic models.
```

---

## PHASE 1 — Project scaffold & shared contracts (Day 1–2)

### Prompt 1.1 — Monorepo structure
```
Create a monorepo folder structure for our stock research app with these top-level folders:
- backend/          (FastAPI app, this is my domain)
- shared/           (Pydantic schemas shared by all three devs)
- frontend/         (React app, not my concern but needs to exist)
- agent/            (AI agent layer, not my concern)
- infra/            (docker-compose, redis, qdrant configs)

Inside backend/ create:
- main.py           (FastAPI app entry point with CORS for localhost:3000)
- routers/          (one file per feature: stock.py, peers.py, alerts.py, export.py)
- services/         (data_fetcher.py, cache.py, edgar.py, precompute.py)
- models/           (database ORM models)
- requirements.txt

Inside shared/ create schemas.py with these Pydantic v2 models:
  - StockReport: ticker, company_name, verdict (buy/wait/avoid), verdict_confidence (0-1),
    plain_english_summary (str), three_bulls (list[CitedPoint]), three_risks (list[CitedPoint]),
    snowflake_scores (SnowflakeScores), financials (FinancialSnapshot), generated_at (datetime)
  - CitedPoint: text (str), source (str), source_url (str)
  - SnowflakeScores: value (float 0-10), growth (float), health (float),
    momentum (float), smart_money (float)
  - FinancialSnapshot: revenue_ttm, net_income_ttm, gross_margin, pe_ratio,
    ev_ebitda, debt_to_equity, market_cap, sector, industry
  - PeerComparisonRow: ticker, company_name, market_cap, pe_ratio, ev_ebitda,
    gross_margin, revenue_growth_yoy, net_margin, debt_to_equity, snowflake_scores
  - InsiderCluster: ticker, cluster_date, total_value_usd, insider_count,
    insiders (list[InsiderTrade]), signal_strength (float 0-1)
  - InsiderTrade: name, role, shares, value_usd, trade_date, is_10b5_plan (bool)
  - SuperinvestorCluster: ticker, quarter, funds (list[FundEntry]), total_aum_pct (float)
  - FundEntry: fund_name, shares_held, pct_of_fund_aum, change_from_prior
  - FilingDiff: ticker, filing_type, current_period, prior_period,
    changed_sections (list[DiffSection])
  - DiffSection: section_name, additions (list[str]), deletions (list[str]), summary (str)
  - SentimentPulse: ticker, reddit_score (float -1 to 1), reddit_mention_count (int),
    top_posts (list[RedditPost]), updated_at (datetime)
  - RedditPost: title, subreddit, score, url, sentiment (float)

Export all models. Add a VERSION = "1.0.0" constant.
This file is the source of truth for all three developers.
```

### Prompt 1.2 — Docker compose for local dev
```
Create infra/docker-compose.yml that starts:
- Redis 7 on port 6379 with persistence
- Qdrant latest on ports 6333 (HTTP) and 6334 (gRPC) with local volume mount
- PostgreSQL 15 on port 5432 with a database called "stockresearch"

Also create infra/.env.example with placeholders for:
ANTHROPIC_API_KEY=
REDIS_URL=redis://localhost:6379
QDRANT_URL=http://localhost:6333
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/stockresearch
PRECOMPUTE_TICKERS=AAPL,MSFT,GOOGL,AMZN,META,NVDA,TSLA,JPM,JNJ,V,WMT,PG,MA,UNH,HD,BAC,XOM,CVX,LLY,ABBV,PFE,MRK,TMO,AVGO,COST,DIS,NFLX,CRM,AMD,INTC,QCOM,TXN,INTU,AMAT,MU,NOW,ADBE,PANW,SNOW,SQ,PYPL,UBER,LYFT,SHOP,NET,PLTR,COIN,RBLX,HOOD,SOFI

Add a Makefile with: make dev (starts docker compose + uvicorn with hot reload)
```

---

## PHASE 2 — DefeatBeta data layer (Day 2–4)

### Prompt 2.1 — DefeatBeta wrapper service
```
Create backend/services/data_fetcher.py using defeatbeta-api (pip install defeatbeta-api).

DefeatBeta usage:
  from defeatbeta_api.data.ticker import Ticker
  t = Ticker('AAPL')
  t.price()                          # historical prices DataFrame
  t.quarterly_income_statement()     # quarterly income statement
  t.quarterly_balance_sheet()        # balance sheet
  t.quarterly_cash_flow()            # cash flow
  t.ttm_metrics()                    # trailing twelve month metrics
  t.earnings_call_transcript()       # earnings call transcripts
  t.news()                           # recent news

Build an async DataFetcher class with these methods (wrap sync defeatbeta calls in
asyncio.get_event_loop().run_in_executor(None, ...) for non-blocking execution):

  async def get_financials(ticker: str) -> FinancialSnapshot
    - Pull quarterly_income_statement, balance_sheet, ttm_metrics
    - Compute gross_margin, pe_ratio, ev_ebitda, debt_to_equity from raw data
    - Return FinancialSnapshot (from shared/schemas.py)

  async def get_price_history(ticker: str, days: int = 365) -> list[dict]
    - Return last N days of OHLCV data

  async def get_earnings_transcript(ticker: str) -> str
    - Return the most recent earnings call transcript as plain text

  async def get_news(ticker: str, limit: int = 10) -> list[dict]
    - Return recent news items with title, url, summary, published_at

  async def get_peer_tickers(ticker: str) -> list[str]
    - Use t.ttm_metrics() to get sector/industry
    - Query all tickers in PRECOMPUTE_TICKERS env var that share same sector
    - Return list of peer tickers (max 8)

  async def get_batch_financials(tickers: list[str]) -> dict[str, FinancialSnapshot]
    - Fan out get_financials for all tickers concurrently using asyncio.gather
    - return_exceptions=True for graceful partial failure

Include retry logic (3 attempts, exponential backoff) and structured logging.
```

### Prompt 2.2 — EDGAR integration
```
Create backend/services/edgar.py for free SEC EDGAR data.

Implement these async functions using httpx.AsyncClient:

1. get_recent_filings(ticker: str, form_types: list = ['10-K','10-Q','8-K']) -> list[dict]
   - Hit https://efts.sec.gov/LATEST/search-index?q="{ticker}"&dateRange=custom&startdt=2023-01-01&forms={form}
   - Return list with: accession_number, form_type, filed_date, document_url

2. get_filing_text(accession_url: str) -> str
   - Fetch full text of a filing from SEC EDGAR
   - Strip HTML tags, return clean text (max 100K chars)

3. get_insider_trades(ticker: str, days_back: int = 90) -> list[InsiderTrade]
   - Hit https://efts.sec.gov/LATEST/search-index?q="{ticker}"&forms=4&dateRange=custom
   - Parse Form 4 XML: owner name, role, shares, value, date, is_10b5_plan flag
   - Return list of InsiderTrade objects (from shared/schemas.py)

4. detect_insider_cluster(ticker: str) -> InsiderCluster | None
   - Call get_insider_trades(ticker, days_back=30)
   - A cluster = 3+ unique insiders, total value $100K+, all within 30 days
   - Weight CEO buys at 3x, CFO at 2x, Director at 1x (signal_strength)
   - Exclude rows where is_10b5_plan = True
   - Return InsiderCluster or None if no cluster

5. get_congressional_trades(ticker: str) -> list[dict]
   - Hit https://efts.sec.gov/LATEST/search-index with STOCK Act disclosures
   - Alternatively scrape https://www.capitoltrades.com/trades?ticker={ticker} (free, public)
   - Return list with: politician_name, chamber, party, transaction_type, amount_range, trade_date

6. get_recent_8k_items(ticker: str) -> list[dict]
   - Fetch recent 8-Ks and classify by Item number
   - Flag item 4.02 (non-reliance/restatement) and 5.02 (officer departure) as HIGH_ALERT
   - Return list with: filed_date, item_numbers, descriptions, alert_level

7. compute_filing_diff(ticker: str, form_type: str = '10-Q') -> FilingDiff
   - Get the two most recent filings of form_type
   - For each major section (MD&A, Risk Factors, Financial Statements):
     - Use difflib.unified_diff on the text
     - Extract additions (lines starting with +) and deletions (lines starting with -)
     - Cap at 20 additions/deletions per section
   - Return FilingDiff object

Use rate limiting: max 10 req/sec to EDGAR (they ask for this). Add User-Agent header:
"StockResearchApp research@example.com" (EDGAR requires a descriptive user agent).
```

### Prompt 2.3 — Reddit sentiment
```
Create backend/services/sentiment.py for social sentiment.

Use ONLY free sources — no paid APIs:

1. Reddit via official API (no auth needed for public search):
   async def get_reddit_sentiment(ticker: str) -> SentimentPulse
   - Query https://www.reddit.com/search.json?q={ticker}&sort=hot&limit=25&t=week
   - Also query r/wallstreetbets, r/stocks, r/investing subreddits specifically
   - For each post title + selftext, compute sentiment using:
     pip install vaderSentiment
     from vaderSentiment.sentiment import SentimentIntensityAnalyzer
   - Average compound scores weighted by post score (upvotes)
   - Return SentimentPulse with reddit_score (-1 to 1), mention count, top 5 posts

2. ApeWisdom (free API, no key needed):
   async def get_apewisdom_rank(ticker: str) -> dict
   - Hit https://apewisdom.io/api/v1.0/filter/all-stocks/
   - Find ticker in results, return rank, mention_count, upvotes_24h

Combine both into get_full_sentiment(ticker: str) -> SentimentPulse
Cache results for 30 minutes (sentiment changes fast but not per-second).
```

---

## PHASE 3 — Caching & Speed layer (Day 4–6)

### Prompt 3.1 — Redis multi-tier cache
```
Create backend/services/cache.py — this is the most important speed component.

Build a CacheManager class backed by Redis (aioredis):

CACHE TTL STRATEGY (implement exactly):
  - intraday prices:     5 minutes
  - news:               15 minutes
  - sentiment:          30 minutes
  - financials (TTM):   6 hours
  - earnings transcript: 24 hours
  - SEC filings text:   PERMANENT (filings never change — use TTL of 30 days)
  - filing diffs:       PERMANENT (same reason)
  - insider trades:     1 hour
  - pre-computed report: 12 hours (nightly batch refreshes anyway)
  - peer list:          24 hours

Methods:
  async def get(key: str) -> Any | None
  async def set(key: str, value: Any, ttl_seconds: int)
  async def get_or_fetch(key: str, fetch_fn: Callable, ttl_seconds: int) -> Any
    - This is the primary interface: check cache, call fetch_fn if miss, store result

Key naming convention: "{entity}:{ticker}:{data_type}:{extra}"
  Examples: "stock:AAPL:financials", "stock:AAPL:transcript:2024Q3", "peers:AAPL:list"

Also build a decorator:
  @cached(ttl=CacheTTL.FINANCIALS)
  async def get_financials(ticker: str) -> FinancialSnapshot

Serialize with orjson (faster than stdlib json). Handle cache stampede with a 30-second lock
(use Redis SET NX) so parallel requests don't all re-fetch on cache miss.

Log cache hits vs misses per key prefix for monitoring.
```

### Prompt 3.2 — Qdrant vector store setup
```
Create backend/services/vector_store.py for semantic search over SEC filings.

Use qdrant-client (pip install qdrant-client).

COLLECTION SETUP:
  Collection name: "sec_filings"
  Vector size: 1536 (text-embedding-3-small from OpenAI, cheapest + fast)
  Distance: Cosine
  
  Payload fields to index for filtering (use Qdrant payload indexes):
    - ticker: keyword
    - form_type: keyword  (10-K, 10-Q, 8-K)
    - fiscal_period: keyword  (2024Q3, 2024Q4, etc.)
    - section: keyword  (MD&A, RiskFactors, FinancialStatements, etc.)
    - filed_date: datetime

Build VectorStore class with:

  async def upsert_filing_chunks(ticker: str, form_type: str, period: str, chunks: list[dict])
    - Each chunk: {"text": str, "section": str, "chunk_id": str}
    - Embed using text-embedding-3-small (batch up to 100 at a time)
    - Prepend contextual header to each chunk before embedding:
      "This chunk is from {ticker} {form_type} {period}, section: {section}. Content: {text}"
      (this is Anthropic's contextual retrieval technique — critical for accuracy)
    - Upsert to Qdrant with full payload

  async def hybrid_search(ticker: str, query: str, top_k: int = 8,
                           form_type: str = None, section: str = None) -> list[dict]
    - Run BM25 keyword search (use rank_bm25 library on in-memory corpus for the ticker)
    - Run Qdrant dense search with payload filters (ticker=ticker, form_type if provided)
    - Merge results: RRF (Reciprocal Rank Fusion) with k=60
    - Return top_k merged results with text, source, score

  async def delete_ticker_chunks(ticker: str)
    - Delete all vectors for a ticker (for refresh)

Note: BM25 beats dense-only on financial docs because tickers, line-item names, and fiscal
periods are highly lexical. The hybrid approach gives recall@5 of 0.82 vs 0.59 dense-only.
```

### Prompt 3.3 — Nightly pre-compute pipeline
```
Create backend/services/precompute.py — the single biggest speed win.

This nightly job pre-builds everything for the top N tickers so on-demand requests
just "hydrate cache + refresh news" instead of computing from scratch.

TICKER LIST: Read from PRECOMPUTE_TICKERS env var (default: top 50 from .env.example)

Build PrecomputeService class:

  async def run_full_pipeline(ticker: str) -> dict
    "Run all pre-compute steps for one ticker. Returns summary of what was built."
    Steps (run concurrently where possible):
    1. Fetch & cache financials (DataFetcher.get_financials)
    2. Fetch & cache earnings transcript (DataFetcher.get_earnings_transcript)
    3. Fetch & embed latest 10-K and 10-Q into Qdrant (VectorStore.upsert_filing_chunks)
    4. Compute & cache filing diff (EdgarService.compute_filing_diff)
    5. Detect & cache insider cluster (EdgarService.detect_insider_cluster)
    6. Fetch & cache congressional trades (EdgarService.get_congressional_trades)
    7. Compute & cache Snowflake scores (compute_snowflake_scores)
    8. Fetch sentiment (SentimentService.get_full_sentiment)
    
    Build a draft StockReport (without AI synthesis) and cache with 12hr TTL.
    The AI synthesis step runs on-demand in 2–5 seconds on top of this cached draft.

  async def run_all_tickers()
    "Fan out run_full_pipeline for all tickers with max 5 concurrent jobs"
    Use asyncio.Semaphore(5) to avoid hammering EDGAR.
    Log progress: "Precomputed {ticker} in {elapsed}s"

  def compute_snowflake_scores(financials: FinancialSnapshot, 
                                price_history: list, 
                                insider_cluster: InsiderCluster | None,
                                superinvestor: SuperinvestorCluster | None) -> SnowflakeScores
    Score each axis 0–10:
    - Value: (1/PE ratio normalized) + (EV/EBITDA inverse) + (Price/Book inverse) → normalize to 0-10
    - Growth: revenue_growth_yoy * 0.6 + earnings_growth * 0.4 → normalize to 0-10
    - Health: (1 - debt_to_equity) * 0.5 + current_ratio * 0.3 + interest_coverage * 0.2 → 0-10
    - Momentum: price_vs_52w_high * 0.4 + price_vs_200ma * 0.3 + revenue_surprise * 0.3 → 0-10
    - Smart Money: insider_cluster_signal * 0.5 + superinvestor_score * 0.5 → 0-10
    Clamp all scores to [0, 10].

Set up Arq worker (pip install arq):
  Create backend/worker.py with:
  - Schedule run_all_tickers() daily at 2 AM UTC
  - Also expose run_full_pipeline as an on-demand job (triggered when a new ticker is searched)

  class WorkerSettings:
    functions = [run_full_pipeline_job, run_all_tickers_job]
    cron_jobs = [cron(run_all_tickers_job, hour=2, minute=0)]
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL"))
```

---

## PHASE 4 — FastAPI routes (Day 6–8)

### Prompt 4.1 — Core stock routes
```
Create backend/routers/stock.py — these are the endpoints Person 3 (frontend) will call.

All responses use shared/schemas.py Pydantic models. Use JSONResponse with orjson.

Implement with FastAPI, all async:

GET /api/stock/{ticker}/report
  - Check Redis cache for pre-computed StockReport
  - If cache hit: return immediately (this is the ~2 second path)
  - If cache miss: trigger run_full_pipeline as background task, return 202 with job_id
  - Query param: ?force_refresh=true to bypass cache

GET /api/stock/{ticker}/report/stream
  - SSE (Server-Sent Events) endpoint using FastAPI's StreamingResponse
  - Event protocol (Person 2 will fill in AI synthesis, you emit the cached data):
    data: {"event": "section_start", "section": "overview"}
    data: {"event": "data", "section": "financials", "payload": {...}}
    data: {"event": "data", "section": "snowflake", "payload": {...}}
    data: {"event": "data", "section": "filing_diff", "payload": {...}}
    data: {"event": "data", "section": "insider_cluster", "payload": {...}}
    data: {"event": "data", "section": "sentiment", "payload": {...}}
    data: {"event": "done"}
  - Set headers: Content-Type: text/event-stream, X-Accel-Buffering: no, Cache-Control: no-cache

GET /api/stock/{ticker}/filing-diff
  - Return FilingDiff from cache or compute on demand

GET /api/stock/{ticker}/insider-cluster
  - Return InsiderCluster or null

GET /api/stock/{ticker}/congressional-trades
  - Return list of congressional trades

GET /api/stock/{ticker}/sentiment
  - Return SentimentPulse

GET /api/stock/{ticker}/snowflake
  - Return SnowflakeScores

GET /api/stock/{ticker}/price-history?days=365
  - Return price history array

GET /api/jobs/{job_id}/status
  - Poll job status for cache-miss scenario
```

### Prompt 4.2 — Peer comparison routes
```
Create backend/routers/peers.py — powers the Peer Comparison tab on the frontend.

GET /api/peers/{ticker}
  - Get peer tickers from DataFetcher.get_peer_tickers(ticker)
    (same sector + similar market cap ±50% from PRECOMPUTE_TICKERS list)
  - Fan out get_financials for all peers concurrently
  - Also fetch snowflake_scores for each
  - Return list[PeerComparisonRow] sorted by market_cap desc

GET /api/peers/{ticker}/compare?metrics=pe_ratio,ev_ebitda,gross_margin
  - Return structured comparison table
  - metrics param filters which columns to include
  - Always include: ticker, company_name, market_cap as fixed columns
  - Response: { "subject": PeerComparisonRow, "peers": list[PeerComparisonRow] }

GET /api/peers/{ticker}/superinvestor-cluster
  - Parse EDGAR 13F filings for the ticker and top 100 known fund names
  - Detect if 3+ funds entered same position in same quarter
  - Return SuperinvestorCluster or null
  - Cache for 24 hours (13F data is quarterly, not real-time)

Note: For market cap similarity, use ±50% band:
  if subject market cap is $500B, peers must be $250B–$750B AND same sector.
```

### Prompt 4.3 — Export routes
```
Create backend/routers/export.py — powers the download buttons.

GET /api/stock/{ticker}/export/pdf
  - Fetch cached StockReport for ticker
  - Generate a 1-page PDF using reportlab (pip install reportlab):
    Layout (single A4 page):
    - Header: Company name + ticker + date + "Generated by StockResearch AI"
    - Verdict box: big BUY/WAIT/AVOID badge with confidence %
    - Plain English summary (2-3 sentences)
    - Two columns:
      Left: 3 bull points (each with source citation)
      Right: 3 risk points (each with source citation)  
    - Snowflake scores as a simple bar chart (use reportlab Drawing)
    - Key financials table: Revenue TTM, Net Income, PE, EV/EBITDA, Gross Margin, Debt/Equity
    - Footer: "Data sourced from SEC EDGAR, DefeatBeta API. Not financial advice."
  - Return as application/pdf with Content-Disposition: attachment; filename="{ticker}_report.pdf"

GET /api/stock/{ticker}/export/excel
  - Generate Excel workbook with openpyxl (pip install openpyxl):
    Sheet 1 "Summary": StockReport fields in a formatted table
    Sheet 2 "Financials": Quarterly income statement (last 8 quarters from DefeatBeta)
    Sheet 3 "Peer Comparison": PeerComparisonRow table for all peers
    Sheet 4 "Filing Diff": Changed sections from latest 10-Q diff
    Sheet 5 "Insider Trades": InsiderTrade list for last 90 days
    Sheet 6 "Congressional Trades": Congressional trades list
  - Apply basic formatting: bold headers, alternating row colors, auto-width columns
  - Return as application/vnd.openxmlformats-officedocument.spreadsheetml.sheet

GET /api/stock/{ticker}/export/pptx (stretch goal — implement last)
  - Generate a 5-slide PowerPoint using python-pptx:
    Slide 1: Title + verdict + company overview
    Slide 2: Snowflake visual (as image rendered from matplotlib)
    Slide 3: Bull case — 3 points with citations
    Slide 4: Bear case — 3 risks with citations  
    Slide 5: Key financials table + peer comparison
```

---

## PHASE 5 — Integration & handoff (Day 8–10)

### Prompt 5.1 — OpenAPI export & mock server
```
Now that all routes exist, do the following:

1. Run the FastAPI app and export the OpenAPI schema:
   python -c "import json; from backend.main import app; print(json.dumps(app.openapi()))" > shared/openapi.json

2. Create shared/mock_data.py with realistic mock responses for every schema in shared/schemas.py.
   Use AAPL as the example ticker. Make the mock data realistic (real-ish P/E ratios, market caps, etc.)

3. Create a simple mock server script shared/mock_server.py that:
   - Reads shared/openapi.json
   - Serves mock responses for every endpoint using the mock data
   - Runs on port 8001 (real backend runs on 8000)
   - This lets Person 3 (frontend) build against realistic data while you finish the real backend

4. Write shared/README.md explaining:
   - How to run the mock server: python shared/mock_server.py
   - How to switch frontend from mock (port 8001) to real (port 8000): change VITE_API_URL env var
   - List of all endpoints with example responses
```

### Prompt 5.2 — Tests & health checks
```
Add backend/tests/ with pytest tests for the most critical paths:

1. test_data_fetcher.py — test get_financials("AAPL") returns valid FinancialSnapshot
2. test_cache.py — test cache set/get/TTL expiry works correctly
3. test_edgar.py — test get_insider_trades("AAPL") parses at least one trade
4. test_precompute.py — test run_full_pipeline("AAPL") completes without exceptions
5. test_routes.py — test all FastAPI endpoints return 200 with valid schema

Add GET /api/health endpoint that returns:
{
  "status": "ok",
  "redis": "connected" | "error",
  "qdrant": "connected" | "error", 
  "precompute_cache_coverage": "42/50 tickers cached",
  "last_nightly_run": "2025-05-01T02:00:00Z"
}

Add GET /api/cache/stats for debugging:
{
  "hit_rate": 0.87,
  "total_keys": 412,
  "by_prefix": {"stock:financials": 50, "stock:transcript": 48, ...}
}
```

---

## MERGE CHECKLIST (before combining with Person 2 & 3)

```
Before pushing to the shared branch, verify:

[ ] python shared/mock_server.py starts on port 8001 with no errors
[ ] GET /api/health returns 200 with all services "connected"
[ ] GET /api/stock/AAPL/report returns a valid StockReport JSON
[ ] GET /api/stock/AAPL/report/stream emits at least 3 SSE events then "done"
[ ] GET /api/peers/AAPL returns at least 3 PeerComparisonRow items
[ ] GET /api/stock/AAPL/export/pdf returns a downloadable PDF file
[ ] GET /api/stock/AAPL/export/excel returns a downloadable .xlsx file
[ ] Redis cache hit rate > 80% on second request for same ticker
[ ] Nightly precompute job runs for all 50 tickers in < 10 minutes total
[ ] shared/schemas.py imported successfully by both backend/ and agent/ (no circular imports)
[ ] All Pydantic models in shared/schemas.py have working .model_json_schema()

Tell Person 2: "Backend is ready. Import from shared.schemas. Real API on port 8000, mock on 8001."
Tell Person 3: "Mock server running on 8001. OpenAPI spec at shared/openapi.json. Switch to 8000 when ready."
```
