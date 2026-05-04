from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse

from agent.stream_agent import stream_agent

agent_router = APIRouter()

# Imported at runtime — these live in Person 1's backend package
try:
    from backend.cache_manager import cache_manager
    from backend.precompute_service import precompute_service
    _BACKEND_AVAILABLE = True
except ImportError:
    _BACKEND_AVAILABLE = False
    cache_manager = None
    precompute_service = None


@agent_router.get("/api/stock/{ticker}/report/stream")
async def stream_stock_report(
    ticker: str, request: Request, background_tasks: BackgroundTasks
):
    ticker = ticker.upper()

    cached_data = None
    if _BACKEND_AVAILABLE and cache_manager:
        cached_data = await cache_manager.get(f"stock:{ticker}:precomputed")

    if not cached_data:
        if _BACKEND_AVAILABLE and precompute_service:
            background_tasks.add_task(precompute_service.run_full_pipeline, ticker)
        return JSONResponse(
            {"status": "building", "retry_after": 30},
            status_code=202,
        )

    return StreamingResponse(
        stream_agent.stream_report(ticker, cached_data),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@agent_router.post("/api/agent/synthesize")
async def synthesize(request: Request):
    body = await request.json()
    ticker = body.get("ticker", "").upper()
    cached_data = body.get("cached_data", {})

    if not ticker or not cached_data:
        return JSONResponse(
            {"error": "ticker and cached_data are required"},
            status_code=400,
        )

    from agent.orchestrator import StockReportOrchestrator
    report = await StockReportOrchestrator().generate_report(ticker, cached_data)
    return report.model_dump()
