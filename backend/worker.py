import asyncio
import logging
import os

from arq import cron
from arq.connections import RedisSettings

logger = logging.getLogger(__name__)


async def run_full_pipeline_job(ctx, ticker: str):
    from backend.services.precompute import PrecomputeService
    svc = PrecomputeService()
    return await svc.run_full_pipeline(ticker)


async def run_all_tickers_job(ctx):
    from backend.services.precompute import PrecomputeService
    svc = PrecomputeService()
    await svc.run_all_tickers()


class WorkerSettings:
    functions = [run_full_pipeline_job, run_all_tickers_job]
    cron_jobs = [cron(run_all_tickers_job, hour=2, minute=0)]
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379"))
    max_jobs = 10
