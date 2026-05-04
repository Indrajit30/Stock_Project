import asyncio
import logging
import os
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

    def _clamp(v: float) -> float:
        return max(0.0, min(10.0, v))

    def _safe(v, default=0.0):
        return float(v) if v is not None else default

    # Value score
    pe = _safe(financials.pe_ratio, 20.0)
    ev_ebitda = _safe(financials.ev_ebitda, 15.0)
    value_raw = (1 / max(pe, 1)) * 100 + (1 / max(ev_ebitda, 1)) * 80
    value = _clamp(value_raw)

    # Growth score based on revenue YoY growth
    rev_growth = _safe(getattr(financials, "revenue_growth_yoy", None), None)
    if rev_growth is None:
        growth = 5.0
    elif rev_growth > 0.25:
        growth = 9.0
    elif rev_growth > 0.15:
        growth = 7.5
    elif rev_growth > 0.05:
        growth = 6.0
    elif rev_growth > 0.0:
        growth = 5.0
    elif rev_growth > -0.05:
        growth = 3.5
    else:
        growth = 2.0
    growth = _clamp(growth)

    # Health score
    dte = _safe(financials.debt_to_equity, 1.0)
    health = _clamp(10.0 - dte * 2)

    # Momentum score
    if price_history and len(price_history) >= 200:
        closes = [p["close"] for p in price_history if p.get("close")]
        if closes:
            latest = closes[-1]
            high_52w = max(closes[-252:]) if len(closes) >= 252 else max(closes)
            ma_200 = sum(closes[-200:]) / 200
            vs_high = latest / high_52w if high_52w else 1.0
            vs_ma = latest / ma_200 if ma_200 else 1.0
            momentum = _clamp((vs_high * 0.4 + vs_ma * 0.6) * 10)
        else:
            momentum = 5.0
    else:
        momentum = 5.0

    # Smart money score
    insider_signal = insider_cluster.signal_strength if insider_cluster else 0.0
    super_signal = min(len(superinvestor.funds) / 5.0, 1.0) if superinvestor else 0.0
    smart_money = _clamp((insider_signal * 0.5 + super_signal * 0.5) * 10)

    return SnowflakeScores(
        value=round(value, 2),
        growth=round(growth, 2),
        health=round(health, 2),
        momentum=round(momentum, 2),
        smart_money=round(smart_money, 2),
    )


class PrecomputeService:
    def __init__(self, cache=None):
        from backend.services.data_fetcher import DataFetcher
        from backend.services.edgar import (
            compute_filing_diff,
            detect_insider_cluster,
            get_congressional_trades,
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

        financials, transcript, price_history, filing_diff, insider_cluster, cong_trades, sentiment = (
            await asyncio.gather(
                _step("financials", self._fetcher.get_financials(ticker)),
                _step("transcript", self._fetcher.get_earnings_transcript(ticker)),
                _step("price_history", self._fetcher.get_price_history(ticker)),
                _step("filing_diff", self._compute_filing_diff(ticker)),
                _step("insider_cluster", self._detect_insider_cluster(ticker)),
                _step("congressional_trades", self._get_congressional_trades(ticker)),
                _step("sentiment", self._get_full_sentiment(ticker)),
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
