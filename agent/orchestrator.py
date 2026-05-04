import asyncio
import json
import logging
from datetime import datetime

from shared.schemas import CitedPoint, FinancialSnapshot, SnowflakeScores, StockReport
from agent.llm_router import llm_router
from agent.citation_guard import citation_guard, SYSTEM_PROMPT_BASE

logger = logging.getLogger(__name__)


class StockReportOrchestrator:
    async def generate_report(self, ticker: str, cached_data: dict) -> StockReport:
        # STEP 1 — Build stable cached prefix (filing text goes into system prompt
        # so OpenAI's automatic prompt caching gives ~50% cost reduction on cache hits)
        filing_cache_prefix = (
            f"=== {ticker} 10-Q FILING TEXT ===\n"
            f"{cached_data.get('filing_10q_text', '')[:40000]}\n\n"
            f"=== EARNINGS CALL TRANSCRIPT ===\n"
            f"{cached_data.get('transcript', '')[:20000]}"
        )

        # STEP 2 — Fan out 5 parallel subagent calls
        financials = cached_data.get("financials")
        results = await asyncio.gather(
            self.analyze_financials(ticker, financials, filing_cache_prefix),
            self.analyze_risks(ticker, cached_data.get("filing_10q_text", ""), filing_cache_prefix),
            self.analyze_growth(ticker, financials, cached_data.get("transcript", "")),
            self.analyze_sentiment_and_news(
                ticker, cached_data.get("news", []), cached_data.get("sentiment")
            ),
            self.analyze_mgmt_tone(ticker, cached_data.get("transcript", "")),
            return_exceptions=True,
        )
        results = [str(r) if isinstance(r, Exception) else r for r in results]

        # STEP 3 — Synthesize with smart model
        synthesis = await self.synthesize_all_sections(ticker, results, cached_data)

        # STEP 4 — Citation guard post-pass
        allowed = self._build_allowed_sources(ticker)
        raw_claims = citation_guard.extract_citations(synthesis.plain_english_summary)
        citation_guard.validate_citations(raw_claims, allowed)

        return synthesis

    async def analyze_financials(
        self, ticker: str, financials, cache_prefix: str
    ) -> dict:
        if financials is None:
            return {"section": "financials", "content": "No financial data available."}

        fin = financials if isinstance(financials, dict) else financials.model_dump()
        prompt = (
            f"Analyze these financial metrics for {ticker}:\n"
            f"PE Ratio: {fin.get('pe_ratio')}\n"
            f"EV/EBITDA: {fin.get('ev_ebitda')}\n"
            f"Gross Margin: {fin.get('gross_margin')}\n"
            f"Revenue TTM: {fin.get('revenue_ttm')}\n"
            f"Debt/Equity: {fin.get('debt_to_equity')}\n\n"
            f"From the filing text above, find specific commentary on:\n"
            f"1. Revenue trends and guidance\n"
            f"2. Margin expansion or compression\n"
            f"3. Any one-time items affecting results\n\n"
            f"Cite every claim with [Source: {ticker} 10-Q section name].\n"
            f"Format: JSON with keys: summary, key_metrics, trends, citations"
        )
        result = await llm_router.complete_fast(
            prompt, system=SYSTEM_PROMPT_BASE, cached_prefix=cache_prefix
        )
        return {"section": "financials", "content": result}

    async def analyze_risks(
        self, ticker: str, filing_text: str, cache_prefix: str
    ) -> dict:
        prompt = (
            f"From the {ticker} 10-Q filing text, extract the top 3 risk factors.\n"
            f"For each risk:\n"
            f"1. State the risk clearly in one sentence\n"
            f"2. Quote the relevant section\n"
            f"3. Cite with [Source: {ticker} 10-Q Risk Factors]\n\n"
            f"Format: JSON with keys: risks (list of {{risk, quote, citation}})"
        )
        result = await llm_router.complete_fast(
            prompt, system=SYSTEM_PROMPT_BASE, cached_prefix=cache_prefix
        )
        return {"section": "risks", "content": result}

    async def analyze_growth(
        self, ticker: str, financials, transcript: str
    ) -> dict:
        fin = {}
        if financials:
            fin = financials if isinstance(financials, dict) else financials.model_dump()

        snippet = transcript[:8000] if transcript else "No transcript available"
        prompt = (
            f"Analyze growth prospects for {ticker}.\n"
            f"Revenue growth YoY: {fin.get('revenue_growth_yoy')}\n\n"
            f"Transcript excerpt:\n{snippet}\n\n"
            f"Extract:\n"
            f"1. Revenue growth trend and management guidance\n"
            f"2. New products, markets, or business lines mentioned\n"
            f"3. Any guidance upgrades or downgrades\n\n"
            f"Cite every claim with [Source: {ticker} Earnings Transcript or 10-Q].\n"
            f"Format: JSON with keys: growth_summary, guidance, new_initiatives"
        )
        result = await llm_router.complete_fast(prompt, system=SYSTEM_PROMPT_BASE)
        return {"section": "growth", "content": result}

    async def analyze_sentiment_and_news(
        self, ticker: str, news: list, sentiment
    ) -> dict:
        news_str = json.dumps(news[:5], default=str) if news else "No news available"
        sent_str = ""
        if sentiment:
            sent = sentiment if isinstance(sentiment, dict) else sentiment.model_dump()
            sent_str = (
                f"Overall sentiment: {sent.get('overall_score')}, "
                f"News sentiment: {sent.get('news_score')}, "
                f"Analyst consensus: {sent.get('analyst_consensus')}"
            )

        prompt = (
            f"Sentiment and news analysis for {ticker}:\n"
            f"{sent_str}\n\n"
            f"Top news items:\n{news_str}\n\n"
            f"Summarize:\n"
            f"1. Overall market sentiment toward {ticker}\n"
            f"2. Top 3 most relevant news items and their potential impact\n"
            f"3. Any material events (earnings surprise, guidance change, executive departure)\n\n"
            f"Cite with [Source: News/Sentiment Data].\n"
            f"Format: JSON with keys: sentiment_summary, top_news, material_events"
        )
        result = await llm_router.complete_fast(prompt, system=SYSTEM_PROMPT_BASE)
        return {"section": "sentiment", "content": result}

    async def analyze_mgmt_tone(self, ticker: str, transcript: str) -> dict:
        from agent.hedging_detector import HedgingDetector
        detector = HedgingDetector()
        try:
            result = await detector.analyze_transcript(ticker, transcript)
            return {"section": "mgmt_tone", "content": result}
        except Exception as e:
            logger.error(f"Hedging analysis failed: {e}")
            return {"section": "mgmt_tone", "content": {"error": str(e)}}

    async def synthesize_all_sections(
        self, ticker: str, section_results: list, all_data: dict
    ) -> StockReport:
        combined = "\n\n".join(
            (
                f"=== {r.get('section', f'section_{i}').upper()} ===\n"
                f"{json.dumps(r.get('content', r), default=str, indent=2)}"
            )
            if isinstance(r, dict)
            else f"=== SECTION {i} ===\n{r}"
            for i, r in enumerate(section_results)
        )

        synthesis_prompt = (
            f"Based on this comprehensive analysis of {ticker}:\n\n"
            f"{combined}\n\n"
            f"Produce a final investment verdict in this exact JSON structure:\n"
            f'{{\n'
            f'  "verdict": "buy" | "wait" | "avoid",\n'
            f'  "verdict_confidence": 0.0-1.0,\n'
            f'  "plain_english_summary": "2-3 sentence plain English summary for a retail investor",\n'
            f'  "three_bulls": [\n'
            f'    {{"text": "...", "source": "...", "source_url": ""}},\n'
            f'    {{"text": "...", "source": "...", "source_url": ""}},\n'
            f'    {{"text": "...", "source": "...", "source_url": ""}}\n'
            f'  ],\n'
            f'  "three_risks": [ ...same structure... ]\n'
            f'}}\n\n'
            f"Rules:\n"
            f"- verdict_confidence > 0.8 only if multiple data points agree\n"
            f"- every bull/risk MUST have a source from the analysis above\n"
            f"- plain_english_summary must be jargon-free (no EBITDA, no YoY)\n"
            f"- respond with ONLY the JSON object, no markdown fences"
        )

        messages = [{"role": "user", "content": synthesis_prompt}]
        response = await llm_router.complete_smart(messages, system=SYSTEM_PROMPT_BASE)
        return self._parse_report(response, ticker, all_data)

    async def stream_reasoning_steps(self, ticker: str, cached_data: dict):
        from agent.reasoning_trace import ReasoningTracer
        tracer = ReasoningTracer()
        async for step in tracer.trace_report_generation(ticker, cached_data):
            yield step

    def _build_citation_url(self, ticker: str, source: str) -> str:
        sl = source.lower()
        if "10-q" in sl or "10q" in sl:
            return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}&type=10-Q&dateb=&owner=include&count=5"
        if "10-k" in sl or "10k" in sl:
            return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}&type=10-K&dateb=&owner=include&count=5"
        if "transcript" in sl or "earnings" in sl:
            return f"https://finance.yahoo.com/quote/{ticker}/"
        return ""

    def _parse_report(self, response: str, ticker: str, all_data: dict) -> StockReport:
        # Use ticker from all_data if caller passed it through
        ticker = all_data.get("ticker") or ticker

        try:
            clean = response.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                clean = clean.split("```")[1].split("```")[0].strip()

            start = clean.find("{")
            end = clean.rfind("}") + 1
            if start >= 0 and end > start:
                clean = clean[start:end]

            data = json.loads(clean)

            def _cited(item: dict) -> CitedPoint:
                url = item.get("source_url") or self._build_citation_url(ticker, item.get("source", ""))
                return CitedPoint(**{**item, "source_url": url})

            bulls = [_cited(b) for b in data.get("three_bulls", [])]
            risks = [_cited(r) for r in data.get("three_risks", [])]
            financials = all_data.get("financials") or {}
            snowflake = all_data.get("snowflake_scores") or {}

            verdict = str(data.get("verdict", "wait")).lower()
            if verdict not in {"buy", "wait", "avoid"}:
                verdict = "wait"

            return StockReport(
                ticker=ticker,
                company_name=data.get("company_name") or f"{ticker} Corp.",
                generated_at=datetime.utcnow(),
                verdict=verdict,
                verdict_confidence=float(data.get("verdict_confidence", 0.5)),
                plain_english_summary=data.get(
                    "plain_english_summary", "Analysis unavailable."
                ),
                three_bulls=bulls[:3],
                three_risks=risks[:3],
                snowflake_scores=(
                    snowflake
                    if isinstance(snowflake, SnowflakeScores)
                    else SnowflakeScores(**snowflake)
                ),
                financials=(
                    financials
                    if isinstance(financials, FinancialSnapshot)
                    else FinancialSnapshot(**financials)
                ),
            )
        except Exception as e:
            logger.error(f"Failed to parse synthesis response: {e}\nRaw: {response[:200]}")
            financials = all_data.get("financials") or {}
            snowflake = all_data.get("snowflake_scores") or {}
            return StockReport(
                ticker=ticker,
                company_name=f"{ticker} Corp.",
                generated_at=datetime.utcnow(),
                verdict="wait",
                verdict_confidence=0.3,
                plain_english_summary="Analysis could not be completed due to a parsing error.",
                three_bulls=[],
                three_risks=[],
                snowflake_scores=(
                    snowflake
                    if isinstance(snowflake, SnowflakeScores)
                    else SnowflakeScores(**snowflake)
                ),
                financials=(
                    financials
                    if isinstance(financials, FinancialSnapshot)
                    else FinancialSnapshot(**financials)
                ),
            )

    def _build_allowed_sources(self, ticker: str) -> list[str]:
        return [
            f"{ticker} 10-Q",
            f"{ticker} 10-K",
            f"{ticker} Earnings Transcript",
            "DefeatBeta TTM Metrics",
            "News/Sentiment Data",
            "EDGAR 13F Filings",
        ]
