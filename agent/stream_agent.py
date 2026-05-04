import json
import logging
from datetime import datetime
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class StreamingAgent:
    def sse_event(self, event_type: str, data: dict) -> str:
        return f"data: {json.dumps({'event': event_type, **data}, default=str)}\n\n"

    async def stream_report(
        self, ticker: str, cached_data: dict
    ) -> AsyncGenerator[str, None]:
        from agent.orchestrator import StockReportOrchestrator

        yield self.sse_event("section_start", {"section": "overview", "ticker": ticker})

        # Yield all cached sections immediately — zero LLM latency
        financials = cached_data.get("financials")
        if financials:
            payload = financials if isinstance(financials, dict) else financials.model_dump()
            yield self.sse_event("data", {
                "section": "financials",
                "payload": payload,
                "source": "DefeatBeta API",
            })

        snowflake = cached_data.get("snowflake_scores")
        if snowflake:
            payload = snowflake if isinstance(snowflake, dict) else snowflake.model_dump()
            yield self.sse_event("data", {"section": "snowflake", "payload": payload})

        sentiment = cached_data.get("sentiment")
        if sentiment:
            payload = sentiment if isinstance(sentiment, dict) else sentiment.model_dump()
            yield self.sse_event("data", {"section": "sentiment", "payload": payload})

        filing_diff = cached_data.get("filing_diff")
        if filing_diff:
            payload = filing_diff if isinstance(filing_diff, dict) else filing_diff.model_dump()
            yield self.sse_event("data", {"section": "filing_diff", "payload": payload})

        insider = cached_data.get("insider_cluster")
        if insider:
            payload = insider if isinstance(insider, dict) else insider.model_dump()
            yield self.sse_event("data", {"section": "insider_cluster", "payload": payload})

        congress = cached_data.get("congressional_trades")
        if congress:
            yield self.sse_event("data", {
                "section": "congressional_trades",
                "payload": congress,
            })

        # Start LLM synthesis
        yield self.sse_event("section_start", {
            "section": "ai_synthesis",
            "status": "generating",
        })

        orchestrator = StockReportOrchestrator()

        # Stream reasoning steps so the user sees progress immediately
        async for step in orchestrator.stream_reasoning_steps(ticker, cached_data):
            step_data = step if isinstance(step, dict) else step.model_dump()
            yield self.sse_event("reasoning_step", step_data)

        try:
            report = await orchestrator.generate_report(ticker, cached_data)
            yield self.sse_event("data", {
                "section": "verdict",
                "payload": {
                    "ticker": report.ticker,
                    "company_name": report.company_name,
                    "verdict": report.verdict,
                    "verdict_confidence": report.verdict_confidence,
                    "plain_english_summary": report.plain_english_summary,
                    "three_bulls": [b.model_dump() for b in report.three_bulls],
                    "three_risks": [r.model_dump() for r in report.three_risks],
                },
            })
        except Exception as e:
            logger.error(f"Synthesis failed for {ticker}: {e}")
            yield self.sse_event("error", {"message": str(e)})

        yield self.sse_event("done", {
            "ticker": ticker,
            "generated_at": datetime.utcnow().isoformat(),
        })


stream_agent = StreamingAgent()
