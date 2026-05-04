import asyncio
import logging
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import httpx

from shared.schemas import FinancialSnapshot

logger = logging.getLogger(__name__)

PRECOMPUTE_TICKERS = [
    t.strip().upper()
    for t in os.getenv(
        "PRECOMPUTE_TICKERS",
        "AAPL,MSFT,GOOGL,AMZN,META,NVDA,TSLA,JPM,JNJ,V",
    ).split(",")
    if t.strip()
]

SEC_HEADERS = {
    "User-Agent": os.getenv(
        "SEC_USER_AGENT",
        "StockResearchApp contact@example.com",
    )
}

def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _latest_usd_fact(facts: dict, tags: list[str]) -> float | None:
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    candidates: list[dict] = []
    for tag in tags:
        units = us_gaap.get(tag, {}).get("units", {})
        values = units.get("USD") or units.get("shares") or []
        for item in values:
            val = _num(item.get("val"))
            if val is None:
                continue
            candidates.append(
                {
                    "val": val,
                    "end": item.get("end") or "",
                    "filed": item.get("filed") or "",
                    "form": item.get("form") or "",
                    "frame": item.get("frame") or "",
                }
            )
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item["end"], item["filed"], item["form"]), reverse=True)
    return candidates[0]["val"]


def _ttm_usd_fact(facts: dict, tags: list[str]) -> float | None:
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    by_frame: dict[str, dict] = {}
    for tag in tags:
        values = us_gaap.get(tag, {}).get("units", {}).get("USD") or []
        for item in values:
            frame = item.get("frame") or ""
            if "Q" not in frame:
                continue
            val = _num(item.get("val"))
            if val is None:
                continue
            current = by_frame.get(frame)
            if current is None or (item.get("filed") or "") > current.get("filed", ""):
                by_frame[frame] = {"val": val, "end": item.get("end") or "", "filed": item.get("filed") or ""}

    quarters = sorted(by_frame.values(), key=lambda item: (item["end"], item["filed"]), reverse=True)
    if len(quarters) >= 4:
        return sum(item["val"] for item in quarters[:4])
    return _latest_usd_fact(facts, tags)


def _prior_year_ttm_usd_fact(facts: dict, tags: list[str]) -> float | None:
    """Sum of quarters 5-8 (the prior-year TTM window) for YoY growth calculation."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    by_frame: dict[str, dict] = {}
    for tag in tags:
        values = us_gaap.get(tag, {}).get("units", {}).get("USD") or []
        for item in values:
            frame = item.get("frame") or ""
            if "Q" not in frame:
                continue
            val = _num(item.get("val"))
            if val is None:
                continue
            current = by_frame.get(frame)
            if current is None or (item.get("filed") or "") > current.get("filed", ""):
                by_frame[frame] = {"val": val, "end": item.get("end") or "", "filed": item.get("filed") or ""}
    quarters = sorted(by_frame.values(), key=lambda item: (item["end"], item["filed"]), reverse=True)
    if len(quarters) >= 8:
        return sum(item["val"] for item in quarters[4:8])
    return None


@lru_cache(maxsize=1)
def _empty_ticker_map_marker() -> str:
    return "uncached"


class DataFetcher:
    def __init__(self, cache=None):
        self._cache = cache

    async def _get_json(self, url: str, headers: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()

    async def _get_text(self, url: str, headers: dict | None = None) -> str:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text

    async def get_ticker_map(self) -> dict[str, dict]:
        if self._cache:
            cached = await self._cache.get("sec:ticker_map")
            if cached:
                return cached

        data = await self._get_json("https://www.sec.gov/files/company_tickers.json", SEC_HEADERS)
        mapped = {
            row["ticker"].upper(): {
                "cik": str(row["cik_str"]).zfill(10),
                "company_name": row["title"],
            }
            for row in data.values()
        }
        if self._cache:
            await self._cache.set("sec:ticker_map", mapped, 24 * 60 * 60)
        return mapped

    async def get_company_identity(self, ticker: str) -> dict:
        ticker = ticker.upper()
        mapping = await self.get_ticker_map()
        return mapping.get(ticker, {"cik": None, "company_name": f"{ticker} Corp."})

    async def get_company_facts(self, ticker: str) -> dict:
        ticker = ticker.upper()
        if self._cache:
            cached = await self._cache.get(f"sec:{ticker}:companyfacts")
            if cached:
                return cached

        identity = await self.get_company_identity(ticker)
        cik = identity.get("cik")
        if not cik:
            raise ValueError(f"No SEC CIK found for ticker {ticker}")

        facts = await self._get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", SEC_HEADERS)
        facts["_identity"] = identity
        if self._cache:
            await self._cache.set(f"sec:{ticker}:companyfacts", facts, 6 * 60 * 60)
        return facts

    async def get_company_submissions(self, ticker: str) -> dict:
        """Fetch SEC submissions JSON which contains SIC/industry metadata."""
        ticker = ticker.upper()
        if self._cache:
            cached = await self._cache.get(f"sec:{ticker}:submissions")
            if cached:
                return cached
        identity = await self.get_company_identity(ticker)
        cik = identity.get("cik")
        if not cik:
            return {}
        try:
            data = await self._get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", SEC_HEADERS)
            if self._cache:
                await self._cache.set(f"sec:{ticker}:submissions", data, 24 * 60 * 60)
            return data
        except Exception as exc:
            logger.warning("Failed to fetch SEC submissions for %s: %s", ticker, exc)
            return {}

    async def _yfinance_info(self, ticker: str) -> dict:
        """Fetch yfinance info dict in a thread pool (yfinance is synchronous)."""
        if self._cache:
            cached = await self._cache.get(f"yf:{ticker}:info")
            if cached:
                return cached
        try:
            import yfinance as yf
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: yf.Ticker(ticker).info)
            result = info or {}
            if self._cache and result:
                await self._cache.set(f"yf:{ticker}:info", result, 6 * 60 * 60)
            return result
        except Exception as exc:
            logger.warning("yfinance info fetch failed for %s: %s", ticker, exc)
            return {}

    async def get_financials(self, ticker: str) -> FinancialSnapshot:
        revenue_tags = [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
        ]

        results = await asyncio.gather(
            self.get_company_facts(ticker),
            self.get_company_submissions(ticker),
            self._yfinance_info(ticker),
            return_exceptions=True,
        )
        facts = results[0]
        if isinstance(facts, Exception):
            raise facts
        submissions = results[1] if not isinstance(results[1], Exception) else {}
        yf_info: dict = results[2] if not isinstance(results[2], Exception) else {}

        # SEC XBRL: income + balance sheet fundamentals (most accurate for TTM)
        revenue = _ttm_usd_fact(facts, revenue_tags)
        net_income = _ttm_usd_fact(facts, ["NetIncomeLoss", "ProfitLoss"])
        gross_profit = _ttm_usd_fact(facts, ["GrossProfit"])
        liabilities = _latest_usd_fact(facts, ["Liabilities"])
        equity = _latest_usd_fact(
            facts,
            [
                "StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            ],
        )

        gross_margin_sec = gross_profit / revenue if gross_profit is not None and revenue else None
        debt_to_equity = liabilities / equity if liabilities is not None and equity else None

        # yfinance: market-based metrics (price, multiples, industry)
        market_cap = _num(yf_info.get("marketCap"))
        pe_ratio = _num(yf_info.get("trailingPE"))
        ev_ebitda = _num(yf_info.get("enterpriseToEbitda"))
        gross_margin_yf = _num(yf_info.get("grossMargins"))
        # Prefer SEC gross margin when available (more precise), fall back to yfinance
        gross_margin = gross_margin_sec if gross_margin_sec is not None else gross_margin_yf

        # Industry: prefer yfinance (more specific) over SEC SIC description
        sic_description = (submissions or {}).get("sicDescription")
        industry = yf_info.get("industry") or sic_description or None
        sector = yf_info.get("sector") or sic_description or None

        # Revenue growth YoY (TTM vs prior-year TTM from SEC)
        revenue_growth_yoy: float | None = None
        prior_revenue = _prior_year_ttm_usd_fact(facts, revenue_tags)
        if revenue and prior_revenue and prior_revenue > 0:
            revenue_growth_yoy = round((revenue - prior_revenue) / prior_revenue, 4)

        # Use yfinance revenue as fallback if SEC TTM failed
        if revenue is None:
            revenue = _num(yf_info.get("totalRevenue"))
        if net_income is None:
            net_income = _num(yf_info.get("netIncomeToCommon"))

        return FinancialSnapshot(
            revenue_ttm=revenue,
            net_income_ttm=net_income,
            gross_margin=gross_margin,
            pe_ratio=pe_ratio,
            ev_ebitda=ev_ebitda,
            debt_to_equity=debt_to_equity,
            market_cap=market_cap,
            sector=sector,
            industry=industry,
            revenue_growth_yoy=revenue_growth_yoy,
        )

    async def get_price_history(self, ticker: str, days: int = 365) -> list[dict]:
        """Fetch OHLCV price history via yfinance."""
        if self._cache:
            cached = await self._cache.get(f"yf:{ticker}:price:{days}")
            if cached:
                return cached
        try:
            import yfinance as yf
            from datetime import datetime as dt, timedelta
            loop = asyncio.get_event_loop()

            def _fetch():
                end = dt.today()
                start = end - timedelta(days=days + 30)
                hist = yf.Ticker(ticker).history(
                    start=start.strftime("%Y-%m-%d"),
                    end=end.strftime("%Y-%m-%d"),
                )
                if hist.empty:
                    return []
                rows = []
                for idx, row in hist.iterrows():
                    rows.append({
                        "date": str(idx)[:10],
                        "open": float(row.get("Open") or 0),
                        "high": float(row.get("High") or 0),
                        "low": float(row.get("Low") or 0),
                        "close": float(row.get("Close") or 0),
                        "volume": int(row.get("Volume") or 0),
                    })
                return rows[-days:]

            result = await loop.run_in_executor(None, _fetch)
            if self._cache and result:
                await self._cache.set(f"yf:{ticker}:price:{days}", result, 60 * 60)
            return result
        except Exception as exc:
            logger.warning("yfinance price history failed for %s: %s", ticker, exc)
            return []

    async def get_earnings_transcript(self, ticker: str) -> str:
        return ""

    async def get_news(self, ticker: str, limit: int = 10) -> list[dict]:
        return []

    async def get_revenue_yoy(self, ticker: str) -> float | None:
        return None

    async def get_peer_tickers(self, ticker: str) -> list[str]:
        raise RuntimeError("Peer selection is generated by OpenAI in backend.routers.peers")

    async def get_batch_financials(self, tickers: list[str]) -> dict[str, FinancialSnapshot]:
        results = await asyncio.gather(
            *[self.get_financials(t.upper()) for t in tickers],
            return_exceptions=True,
        )
        out: dict[str, FinancialSnapshot] = {}
        for ticker, res in zip(tickers, results):
            ticker = ticker.upper()
            if isinstance(res, Exception):
                logger.warning("Failed to fetch SEC financials for %s: %s", ticker, res)
            else:
                out[ticker] = res
        return out
