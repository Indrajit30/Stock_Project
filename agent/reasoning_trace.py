import logging
import time
from typing import AsyncGenerator, Callable, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ReasoningStep(BaseModel):
    step_number: int
    title: str
    status: str          # "running" | "done" | "error"
    finding: Optional[str] = None
    duration_ms: Optional[int] = None


class ReasoningTracer:
    async def trace_report_generation(
        self, ticker: str, cached_data: dict
    ) -> AsyncGenerator[ReasoningStep, None]:
        steps: list[tuple[str, Optional[Callable]]] = [
            ("Reading latest 10-Q filing",        lambda: self._analyze_filing_step(ticker, cached_data)),
            ("Analyzing financial performance",   lambda: self._analyze_financials_step(cached_data)),
            ("Scanning for risk factors",         lambda: self._analyze_risks_step(cached_data)),
            ("Checking earnings call tone",       lambda: self._analyze_transcript_step(cached_data)),
            ("Detecting insider activity",        lambda: self._check_insider_step(cached_data)),
            ("Reviewing superinvestor positions", lambda: self._check_superinvestor_step(ticker)),
            ("Computing final verdict",           None),
        ]

        for i, (title, fn) in enumerate(steps):
            step = ReasoningStep(step_number=i + 1, title=title, status="running")
            yield step

            start = time.monotonic()
            finding = None
            status = "done"
            try:
                if fn is not None:
                    result = await fn()
                    finding = self.extract_one_line_finding(result)
            except Exception as e:
                finding = f"Error: {str(e)[:50]}"
                status = "error"
                logger.warning(f"Reasoning step '{title}' failed: {e}")

            step.status = status
            step.finding = finding
            step.duration_ms = int((time.monotonic() - start) * 1000)
            yield step

    def extract_one_line_finding(self, result) -> Optional[str]:
        if result is None:
            return None
        if isinstance(result, str):
            lines = [l.strip() for l in result.strip().splitlines() if l.strip()]
            return lines[0][:100] if lines else None
        if isinstance(result, dict):
            for key in ("summary", "finding", "interpretation", "content"):
                val = result.get(key)
                if val and isinstance(val, str):
                    return val.strip()[:100]
            for val in result.values():
                if isinstance(val, str) and val.strip():
                    return val.strip()[:100]
        return str(result)[:100]

    async def _analyze_filing_step(self, ticker: str, cached_data: dict):
        text = cached_data.get("filing_10q_text", "")
        if not text:
            return "No 10-Q text available"
        return f"Loaded {ticker} 10-Q filing ({len(text.split()):,} words)"

    async def _analyze_financials_step(self, cached_data: dict):
        financials = cached_data.get("financials")
        if not financials:
            return "No financial data available"
        fin = financials if isinstance(financials, dict) else financials.model_dump()
        pe = fin.get("pe_ratio")
        gm = fin.get("gross_margin")
        gm_display = f"{gm * 100:.1f}%" if isinstance(gm, (int, float)) and gm <= 1 else f"{gm}%"
        return f"PE: {pe}, Gross margin: {gm_display}" if (pe or gm) else "Financial metrics loaded"

    async def _analyze_risks_step(self, cached_data: dict):
        text = cached_data.get("filing_10q_text", "")
        idx = text.lower().find("risk factor")
        if idx == -1:
            return "Risk factors section not found in filing"
        return text[idx: idx + 100].replace("\n", " ").strip()

    async def _analyze_transcript_step(self, cached_data: dict):
        transcript = cached_data.get("transcript", "")
        if not transcript:
            return "No earnings transcript available"
        from agent.hedging_detector import HedgingDetector
        score = HedgingDetector().compute_hedging_score(transcript)
        return f"Hedging score: {score:.2f}/1.0"

    async def _check_insider_step(self, cached_data: dict):
        cluster = cached_data.get("insider_cluster")
        if not cluster:
            return "No insider cluster data"
        c = cluster if isinstance(cluster, dict) else cluster.model_dump()
        signal = c.get("signal_strength")
        if signal is not None:
            return f"{c.get('insider_count', 0)} insiders, signal strength {float(signal):.2f}/1.00"
        return f"Signal: {c.get('cluster_signal', 'neutral')}, net shares: {c.get('net_shares', 0):+,}"

    async def _check_superinvestor_step(self, ticker: str):
        from agent.superinvestor_detector import superinvestor_detector
        cluster = await superinvestor_detector.detect_cluster(ticker)
        if cluster is None:
            return "No superinvestor cluster detected"
        return (
            f"{len(cluster.funds)} funds holding {ticker}, "
            f"conviction: {cluster.conviction_score:.1f}/10"
        )


reasoning_tracer = ReasoningTracer()
