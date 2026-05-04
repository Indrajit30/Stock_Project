import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone

from shared.schemas import (
    FinancialSnapshot,
    InsiderCluster,
    SnowflakeScores,
    StockReport,
    SuperinvestorCluster,
)

logger = logging.getLogger(__name__)

PRECOMPUTE_TICKERS = [
    t.strip()
    for t in os.getenv(
        "PRECOMPUTE_TICKERS",
        "AAPL,MSFT,GOOGL,AMZN,META,NVDA,TSLA,JPM,JNJ,V",
    ).split(",")
    if t.strip()
]


def compute_snowflake_scores(
    financials: FinancialSnapshot,
    price_history: list,
    insider_cluster: InsiderCluster | None,
    superinvestor: SuperinvestorCluster | None,
) -> SnowflakeScores:
    """Algorithmic fallback scorer — used when the LLM scorer is unavailable."""

    def _clamp(v: float) -> float:
        return max(0.0, min(10.0, v))

    # Value score: step-function on PE + EV/EBITDA
    # Lower multiples = cheaper = higher score; None/negative = unprofitable = neutral 4
    def _pe_score(pe: float | None) -> float:
        if pe is None or pe <= 0:
            return 4.0
        if pe < 10:   return 9.5
        if pe < 15:   return 8.5
        if pe < 20:   return 7.5
        if pe < 30:   return 6.0
        if pe < 45:   return 4.5
        if pe < 70:   return 3.0
        if pe < 120:  return 2.0
        return 1.0

    def _ev_score(ev: float | None) -> float:
        if ev is None or ev <= 0:
            return 4.0
        if ev < 8:    return 9.5
        if ev < 12:   return 8.0
        if ev < 18:   return 6.5
        if ev < 25:   return 5.0
        if ev < 40:   return 3.5
        if ev < 60:   return 2.5
        return 1.5

    value = _clamp((_pe_score(financials.pe_ratio) + _ev_score(financials.ev_ebitda)) / 2)

    # Growth score: revenue YoY + gross margin quality
    rev_growth = financials.revenue_growth_yoy
    if rev_growth is None:
        growth = 5.0
    elif rev_growth > 0.40:  growth = 9.5
    elif rev_growth > 0.25:  growth = 8.5
    elif rev_growth > 0.15:  growth = 7.5
    elif rev_growth > 0.05:  growth = 6.0
    elif rev_growth > 0.0:   growth = 5.0
    elif rev_growth > -0.05: growth = 3.5
    elif rev_growth > -0.15: growth = 2.5
    else:                    growth = 1.5

    # Bonus for strong gross margins (high-quality business)
    gm = financials.gross_margin or 0.0
    if gm > 0.70:   growth = min(10.0, growth + 1.0)
    elif gm > 0.50: growth = min(10.0, growth + 0.5)
    growth = _clamp(growth)

    # Health score: debt/equity + profitability
    dte = financials.debt_to_equity
    if dte is None:
        health = 5.0
    elif dte < 0:    health = 3.0  # negative equity is a red flag
    elif dte < 0.3:  health = 9.5
    elif dte < 0.6:  health = 8.0
    elif dte < 1.0:  health = 6.5
    elif dte < 2.0:  health = 5.0
    elif dte < 4.0:  health = 3.5
    else:            health = 2.0

    # Penalise loss-makers unless they're high-growth
    net_margin = (
        financials.net_income_ttm / financials.revenue_ttm
        if financials.net_income_ttm is not None and financials.revenue_ttm
        else None
    )
    if net_margin is not None and net_margin < -0.30 and (rev_growth or 0) < 0.20:
        health = max(1.0, health - 2.0)
    health = _clamp(health)

    # Momentum score: price vs 52w high + 200-day MA
    if price_history and len(price_history) >= 50:
        closes = [p["close"] for p in price_history if p.get("close")]
        if closes:
            latest = closes[-1]
            high_52w = max(closes[-min(252, len(closes)):])
            ma_len = min(200, len(closes))
            ma = sum(closes[-ma_len:]) / ma_len
            vs_high = latest / high_52w if high_52w else 1.0
            vs_ma   = latest / ma if ma else 1.0
            momentum = _clamp((vs_high * 0.4 + vs_ma * 0.6) * 10)
        else:
            momentum = 5.0
    else:
        momentum = 5.0

    # Smart money score
    insider_signal = insider_cluster.signal_strength if insider_cluster else 0.0
    super_signal   = min(len(superinvestor.funds) / 5.0, 1.0) if superinvestor else 0.0
    smart_money    = _clamp((insider_signal * 0.5 + super_signal * 0.5) * 10)

    return SnowflakeScores(
        value=round(value, 2),
        growth=round(growth, 2),
        health=round(health, 2),
        momentum=round(momentum, 2),
        smart_money=round(smart_money, 2),
    )


async def compute_snowflake_scores_llm(
    ticker: str,
    company_name: str,
    financials: FinancialSnapshot,
    price_history: list | None = None,
    insider_cluster: InsiderCluster | None = None,
) -> SnowflakeScores | None:
    """
    LLM-based snowflake scoring. Uses the model's knowledge of the company and
    industry context for accurate, qualitative-aware scores. Falls back to
    compute_snowflake_scores() on failure.
    """
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from agent.llm_router import llm_router

        fin = financials
        rev_ttm   = f"${fin.revenue_ttm / 1e9:.2f}B" if fin.revenue_ttm else "N/A"
        rev_yoy   = f"{fin.revenue_growth_yoy * 100:.1f}%" if fin.revenue_growth_yoy is not None else "N/A"
        gm        = f"{fin.gross_margin * 100:.1f}%" if fin.gross_margin is not None else "N/A"
        net_m     = (
            f"{fin.net_income_ttm / fin.revenue_ttm * 100:.1f}%"
            if fin.net_income_ttm is not None and fin.revenue_ttm
            else "N/A"
        )
        pe        = f"{fin.pe_ratio:.1f}x" if fin.pe_ratio else "N/A (unprofitable)"
        ev        = f"{fin.ev_ebitda:.1f}x" if fin.ev_ebitda else "N/A"
        dte       = f"{fin.debt_to_equity:.2f}" if fin.debt_to_equity is not None else "N/A"
        mktcap    = f"${fin.market_cap / 1e9:.0f}B" if fin.market_cap else "N/A"

        # Momentum context from price history
        momentum_ctx = "No price data."
        if price_history and len(price_history) >= 50:
            closes = [p["close"] for p in price_history if p.get("close")]
            if closes:
                latest   = closes[-1]
                high_52w = max(closes[-min(252, len(closes)):])
                ma_len   = min(200, len(closes))
                ma       = sum(closes[-ma_len:]) / ma_len
                momentum_ctx = (
                    f"Price ${latest:.2f}, vs 52w-high {(latest/high_52w-1)*100:.1f}%, "
                    f"vs {ma_len}d-MA {(latest/ma-1)*100:.1f}%"
                )

        insider_ctx = "No unusual insider activity."
        if insider_cluster:
            insider_ctx = (
                f"{insider_cluster.insider_count} insiders bought "
                f"${insider_cluster.total_value_usd:,.0f} recently "
                f"(signal {insider_cluster.signal_strength:.2f}/1.0)"
            )

        prompt = f"""Score {company_name} ({ticker}) on 5 investment quality dimensions.

Financials:
  Revenue TTM: {rev_ttm}  |  Revenue Growth YoY: {rev_yoy}
  Gross Margin: {gm}       |  Net Margin: {net_m}
  P/E (TTM): {pe}          |  EV/EBITDA: {ev}
  Debt/Equity: {dte}       |  Market Cap: {mktcap}
  Momentum: {momentum_ctx}
  Insider activity: {insider_ctx}

Scoring guide (0 = worst, 10 = best):
  value       — Is the valuation reasonable for the quality/growth of this business?
                Premium valuations are OK if justified. Penalise if outrageously overvalued.
  growth      — Revenue and earnings growth trajectory and sustainability.
  health      — Balance sheet, cash flow, margin quality, debt sustainability.
  momentum    — Price trend quality. Use the price data above.
  smart_money — Insider and institutional conviction signal.

Important: use your knowledge of {ticker}'s competitive position, business model,
and industry. A high P/E alone does NOT mean low value if the business justifies it.

Respond with ONLY this JSON (no text, no markdown):
{{"value": X.X, "growth": X.X, "health": X.X, "momentum": X.X, "smart_money": X.X}}"""

        raw = await llm_router.complete_fast(
            prompt=prompt,
            system=(
                "You are a senior equity analyst. Score each dimension 0.0–10.0. "
                "Return only valid JSON, no explanation."
            ),
            max_tokens=80,
        )

        clean = raw.strip()
        if "```" in clean:
            clean = re.sub(r"```[a-z]*", "", clean).replace("```", "").strip()
        s, e = clean.find("{"), clean.rfind("}") + 1
        if s >= 0 and e > s:
            clean = clean[s:e]
        data = json.loads(clean)

        def _c(v):
            return round(max(0.0, min(10.0, float(v))), 2)

        return SnowflakeScores(
            value=_c(data["value"]),
            growth=_c(data["growth"]),
            health=_c(data["health"]),
            momentum=_c(data["momentum"]),
            smart_money=_c(data["smart_money"]),
        )
    except Exception as exc:
        logger.warning("LLM snowflake scoring failed for %s: %s", ticker, exc)
        return None


class PrecomputeService:
    def __init__(self, cache=None):
        from backend.services.data_fetcher import DataFetcher
        from backend.services.edgar import (
            compute_filing_diff,
            detect_insider_cluster,
            get_congressional_trades,
            get_institutional_ownership,
        )
        from backend.services.sentiment import get_full_sentiment
        from backend.services.vector_store import VectorStore

        self._cache = cache
        self._fetcher = DataFetcher(cache=cache)
        self._vector = VectorStore()
        self._compute_filing_diff = compute_filing_diff
        self._detect_insider_cluster = detect_insider_cluster
        self._get_congressional_trades = get_congressional_trades
        self._get_full_sentiment = get_full_sentiment
        self._get_institutional_ownership = lambda t: get_institutional_ownership(t, cache)

    async def run_full_pipeline(self, ticker: str) -> dict:
        start = time.time()
        summary: dict = {"ticker": ticker, "steps": {}}

        async def _step(name: str, coro):
            try:
                result = await coro
                summary["steps"][name] = "ok"
                return result
            except Exception as exc:
                logger.warning("Precompute step %s failed for %s: %s", name, ticker, exc)
                summary["steps"][name] = f"error: {exc}"
                return None

        financials, transcript, price_history, filing_diff, insider_cluster, cong_trades, sentiment, inst_ownership = (
            await asyncio.gather(
                _step("financials", self._fetcher.get_financials(ticker)),
                _step("transcript", self._fetcher.get_earnings_transcript(ticker)),
                _step("price_history", self._fetcher.get_price_history(ticker)),
                _step("filing_diff", self._compute_filing_diff(ticker)),
                _step("insider_cluster", self._detect_insider_cluster(ticker)),
                _step("congressional_trades", self._get_congressional_trades(ticker)),
                _step("sentiment", self._get_full_sentiment(ticker)),
                _step("institutional_ownership", self._get_institutional_ownership(ticker)),
            )
        )

        snowflake = compute_snowflake_scores(
            financials or FinancialSnapshot(),
            price_history or [],
            insider_cluster,
            None,
        )
        summary["steps"]["snowflake"] = "ok"

        if self._cache:
            cache_key_base = f"stock:{ticker}"
            from backend.services.cache import CacheTTL
            if financials:
                await self._cache.set(f"{cache_key_base}:financials", financials.model_dump(), CacheTTL.FINANCIALS)
            if transcript:
                await self._cache.set(f"{cache_key_base}:transcript", transcript, CacheTTL.EARNINGS_TRANSCRIPT)
            if price_history:
                await self._cache.set(f"{cache_key_base}:price_history", price_history, CacheTTL.INTRADAY_PRICES)
            if filing_diff:
                await self._cache.set(f"{cache_key_base}:filing_diff", filing_diff.model_dump(), CacheTTL.FILING_DIFFS)
            if insider_cluster:
                await self._cache.set(f"{cache_key_base}:insider_cluster", insider_cluster.model_dump(), CacheTTL.INSIDER_TRADES)
            if cong_trades:
                await self._cache.set(f"{cache_key_base}:congressional_trades", cong_trades, CacheTTL.SEC_FILINGS)
            if sentiment:
                await self._cache.set(f"{cache_key_base}:sentiment", sentiment.model_dump(), CacheTTL.SENTIMENT)
            if inst_ownership:
                await self._cache.set(f"{cache_key_base}:institutional_ownership", inst_ownership.model_dump(), CacheTTL.INSIDER_TRADES)
            await self._cache.set(f"{cache_key_base}:snowflake", snowflake.model_dump(), CacheTTL.PRECOMPUTED_REPORT)

            draft = StockReport(
                ticker=ticker,
                company_name=ticker,
                verdict="wait",
                verdict_confidence=0.5,
                plain_english_summary="Pre-computed draft — AI synthesis pending.",
                three_bulls=[],
                three_risks=[],
                snowflake_scores=snowflake,
                financials=financials or FinancialSnapshot(),
                generated_at=datetime.now(timezone.utc),
            )
            await self._cache.set(f"{cache_key_base}:report", draft.model_dump(), CacheTTL.PRECOMPUTED_REPORT)
            summary["steps"]["cache_draft"] = "ok"

        summary["elapsed"] = round(time.time() - start, 2)
        logger.info("Precomputed %s in %.2fs", ticker, summary["elapsed"])
        return summary

    async def run_all_tickers(self):
        sem = asyncio.Semaphore(5)

        async def _bounded(ticker: str):
            async with sem:
                return await self.run_full_pipeline(ticker)

        results = await asyncio.gather(*[_bounded(t) for t in PRECOMPUTE_TICKERS], return_exceptions=True)
        for ticker, res in zip(PRECOMPUTE_TICKERS, results):
            if isinstance(res, Exception):
                logger.error("Precompute failed for %s: %s", ticker, res)
