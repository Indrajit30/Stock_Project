# Person 2 — AI Agent Layer, NLP & Synthesis Engine
## Claude Code Prompt Roadmap

> Feed each section to Claude Code in order. Complete one before starting the next.
> Your job: turn raw cached data into cited, honest, synthesized intelligence.

---

## CONTEXT (paste this at the start of every Claude Code session)

```
We are building an AI stock research web app. I own the AI agent layer — the orchestrator
that takes pre-fetched data from the backend (Person 1) and synthesizes it into cited reports,
verdicts, and signals using LLMs.

Stack:
- Python 3.11+, asyncio
- Anthropic API: claude-haiku-4-5 for parallel subagents, claude-sonnet-4-6 for final synthesis
- anthropic SDK with prompt caching (cache_control: ephemeral)
- LiteLLM for model routing with fallbacks
- FinBERT for earnings call NLP (pip install transformers torch)
- vaderSentiment for quick sentiment scoring
- rank_bm25 for keyword search
- shared/schemas.py (Pydantic models shared by all 3 devs — DO NOT modify)

Person 1 (backend) exposes data via FastAPI on port 8000. I call internal service functions
directly (not HTTP) since agent/ is co-located with backend/ in the monorepo.

Person 3 (frontend) calls POST /api/agent/synthesize and GET /api/stock/{ticker}/report/stream.
I must emit SSE events in the exact protocol Person 3 expects.

CRITICAL RULES I must follow for trust:
- Every factual claim must include source + source_url from the actual filing or transcript
- If data is missing, return "Data not available" — NEVER fabricate
- Restrict numerical claims to SEC filings and DefeatBeta data ONLY — never open web
- Show intermediate reasoning steps (for the "visible agent reasoning" feature)
```

---

## PHASE 1 — Agent scaffold & LLM routing (Day 1–2)

### Prompt 1.1 — LiteLLM router setup
```
Create agent/llm_router.py — the model routing layer.

Install: pip install litellm anthropic

Build an LLMRouter class:

MODEL TIERS (implement exactly):
  FAST_MODEL = "claude-haiku-4-5"       # subagents: 150-240 tok/s, cheap
  SMART_MODEL = "claude-sonnet-4-6"     # synthesis: best quality
  
  Fallback chain per tier:
  FAST: claude-haiku-4-5 → claude-haiku-4-5-20251001 (version fallback)
  SMART: claude-sonnet-4-6 → claude-haiku-4-5 (degrade gracefully if quota hit)

Methods:
  async def complete_fast(prompt: str, system: str = None, max_tokens: int = 1000) -> str
    - Use FAST_MODEL via anthropic SDK directly (not litellm — direct SDK is faster)
    - Log latency and tokens used

  async def complete_smart(messages: list, system: str, max_tokens: int = 4000,
                            cached_prefix: str = None) -> str
    - Use SMART_MODEL
    - If cached_prefix is provided, structure the API call with Anthropic prompt caching:
      messages=[
        {"role": "user", "content": [
          {"type": "text", "text": cached_prefix,
           "cache_control": {"type": "ephemeral"}},   ← cache the filing text
          {"type": "text", "text": dynamic_query}
        ]}
      ]
    - This gives 85% TTFT reduction and 10% input cost on cache hits

  async def complete_parallel(prompts: list[dict]) -> list[str]
    - Fan out multiple FAST_MODEL calls concurrently with asyncio.gather
    - Each dict: {"prompt": str, "system": str, "max_tokens": int}
    - return_exceptions=True, replace exceptions with error strings
    - Log how many completed vs failed

Add token counting and cost estimation logging per call.
```

### Prompt 1.2 — Citation enforcement layer
```
Create agent/citation_guard.py — the most important trust component.

Build a CitationGuard class that post-processes every LLM response:

  def extract_citations(text: str) -> list[dict]
    - Find all patterns like [Source: AAPL 10-Q Q3 2024, MD&A Section]
      or <cite>...</cite> tags
    - Return list of {"claim": str, "source": str, "source_url": str | None}

  def validate_citations(claims: list[dict], allowed_sources: list[str]) -> list[dict]
    - allowed_sources = list of source identifiers from the actual data fetched
      (e.g. ["AAPL 10-Q 2024Q3", "AAPL 10-K 2023", "DefeatBeta TTM Metrics"])
    - For each claim, check if its source is in allowed_sources
    - Flag as UNVERIFIED if source not in allowed list
    - Return claims with verification_status added

  def strip_unverified_claims(text: str, verified_sources: list[str]) -> str
    - Remove any sentence that contains a number/percentage but no inline citation
    - Replace with: "[Data not available from verified sources]"

  def build_citation_prompt(data_context: str, allowed_sources: list[str]) -> str
    - Returns a system prompt fragment that instructs the LLM to:
      1. Cite every numerical claim with [Source: exact_source_name]
      2. Write "Data not available" if the answer isn't in the provided context
      3. Never use information not present in the provided documents
      4. List sources used at the end of the response

Build SYSTEM_PROMPT_BASE constant:
  "You are a financial research analyst. You ONLY use information from the provided
   documents. Every numerical claim must be cited with [Source: document_name].
   If data is not in the provided documents, write 'Data not available' — never
   guess or use prior knowledge for financial figures. You are honest and precise."
```

---

## PHASE 2 — Parallel section analysis (Day 2–4)

### Prompt 2.1 — Orchestrator-worker architecture
```
Create agent/orchestrator.py — the core of the agent system.

This implements the Anthropic orchestrator-worker pattern:
one orchestrator spawns parallel subagents, each analyzing one section of the filing,
then the orchestrator synthesizes all results into the final report.

Build StockReportOrchestrator class:

  async def generate_report(ticker: str, cached_data: dict) -> StockReport
    """
    cached_data comes from Person 1's backend cache and contains:
    {
      "financials": FinancialSnapshot,
      "transcript": str (earnings call text),
      "filing_10q_text": str (latest 10-Q full text),
      "filing_diff": FilingDiff,
      "news": list[dict],
      "insider_cluster": InsiderCluster | None,
      "snowflake_scores": SnowflakeScores,
      "sentiment": SentimentPulse,
      "congressional_trades": list[dict]
    }
    """
    
    STEP 1 — Build the stable cached prefix (file text that never changes):
      filing_cache_prefix = f"""
      === AAPL 10-Q Q3 2024 FILING TEXT ===
      {cached_data['filing_10q_text'][:40000]}
      
      === EARNINGS CALL TRANSCRIPT (Most Recent) ===
      {cached_data['transcript'][:20000]}
      """
      (This entire block gets cached by Anthropic — subsequent calls are 10% cost + 85% faster)
    
    STEP 2 — Fan out 5 parallel subagent calls (all FAST_MODEL, 30s timeout each):
      tasks = [
        analyze_financials(ticker, cached_data['financials'], filing_cache_prefix),
        analyze_risks(ticker, cached_data['filing_10q_text'], filing_cache_prefix),
        analyze_growth(ticker, cached_data['financials'], cached_data['transcript']),
        analyze_sentiment_and_news(ticker, cached_data['news'], cached_data['sentiment']),
        analyze_mgmt_tone(ticker, cached_data['transcript'])
      ]
      results = await asyncio.gather(*tasks, return_exceptions=True)
      
    STEP 3 — Synthesize with SMART_MODEL:
      synthesis = await synthesize_all_sections(ticker, results, cached_data)
    
    STEP 4 — Run CitationGuard post-pass:
      verified = citation_guard.validate_citations(synthesis.claims, allowed_sources)
    
    STEP 5 — Build final StockReport from synthesis
    Return StockReport

  async def analyze_financials(ticker, financials, cache_prefix) -> dict
    prompt = f"""
    Analyze these financial metrics for {ticker}:
    PE Ratio: {financials.pe_ratio}
    EV/EBITDA: {financials.ev_ebitda}
    Gross Margin: {financials.gross_margin}
    Revenue TTM: {financials.revenue_ttm}
    Debt/Equity: {financials.debt_to_equity}
    
    From the filing text above, find specific commentary on:
    1. Revenue trends and guidance
    2. Margin expansion or compression  
    3. Any one-time items affecting results
    
    Cite every claim with [Source: {ticker} 10-Q section name].
    Format: JSON with keys: summary, key_metrics, trends, citations
    """
    return await llm_router.complete_fast(prompt, system=SYSTEM_PROMPT_BASE, cached_prefix=cache_prefix)

  async def analyze_risks(ticker, filing_text, cache_prefix) -> dict
    (Similar structure — extract top 3 risks from Risk Factors section with citations)

  async def analyze_growth(ticker, financials, transcript) -> dict
    (Revenue growth, new products/markets mentioned, guidance commentary)

  async def analyze_sentiment_and_news(ticker, news, sentiment) -> dict
    (Summarize sentiment + top 3 relevant news items)

  async def analyze_mgmt_tone(ticker, transcript) -> dict
    (Delegate to HedgingDetector — see Prompt 2.2)

  async def synthesize_all_sections(ticker, section_results, all_data) -> StockReport
    combined_context = merge all section_results into structured text
    
    synthesis_prompt = f"""
    Based on this comprehensive analysis of {ticker}:
    
    {combined_context}
    
    Produce a final investment verdict in this exact JSON structure:
    {{
      "verdict": "buy" | "wait" | "avoid",
      "verdict_confidence": 0.0–1.0,
      "plain_english_summary": "2-3 sentence plain English summary suitable for a retail investor",
      "three_bulls": [
        {{"text": "...", "source": "...", "source_url": "..."}},
        ...
      ],
      "three_risks": [...same structure...]
    }}
    
    Rules:
    - verdict confidence > 0.8 only if multiple data points agree
    - every bull/risk point MUST have a source from the analysis above
    - plain_english_summary must be jargon-free (no "EBITDA", no "YoY")
    """
    response = await llm_router.complete_smart(synthesis_prompt, system=SYSTEM_PROMPT_BASE)
    return parse_and_validate_report(response, ticker, all_data)
```

### Prompt 2.2 — Earnings call hedging detector
```
Create agent/hedging_detector.py — one of the unique differentiating features.

Install: pip install transformers torch  (for FinBERT)
Install: pip install vaderSentiment

Build HedgingDetector class:

  HEDGING_WORDS = [
    "uncertain", "challenging", "headwinds", "volatile", "may", "might", "could",
    "potentially", "subject to", "risk", "difficult", "macro", "environment",
    "I'll have to get back to you", "we'll see", "too early to say", "monitor",
    "cautious", "careful", "we hope", "we expect to", "pending"
  ]
  
  DEFLECTION_PHRASES = [
    "I'll have to get back to you",
    "we'll follow up on that",  
    "that's something we're still evaluating",
    "I don't want to get ahead of ourselves",
    "we'll provide more color later"
  ]

  def parse_transcript_sections(transcript_text: str) -> dict
    - Split transcript into: "prepared_remarks" and "qa_section"
    - In QA: further split by speaker (use regex for "Analyst:" / "CEO:" / "CFO:" patterns)
    - Return {"prepared": str, "qa": str, "ceo_text": str, "cfo_text": str, "analyst_questions": list[str]}

  def compute_hedging_score(text: str) -> float
    - Count hedging word occurrences per 1000 words
    - Count deflection phrases
    - Return normalized score 0.0 (no hedging) to 1.0 (extreme hedging)

  def compute_deflection_count(qa_text: str) -> int
    - Count how many analyst questions received deflection phrases in response
    - Return integer count

  def compare_to_prior_quarters(current_score: float, historical_scores: list[float]) -> dict
    - Compute z-score vs historical: (current - mean) / std
    - If z_score > 1.5: "significantly more hedging than usual"
    - If z_score < -1.5: "significantly less hedging than usual"  
    - Return {"z_score": float, "trend": "increasing"|"stable"|"decreasing", "interpretation": str}

  async def analyze_transcript(ticker: str, transcript: str,
                                historical_transcripts: list[str] = None) -> dict
    sections = parse_transcript_sections(transcript)
    
    current_hedging = compute_hedging_score(transcript)
    ceo_hedging = compute_hedging_score(sections['ceo_text'])
    cfo_hedging = compute_hedging_score(sections['cfo_text'])
    deflections = compute_deflection_count(sections['qa'])
    
    # Use FinBERT for sentiment (more accurate than VADER for financial text)
    from transformers import pipeline
    finbert = pipeline("text-classification", model="ProsusAI/finbert")
    prepared_sentiment = finbert(sections['prepared'][:512])[0]
    qa_sentiment = finbert(sections['qa'][:512])[0]
    
    trend = {}
    if historical_transcripts:
      hist_scores = [compute_hedging_score(t) for t in historical_transcripts[-4:]]
      trend = compare_to_prior_quarters(current_hedging, hist_scores)
    
    # Get LLM interpretation
    interp_prompt = f"""
    Earnings call hedging analysis for {ticker}:
    - Hedging score: {current_hedging:.2f}/1.0 (higher = more hedging)
    - CEO hedging: {ceo_hedging:.2f}, CFO hedging: {cfo_hedging:.2f}
    - Analyst questions deflected: {deflections}
    - Prepared remarks sentiment: {prepared_sentiment}
    - Q&A sentiment: {qa_sentiment}
    - Trend vs prior 4 quarters: {trend}
    
    In 2-3 sentences, interpret what this means for investors. Be specific about
    what management seems reluctant to discuss directly.
    """
    interpretation = await llm_router.complete_fast(interp_prompt)
    
    return {
      "hedging_score": current_hedging,
      "ceo_hedging": ceo_hedging,
      "cfo_hedging": cfo_hedging,
      "deflection_count": deflections,
      "prepared_vs_qa_divergence": abs(float(prepared_sentiment['score']) - float(qa_sentiment['score'])),
      "trend": trend,
      "interpretation": interpretation
    }
```

### Prompt 2.3 — Superinvestor 13F detector
```
Create agent/superinvestor_detector.py — the 13F cluster detection feature.

Build SuperinvestorDetector class:

KNOWN_FUNDS (dict mapping fund name → CIK number for EDGAR):
  {
    "Berkshire Hathaway": "0001067983",
    "Bridgewater Associates": "0001350694",  
    "Renaissance Technologies": "0001037389",
    "Two Sigma": "0001179392",
    "Citadel": "0001423298",
    "Point72": "0001352576",
    "Viking Global": "0001011116",
    "Coatue Management": "0001336528",
    "Tiger Global": "0001359486",
    "Lone Pine Capital": "0001061768",
    "Pershing Square": "0001336528",
    "Baupost Group": "0001061165",
    "Appaloosa Management": "0001102610",
    "Greenlight Capital": "0001079114",
    "Duquesne Family Office": "0001536411"
  }

  async def fetch_13f_holdings(cik: str, quarter: str) -> list[dict]
    - Hit EDGAR API: https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json
    - Find 13F-HR filings for the given quarter
    - Parse the holdings from the XML accession
    - Return list of {"ticker": str, "shares": int, "value_usd": int, "change_from_prior": int}

  async def detect_cluster(ticker: str, quarter: str = None) -> SuperinvestorCluster | None
    - Default quarter = most recent completed quarter
    - Fan out fetch_13f_holdings for all 15 funds concurrently
    - Find funds that hold {ticker}
    - A cluster = 3+ funds BOTH holding the stock AND increased position this quarter
    - For each fund in cluster, compute pct_of_fund_aum = value_usd / total_fund_aum * 100
    - Signal is stronger when multiple high-conviction funds (>2% of AUM) are in
    - Return SuperinvestorCluster or None
    - Cache result for 24 hours (13F data is quarterly)

  def score_conviction(fund_entries: list[FundEntry]) -> float
    - Weighted average: (pct_of_fund_aum * new_position_bonus)
    - new_position_bonus = 2.0 if fund_entry.change_from_prior > 0 (new/increased)
    - Normalize to 0–10 for Smart Money snowflake score
    - Return float

Note: If EDGAR API returns 429, back off 5 seconds and retry. EDGAR is free but
rate-limited. Log a warning and return None rather than crashing.
```

---

## PHASE 3 — SSE streaming agent API (Day 4–6)

### Prompt 3.1 — Streaming synthesis endpoint
```
Create agent/stream_agent.py — the SSE streaming orchestrator that Person 3 consumes.

This is the critical path for perceived speed. The user sees content in 2 seconds
even though full synthesis takes 15-30 seconds.

Build StreamingAgent class:

  async def stream_report(ticker: str, cached_data: dict) -> AsyncGenerator[str, None]
    """
    Yields SSE-formatted strings. Person 3's frontend listens to this stream.
    
    SSE format: "data: {json}\\n\\n"
    """
    
    # IMMEDIATELY yield cached/pre-computed sections (< 100ms each)
    yield sse_event("section_start", {"section": "overview", "ticker": ticker})
    
    # Yield financials from cache — zero LLM needed
    yield sse_event("data", {
      "section": "financials",
      "payload": cached_data["financials"].model_dump(),
      "source": "DefeatBeta API"
    })
    
    # Yield snowflake scores from cache
    yield sse_event("data", {
      "section": "snowflake", 
      "payload": cached_data["snowflake_scores"].model_dump()
    })
    
    # Yield sentiment from cache
    yield sse_event("data", {
      "section": "sentiment",
      "payload": cached_data["sentiment"].model_dump()
    })
    
    # Yield filing diff from cache
    if cached_data.get("filing_diff"):
      yield sse_event("data", {
        "section": "filing_diff",
        "payload": cached_data["filing_diff"].model_dump()
      })
    
    # Yield insider cluster from cache
    if cached_data.get("insider_cluster"):
      yield sse_event("data", {
        "section": "insider_cluster",
        "payload": cached_data["insider_cluster"].model_dump()
      })
    
    # Yield congressional trades
    if cached_data.get("congressional_trades"):
      yield sse_event("data", {
        "section": "congressional_trades",
        "payload": cached_data["congressional_trades"]
      })
    
    # NOW start LLM synthesis (this is where the 15-30s is spent)
    yield sse_event("section_start", {"section": "ai_synthesis", "status": "generating"})
    
    # Parallel subagent analysis
    orchestrator = StockReportOrchestrator()
    
    # Stream reasoning steps as they complete
    async for step in orchestrator.stream_reasoning_steps(ticker, cached_data):
      yield sse_event("reasoning_step", {"step": step})  # shows agent thinking to user
    
    # Final synthesis
    report = await orchestrator.generate_report(ticker, cached_data)
    
    yield sse_event("data", {
      "section": "verdict",
      "payload": {
        "verdict": report.verdict,
        "confidence": report.verdict_confidence,
        "summary": report.plain_english_summary,
        "bulls": [b.model_dump() for b in report.three_bulls],
        "risks": [r.model_dump() for r in report.three_risks]
      }
    })
    
    yield sse_event("done", {"ticker": ticker, "generated_at": datetime.utcnow().isoformat()})

  def sse_event(event_type: str, data: dict) -> str
    return f"data: {json.dumps({'event': event_type, **data})}\\n\\n"

Create agent/router.py — FastAPI router that Person 1 will mount:

  @router.get("/api/stock/{ticker}/report/stream")
  async def stream_stock_report(ticker: str, request: Request):
    cached_data = await cache_manager.get(f"stock:{ticker}:precomputed")
    if not cached_data:
      # Trigger precompute and stream a "building" status
      background_tasks.add_task(precompute_service.run_full_pipeline, ticker)
      return JSONResponse({"status": "building", "retry_after": 30}, status_code=202)
    
    return StreamingResponse(
      stream_agent.stream_report(ticker, cached_data),
      media_type="text/event-stream",
      headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive"
      }
    )
```

### Prompt 3.2 — Peer comparison intelligence
```
Create agent/peer_analyzer.py — AI layer on top of the peer comparison data.

Build PeerAnalyzer class:

  async def generate_peer_narrative(subject: str, peers: list[PeerComparisonRow]) -> str
    """
    Given a subject ticker and its peers, generate a 3-4 sentence narrative
    explaining how the subject compares to its peers.
    
    Example output:
    "NVDA trades at a significant premium to semiconductor peers (PE 65x vs sector avg 28x),
    justified by its 3x higher gross margin (76% vs 26% avg). Revenue growth of 122% YoY
    dwarfs the peer median of 8%. The only concern vs peers is leverage — debt/equity of 0.4
    is higher than AMD (0.1) and INTC (0.3). [Source: DefeatBeta TTM Metrics, SEC 10-Q filings]"
    """
    
    metrics_table = format_peer_table(subject, peers)
    
    prompt = f"""
    Compare {subject} to its sector peers:
    
    {metrics_table}
    
    Write 3-4 sentences explaining:
    1. Where {subject} is most differentiated vs peers (premium or discount valuation and why)
    2. The most important metric where {subject} leads or lags
    3. Any red flags visible only in the peer comparison context
    
    Cite every number with [Source: DefeatBeta TTM Metrics].
    Be specific with numbers, not vague comparisons.
    """
    return await llm_router.complete_fast(prompt)

  def format_peer_table(subject: str, peers: list[PeerComparisonRow]) -> str
    - Format all peers + subject as a clean text table
    - Highlight subject row
    - Include: ticker, PE, EV/EBITDA, gross_margin, revenue_growth, debt_equity
    - Add sector averages as a summary row

  async def rank_peers_by_attractiveness(peers: list[PeerComparisonRow]) -> list[dict]
    - Score each peer on a simple composite: 
      (1/PE * 0.3) + (gross_margin * 0.3) + (revenue_growth * 0.2) + (1/debt_equity * 0.2)
    - Normalize to 0–100
    - Return sorted list with composite score and brief reason
    - This powers the "best alternative in sector" card on the frontend
```

---

## PHASE 4 — Quality & honesty layer (Day 6–8)

### Prompt 4.1 — Hallucination prevention
```
Create agent/honesty_layer.py — the trust foundation.

Build HonestyLayer class that wraps every LLM response before it leaves the agent layer:

  FINANCIAL_PATTERN = re.compile(r'\$[\d,]+|\d+\.?\d*%|\d+\.?\d*x|\d+\.?\d*B|\d+\.?\d*M')

  def audit_response(response_text: str, source_data: dict) -> AuditResult
    """
    Check every financial figure in the response appears in source_data.
    source_data = the raw data dict from cache (financials, transcript, etc.)
    """
    
    # Extract all numbers from response
    claimed_numbers = FINANCIAL_PATTERN.findall(response_text)
    
    # Build a flat string of all source data for lookup
    source_text = json.dumps(source_data, default=str).lower()
    
    flagged = []
    for number in claimed_numbers:
      # Normalize and check if it appears in source data
      normalized = number.replace('$','').replace(',','').replace('%','').replace('x','')
      if normalized not in source_text:
        flagged.append(number)
    
    return AuditResult(
      passed=len(flagged) == 0,
      flagged_claims=flagged,
      confidence_penalty=len(flagged) * 0.1  # reduce verdict confidence per unverified claim
    )

  def sanitize_response(response_text: str, audit: AuditResult) -> str
    - If audit.passed: return response_text unchanged
    - For each flagged claim: replace with "[unverified figure removed]"
    - Append at end: "Note: {len(audit.flagged_claims)} unverified figures were removed."
    - Return sanitized text

  def enforce_data_not_found(response_text: str) -> str
    - Scan for any sentence with a financial figure that lacks [Source: ...] citation
    - Replace entire sentence with: "[Data not available — source not in verified documents]"
    - This is the hardest check — every number needs a citation or it goes

Build AuditResult Pydantic model:
  class AuditResult(BaseModel):
    passed: bool
    flagged_claims: list[str]
    confidence_penalty: float
```

### Prompt 4.2 — Agent reasoning trace
```
Create agent/reasoning_trace.py — makes agent steps visible to the user (trust feature).

Build ReasoningTracer class:

This generates the "step-by-step" reasoning that gets streamed to the frontend
before the final verdict. Shows users the agent isn't a black box.

  class ReasoningStep(BaseModel):
    step_number: int
    title: str          # "Analyzing Q3 2024 10-Q filing..."
    status: str         # "running" | "done" | "error"
    finding: str | None # one-line finding, populated when done
    duration_ms: int | None

  async def trace_report_generation(ticker: str, cached_data: dict) -> AsyncGenerator[ReasoningStep, None]
    steps = [
      ("Reading latest 10-Q filing", lambda: analyze_filing_step(ticker, cached_data)),
      ("Analyzing financial performance", lambda: analyze_financials_step(cached_data)),
      ("Scanning for risk factors", lambda: analyze_risks_step(cached_data)),
      ("Checking earnings call tone", lambda: analyze_transcript_step(cached_data)),
      ("Detecting insider activity", lambda: check_insider_step(cached_data)),
      ("Reviewing superinvestor positions", lambda: check_superinvestor_step(ticker)),
      ("Computing final verdict", lambda: None)  # last step has no sub-function
    ]
    
    for i, (title, fn) in enumerate(steps):
      step = ReasoningStep(step_number=i+1, title=title, status="running")
      yield step  # frontend shows spinner for this step
      
      start = time.monotonic()
      try:
        if fn():
          result = await fn()
          finding = extract_one_line_finding(result)
        else:
          finding = None
        status = "done"
      except Exception as e:
        finding = f"Error: {str(e)[:50]}"
        status = "error"
      
      step.status = status
      step.finding = finding
      step.duration_ms = int((time.monotonic() - start) * 1000)
      yield step  # frontend updates the step with result

  def extract_one_line_finding(analysis_result: dict) -> str
    - Extract the single most important sentence from any analysis result
    - Max 100 characters
    - Examples: "Revenue grew 12% YoY, beating estimates by 3.2%"
                "High hedging language detected — deflection count 4 (above avg of 1.2)"
```

---

## PHASE 5 — Integration & testing (Day 8–10)

### Prompt 5.1 — Mount agent router into backend
```
In backend/main.py, mount the agent router:

  from agent.router import agent_router
  app.include_router(agent_router)

Verify the full pipeline works end-to-end:
1. Hit GET /api/stock/AAPL/report/stream
2. Verify you receive SSE events in this order:
   - section_start (overview)
   - data (financials) — within 500ms
   - data (snowflake) — within 500ms
   - data (sentiment) — within 500ms
   - data (filing_diff) — within 1s
   - data (insider_cluster) — within 1s
   - reasoning_step (×7 steps, each within 500ms of prior)
   - data (verdict) — within 30s total from start
   - done

3. Verify verdict JSON contains: verdict, verdict_confidence, plain_english_summary,
   three_bulls (each with source), three_risks (each with source)

4. Run HonestyLayer.audit_response on the verdict — must pass (0 flagged claims)
   for AAPL which has abundant verifiable data.

Write agent/tests/test_pipeline.py:
- test_full_pipeline_aapl(): run generate_report("AAPL", mock_cached_data) — assert StockReport valid
- test_citation_guard(): give LLM response with fake numbers — assert they get flagged
- test_hedging_detector(): feed known hedgy transcript — assert score > 0.5
- test_superinvestor_detector(): fetch real AAPL 13F data — assert cluster detected (Berkshire holds AAPL)
- test_streaming(): consume stream_report generator — assert all required events present
```

### Prompt 5.2 — Performance validation
```
Measure and optimize until targets are met:

Run this benchmark script for AAPL (must be pre-computed in cache):

  import asyncio, time
  
  async def benchmark():
    start = time.monotonic()
    first_event_time = None
    
    async for event in stream_agent.stream_report("AAPL", await get_cached_data("AAPL")):
      if first_event_time is None:
        first_event_time = time.monotonic() - start
        print(f"Time to first content: {first_event_time:.2f}s")
      parsed = json.loads(event.replace("data: ", ""))
      if parsed.get("event") == "done":
        total = time.monotonic() - start
        print(f"Total time: {total:.2f}s")
        break
  
  asyncio.run(benchmark())

TARGETS (must hit these before merge):
  - Time to first content: < 2 seconds
  - Full report (including verdict): < 45 seconds
  - Anthropic prompt cache hit rate: > 70% (check via API response headers)
  - LLM cost per report: < $0.05 (log token counts)

If NOT hitting targets:
  - Ensure filing text is in cached_prefix (not in the dynamic message)
  - Check asyncio.gather is actually running in parallel (add timing logs per subagent)
  - Reduce transcript to 15K chars instead of 20K if TTFT is slow
  - Downgrade synthesis from Sonnet to Haiku for non-verdict sections

Tell Person 1 and Person 3 when targets are met with a shared Slack/message:
"Agent layer ready. Stream endpoint on /api/stock/{ticker}/report/stream.
 AAPL benchmark: {first_event}s first content, {total}s full report."
```

---

## MERGE CHECKLIST (before combining with Person 1 & 3)

```
[ ] GET /api/stock/AAPL/report/stream emits 8+ SSE events in correct order
[ ] All events contain "event" key with correct event type
[ ] Verdict JSON has verdict, verdict_confidence, plain_english_summary, bulls, risks
[ ] Every bull/risk point has non-empty source and source_url fields
[ ] HonestyLayer passes for AAPL (well-documented ticker)
[ ] Hedging score for a known hedgy earnings call > 0.5
[ ] Superinvestor cluster detected for AAPL (Berkshire + others hold it)
[ ] agent/tests/ all pass: pytest agent/tests/ -v
[ ] No import of shared/schemas.py was modified (it's shared — changes break other devs)
[ ] Reasoning trace yields exactly 7 steps for a full report
[ ] Benchmark: < 2s first content, < 45s full report for cached ticker
```
