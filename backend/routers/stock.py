import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import orjson
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _cache(request: Request):
    return request.app.state.cache


REPORT_CACHE_VERSION = "v2"
FILING_DIFF_CACHE_VERSION = "v2"


def _empty_filing_diff(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "filing_type": "10-Q",
        "current_period": "Data not available",
        "prior_period": "Data not available",
        "changed_sections": [],
    }


def _empty_sentiment(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "reddit_score": 0,
        "reddit_mention_count": 0,
        "top_posts": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _live_bundle(ticker: str, cache) -> dict:
    from backend.services.data_fetcher import DataFetcher
    from backend.services.precompute import compute_snowflake_scores

    fetcher = DataFetcher(cache=cache)
    identity = await fetcher.get_company_identity(ticker)
    financials = await fetcher.get_financials(ticker)

    async def _optional(name: str, coro, default):
        try:
            return await coro
        except Exception as exc:
            logger.warning("Live %s fetch failed for %s: %s", name, ticker, exc)
            return default

    price_history, transcript, news, filing_diff, insider_cluster, sentiment = (
        await asyncio.gather(
            _optional("price history", fetcher.get_price_history(ticker), []),
            _optional("transcript", fetcher.get_earnings_transcript(ticker), ""),
            _optional("news", fetcher.get_news(ticker), []),
            _optional(
                "filing diff",
                __import__("backend.services.edgar", fromlist=["compute_filing_diff"]).compute_filing_diff(ticker),
                _empty_filing_diff(ticker),
            ),
            _optional(
                "insider cluster",
                __import__("backend.services.edgar", fromlist=["detect_insider_cluster"]).detect_insider_cluster(ticker),
                None,
            ),
            _optional(
                "sentiment",
                __import__("backend.services.sentiment", fromlist=["get_full_sentiment"]).get_full_sentiment(ticker),
                _empty_sentiment(ticker),
            ),
        )
    )

    snowflake = compute_snowflake_scores(financials, price_history, insider_cluster, None)

    def dump(value):
        return value.model_dump() if hasattr(value, "model_dump") else value

    return {
        "company_name": identity.get("company_name") or f"{ticker} Corp.",
        "financials": dump(financials),
        "snowflake": dump(snowflake),
        "filing_diff": dump(filing_diff),
        "insider_cluster": dump(insider_cluster) if insider_cluster else None,
        "sentiment": dump(sentiment),
        "congressional_trades": [],
        "transcript": transcript or "",
        "filing_10q_text": "",
        "news": news or [],
    }


async def _cached_or_live(cache, ticker: str) -> dict:
    if not cache:
        return await _live_bundle(ticker, cache)

    bundle = await _live_bundle(ticker, cache)
    keys = {
        "financials": f"stock:{ticker}:financials",
        "snowflake": f"stock:{ticker}:snowflake",
        "filing_diff": f"stock:{ticker}:filing_diff:{FILING_DIFF_CACHE_VERSION}",
        "insider_cluster": f"stock:{ticker}:insider_cluster",
        "sentiment": f"stock:{ticker}:sentiment",
        "congressional_trades": f"stock:{ticker}:congressional_trades",
        "report": f"stock:{ticker}:report:{REPORT_CACHE_VERSION}",
        "transcript": f"stock:{ticker}:transcript",
        "filing_10q_text": f"stock:{ticker}:filing_10q_text",
        "news": f"stock:{ticker}:news",
    }
    for name, key in keys.items():
        cached = await cache.get(key)
        if cached is not None:
            bundle[name] = cached
    return bundle


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(jsonable_encoder(payload))}\n\n"


def _api_key_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


@router.get("/stock/{ticker}/report")
async def get_report(
    ticker: str,
    request: Request,
    background_tasks: BackgroundTasks,
    force_refresh: bool = Query(False),
):
    ticker = ticker.upper()
    cache = _cache(request)
    key = f"stock:{ticker}:report:{REPORT_CACHE_VERSION}"

    if not force_refresh and cache:
        cached = await cache.get(key)
        if cached:
            return JSONResponse(content=cached)

    if not force_refresh:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No generated report for {ticker}. Open /stock/{ticker} first to stream "
                "a live OpenAI-generated report."
            ),
        )

    job_id = str(uuid.uuid4())
    if cache:
        await cache.set(f"job:{job_id}:status", {"status": "queued", "ticker": ticker}, 3600)

    async def _run():
        from backend.services.precompute import PrecomputeService
        svc = PrecomputeService(cache=cache)
        await svc.run_full_pipeline(ticker)
        if cache:
            await cache.set(f"job:{job_id}:status", {"status": "done", "ticker": ticker}, 3600)

    background_tasks.add_task(_run)
    return JSONResponse(content={"job_id": job_id, "status": "queued"}, status_code=202)


@router.get("/stock/{ticker}/report/stream")
async def stream_report(ticker: str, request: Request):
    ticker = ticker.upper()
    cache = _cache(request)

    async def _generate() -> AsyncGenerator[str, None]:
        bundle = await _cached_or_live(cache, ticker)

        yield _sse({
            "event": "section_start",
            "section": "overview",
            "ticker": ticker,
            "company_name": bundle.get("company_name") or ticker,
        })

        static_sections = [
            ("financials", bundle["financials"]),
            ("snowflake", bundle["snowflake"]),
            ("sentiment", bundle["sentiment"]),
            ("filing_diff", bundle["filing_diff"]),
            ("insider_cluster", bundle["insider_cluster"]),
            ("congressional_trades", bundle["congressional_trades"]),
        ]
        for section, payload in static_sections:
            yield _sse({"event": "data", "section": section, "payload": payload})
            await asyncio.sleep(0.08)

        if not _api_key_configured():
            yield _sse(
                {
                    "event": "error",
                    "message": (
                        "OPENAI_API_KEY is not configured. Add it to "
                        "/Users/arunnair/Desktop/AI_llm_project/.env and restart the backend."
                    ),
                }
            )
            yield _sse({"event": "done", "ticker": ticker, "generated_at": datetime.now(timezone.utc)})
            return

        from agent.reasoning_trace import reasoning_tracer

        cached_data = {
            "financials": bundle["financials"],
            "snowflake_scores": bundle["snowflake"],
            "filing_diff": bundle["filing_diff"],
            "insider_cluster": bundle["insider_cluster"],
            "sentiment": bundle["sentiment"],
            "congressional_trades": bundle["congressional_trades"],
            "transcript": bundle.get("transcript", ""),
            "filing_10q_text": bundle.get("filing_10q_text", ""),
            "news": bundle.get("news", []),
            "ticker": ticker,
        }

        async for step in reasoning_tracer.trace_report_generation(ticker, cached_data):
            yield _sse({"event": "reasoning_step", **step.model_dump()})
            await asyncio.sleep(0.08)

        try:
            from agent.orchestrator import StockReportOrchestrator

            synthesized = await StockReportOrchestrator().generate_report(ticker, cached_data)
            report = synthesized.model_dump()
            report["company_name"] = bundle["company_name"]
        except Exception as exc:
            logger.exception("OpenAI synthesis failed for %s", ticker)
            yield _sse({"event": "error", "message": f"OpenAI synthesis failed: {exc}"})
            yield _sse({"event": "done", "ticker": ticker, "generated_at": datetime.now(timezone.utc)})
            return

        if cache:
            await cache.set(f"stock:{ticker}:report:{REPORT_CACHE_VERSION}", jsonable_encoder(report), 3600)
        yield _sse({"event": "data", "section": "verdict", "payload": report})
        yield _sse({"event": "done", "ticker": ticker, "generated_at": datetime.now(timezone.utc)})

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )


@router.post("/admin/precompute/run")
async def run_precompute(request: Request, background_tasks: BackgroundTasks):
    cache = _cache(request)

    async def _run():
        from backend.services.precompute import PRECOMPUTE_TICKERS, PrecomputeService

        svc = PrecomputeService(cache=cache)
        await asyncio.gather(
            *[svc.run_full_pipeline(ticker) for ticker in PRECOMPUTE_TICKERS[:50]],
            return_exceptions=True,
        )

    background_tasks.add_task(_run)
    return JSONResponse(content={"status": "queued"})


@router.get("/stock/{ticker}/filing-diff")
async def filing_diff(ticker: str, request: Request):
    ticker = ticker.upper()
    cache = _cache(request)
    key = f"stock:{ticker}:filing_diff:{FILING_DIFF_CACHE_VERSION}"
    if cache:
        cached = await cache.get(key)
        if cached:
            return JSONResponse(content=cached)
    from backend.services.edgar import compute_filing_diff
    diff = await compute_filing_diff(ticker)
    if cache:
        from backend.services.cache import CacheTTL
        await cache.set(key, diff.model_dump(), CacheTTL.FILING_DIFFS)
    return JSONResponse(content=diff.model_dump())


@router.get("/stock/{ticker}/insider-cluster")
async def insider_cluster(ticker: str, request: Request):
    ticker = ticker.upper()
    cache = _cache(request)
    key = f"stock:{ticker}:insider_cluster"
    if cache:
        cached = await cache.get(key)
        if cached:
            return JSONResponse(content=cached)
    from backend.services.edgar import detect_insider_cluster
    cluster = await detect_insider_cluster(ticker)
    if cache:
        from backend.services.cache import CacheTTL
        await cache.set(key, cluster.model_dump() if cluster else None, CacheTTL.INSIDER_TRADES)
    return JSONResponse(content=cluster.model_dump() if cluster else None)


@router.get("/stock/{ticker}/congressional-trades")
async def congressional_trades(ticker: str, request: Request):
    ticker = ticker.upper()
    cache = _cache(request)
    key = f"stock:{ticker}:congressional_trades"
    if cache:
        cached = await cache.get(key)
        if cached:
            return JSONResponse(content=cached)
    from backend.services.edgar import get_congressional_trades
    trades = await get_congressional_trades(ticker)
    if cache:
        from backend.services.cache import CacheTTL
        await cache.set(key, trades, CacheTTL.SEC_FILINGS)
    return JSONResponse(content=trades)


@router.get("/stock/{ticker}/sentiment")
async def sentiment(ticker: str, request: Request):
    ticker = ticker.upper()
    cache = _cache(request)
    key = f"stock:{ticker}:sentiment"
    if cache:
        cached = await cache.get(key)
        if cached:
            return JSONResponse(content=cached)
    from backend.services.sentiment import get_full_sentiment
    pulse = await get_full_sentiment(ticker)
    if cache:
        from backend.services.cache import CacheTTL
        await cache.set(key, pulse.model_dump(), CacheTTL.SENTIMENT)
    return JSONResponse(content=pulse.model_dump())


@router.get("/stock/{ticker}/snowflake")
async def snowflake(ticker: str, request: Request):
    ticker = ticker.upper()
    cache = _cache(request)
    key = f"stock:{ticker}:snowflake"
    if cache:
        cached = await cache.get(key)
        if cached:
            return JSONResponse(content=cached)
    return JSONResponse(content=None)


@router.get("/stock/{ticker}/price-history")
async def price_history(ticker: str, request: Request, days: int = Query(365)):
    ticker = ticker.upper()
    cache = _cache(request)
    key = f"stock:{ticker}:price_history"
    if cache:
        cached = await cache.get(key)
        if cached:
            return JSONResponse(content=cached)
    from backend.services.data_fetcher import DataFetcher
    fetcher = DataFetcher(cache=cache)
    history = await fetcher.get_price_history(ticker, days=days)
    if cache:
        from backend.services.cache import CacheTTL
        await cache.set(key, history, CacheTTL.INTRADAY_PRICES)
    return JSONResponse(content=history)


@router.get("/jobs/{job_id}/status")
async def job_status(job_id: str, request: Request):
    cache = _cache(request)
    if cache:
        status = await cache.get(f"job:{job_id}:status")
        if status:
            return JSONResponse(content=status)
    return JSONResponse(content={"status": "not_found"}, status_code=404)
