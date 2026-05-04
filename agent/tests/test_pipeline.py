import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from shared.schemas import (
    BullRiskPoint,
    FinancialSnapshot,
    FilingDiff,
    FundEntry,
    InsiderCluster,
    InsiderTrade,
    SentimentPulse,
    SnowflakeScores,
    StockReport,
    SuperinvestorCluster,
)

# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

MOCK_FINANCIALS = FinancialSnapshot(
    ticker="AAPL",
    pe_ratio=28.5,
    ev_ebitda=22.3,
    gross_margin=43.1,
    revenue_ttm=385_600_000_000.0,
    debt_to_equity=1.78,
    revenue_growth_yoy=5.1,
)

MOCK_TRANSCRIPT = """
Prepared Remarks:
CEO: Good morning everyone. We delivered strong results this quarter with revenue of $94.9 billion,
up 5% year over year. Our services business reached an all-time high.
[Source: AAPL Earnings Transcript]

Q&A Section:
Analyst: Can you provide more color on China revenue?
CEO: China remains challenging given the macro environment. We're cautious about the near-term
outlook. We'll see how things develop and monitor closely.

Analyst: What about AI features driving upgrades?
CEO: We're very excited about Apple Intelligence. We expect to see this drive upgrades over time.
"""

MOCK_FILING_TEXT = """
RISK FACTORS
The following risk factors may affect our business:
1. Competition: We face intense competition in all our product categories.
2. Supply chain: We depend on single-source suppliers for certain components.
3. Regulatory: We are subject to complex and evolving laws worldwide.

MANAGEMENT DISCUSSION AND ANALYSIS
Revenue for the quarter was $94.9 billion, an increase of 5% year over year.
Gross margin was 43.1%, compared to 43.3% in the prior year quarter.
[Source: AAPL 10-Q MD&A Section]
"""

MOCK_CACHED_DATA = {
    "financials": MOCK_FINANCIALS,
    "transcript": MOCK_TRANSCRIPT,
    "filing_10q_text": MOCK_FILING_TEXT,
    "filing_diff": FilingDiff(
        ticker="AAPL",
        period="Q3 2024",
        section="MD&A",
        diff_summary="Revenue grew 5% YoY",
    ),
    "news": [
        {"title": "Apple beats Q3 estimates", "source": "Reuters", "url": ""},
        {"title": "Apple Intelligence driving upgrade cycle", "source": "Bloomberg", "url": ""},
    ],
    "insider_cluster": InsiderCluster(
        ticker="AAPL",
        period_days=90,
        trades=[
            InsiderTrade(
                insider_name="Tim Cook",
                title="CEO",
                trade_type="sell",
                shares=100_000,
                value_usd=19_000_000.0,
                filed_at=datetime(2024, 8, 1),
            )
        ],
        net_shares=-100_000,
        cluster_signal="bearish",
    ),
    "snowflake_scores": SnowflakeScores(
        ticker="AAPL",
        value=7.2,
        growth=6.8,
        profitability=8.5,
        health=7.0,
        smart_money=8.0,
        overall=7.5,
    ),
    "sentiment": SentimentPulse(
        ticker="AAPL",
        overall_score=0.35,
        news_score=0.4,
        analyst_consensus="buy",
        analyst_count=32,
    ),
    "congressional_trades": [],
}

_MOCK_VERDICT_JSON = json.dumps({
    "verdict": "wait",
    "verdict_confidence": 0.65,
    "plain_english_summary": "Apple has solid fundamentals but faces near-term headwinds in China.",
    "three_bulls": [
        {"text": "Services revenue hit an all-time high.", "source": "AAPL 10-Q MD&A Section", "source_url": ""},
        {"text": "Gross margin remains strong at 43%.", "source": "AAPL 10-Q MD&A Section", "source_url": ""},
        {"text": "Strong cash generation funds buybacks.", "source": "AAPL 10-Q", "source_url": ""},
    ],
    "three_risks": [
        {"text": "China revenue faces macro headwinds.", "source": "AAPL Earnings Transcript", "source_url": ""},
        {"text": "Single-source supply chain concentration.", "source": "AAPL 10-Q Risk Factors", "source_url": ""},
        {"text": "Premium valuation leaves little room for disappointment.", "source": "DefeatBeta TTM Metrics", "source_url": ""},
    ],
})

_MOCK_SECTION_JSON = '{"summary": "test", "key_metrics": {}, "trends": [], "citations": []}'


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_pipeline_aapl():
    from agent.orchestrator import StockReportOrchestrator

    with (
        patch("agent.llm_router.LLMRouter.complete_fast", new_callable=AsyncMock) as mock_fast,
        patch("agent.llm_router.LLMRouter.complete_smart", new_callable=AsyncMock) as mock_smart,
    ):
        mock_fast.return_value = _MOCK_SECTION_JSON
        mock_smart.return_value = _MOCK_VERDICT_JSON

        report = await StockReportOrchestrator().generate_report("AAPL", MOCK_CACHED_DATA)

    assert isinstance(report, StockReport)
    assert report.ticker == "AAPL"
    assert report.verdict in ("buy", "wait", "avoid")
    assert 0.0 <= report.verdict_confidence <= 1.0
    assert len(report.plain_english_summary) > 0
    assert len(report.three_bulls) <= 3
    assert len(report.three_risks) <= 3
    for point in report.three_bulls + report.three_risks:
        assert point.source, "Every bull/risk point must have a non-empty source"


@pytest.mark.asyncio
async def test_citation_guard():
    from agent.citation_guard import CitationGuard

    guard = CitationGuard()
    allowed = ["AAPL 10-Q", "AAPL 10-K", "DefeatBeta TTM Metrics"]

    cited = (
        "Revenue grew 5% year over year [Source: AAPL 10-Q MD&A Section]. "
        "Gross margin was 43.1% [Source: AAPL 10-Q MD&A Section]."
    )
    uncited = "Revenue grew 5% year over year. Gross margin was 43.1%."

    claims = guard.extract_citations(cited)
    assert len(claims) > 0
    assert any("10-Q" in c["source"] for c in claims)

    validated = guard.validate_citations(claims, allowed)
    assert all(c["verification_status"] == "VERIFIED" for c in validated)

    stripped = guard.strip_unverified_claims(uncited, allowed)
    assert "[Data not available from verified sources]" in stripped


@pytest.mark.asyncio
async def test_hedging_detector():
    from agent.hedging_detector import HedgingDetector

    detector = HedgingDetector()
    hedgy = (
        "CEO: We face uncertain and challenging macro environment. "
        "There may be headwinds in the volatile market. "
        "We might see difficult conditions. Potentially subject to risk. "
        "We're cautious and careful. We hope conditions improve. "
        "It's too early to say. We'll monitor the situation. "
        "I'll have to get back to you on specific numbers. "
        "We'll provide more color later. We'll follow up on that. "
        "That's something we're still evaluating. "
        "I don't want to get ahead of ourselves on guidance."
    ) * 3  # repeat for meaningful word count

    score = detector.compute_hedging_score(hedgy)
    assert score > 0.5, f"Expected score > 0.5 for hedge-heavy transcript, got {score}"

    deflections = detector.compute_deflection_count(hedgy)
    assert deflections > 0


@pytest.mark.asyncio
async def test_superinvestor_detector():
    from agent.superinvestor_detector import SuperinvestorDetector

    detector = SuperinvestorDetector()

    def _aapl_holding(name, cik, quarter):
        if name in ("Berkshire Hathaway", "Two Sigma", "Citadel"):
            return [
                {
                    "ticker": "AAPL",
                    "shares": 1_000_000,
                    "value_usd": 190_000_000,
                    "change_from_prior": 50_000,
                    "pct_of_fund_aum": 2.5,
                }
            ]
        return []

    with patch.object(
        detector, "fetch_13f_holdings", new_callable=AsyncMock, side_effect=_aapl_holding
    ):
        cluster = await detector.detect_cluster("AAPL", "2024Q2")

    assert cluster is not None, "3 funds hold AAPL — cluster should be detected"
    assert len(cluster.funds) >= 3
    assert cluster.conviction_score > 0


@pytest.mark.asyncio
async def test_streaming():
    from agent.stream_agent import StreamingAgent

    agent = StreamingAgent()

    with (
        patch("agent.llm_router.LLMRouter.complete_fast", new_callable=AsyncMock) as mock_fast,
        patch("agent.llm_router.LLMRouter.complete_smart", new_callable=AsyncMock) as mock_smart,
    ):
        mock_fast.return_value = _MOCK_SECTION_JSON
        mock_smart.return_value = _MOCK_VERDICT_JSON

        events = []
        async for sse_str in agent.stream_report("AAPL", MOCK_CACHED_DATA):
            assert sse_str.startswith("data: "), "SSE event must start with 'data: '"
            payload = json.loads(sse_str[len("data: "):])
            events.append(payload)

    event_types = [e["event"] for e in events]
    assert "section_start" in event_types
    assert "data" in event_types
    assert "done" in event_types

    financials_idx = next(
        (i for i, e in enumerate(events) if e.get("section") == "financials"), None
    )
    done_idx = next(
        (i for i, e in enumerate(events) if e["event"] == "done"), None
    )
    assert financials_idx is not None, "financials event must be present"
    assert financials_idx < done_idx, "financials must arrive before done"

    verdict_events = [e for e in events if e.get("section") == "verdict"]
    assert len(verdict_events) == 1
    verdict = verdict_events[0]["payload"]
    assert "verdict" in verdict
    assert "summary" in verdict
    assert "bulls" in verdict
    assert "risks" in verdict
