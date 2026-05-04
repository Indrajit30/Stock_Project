import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

import httpx

from shared.schemas import FundEntry, SuperinvestorCluster

logger = logging.getLogger(__name__)

KNOWN_FUNDS: dict[str, str] = {
    "Berkshire Hathaway": "0001067983",
    "Bridgewater Associates": "0001350694",
    "Renaissance Technologies": "0001037389",
    "Two Sigma": "0001179392",
    "Citadel": "0001423298",
    "Point72": "0001352576",
    "Viking Global": "0001011116",
    "Coatue Management": "0001336528",
    "Tiger Global": "0001359486",
    "Lone Pine Capital": "0001061768",
    "Pershing Square": "0001336528",
    "Baupost Group": "0001061165",
    "Appaloosa Management": "0001102610",
    "Greenlight Capital": "0001079114",
    "Duquesne Family Office": "0001536411",
}

_cache: dict = {}
_CACHE_TTL_SECS = 86400  # 13F is quarterly; cache for 24h
_EDGAR_HEADERS = {"User-Agent": "StockResearchApp research@example.com"}


class SuperinvestorDetector:
    async def fetch_13f_holdings(
        self, fund_name: str, cik: str, quarter: str
    ) -> list[dict]:
        url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.get(url, headers=_EDGAR_HEADERS)

                if resp.status_code == 429:
                    logger.warning(f"EDGAR rate limit for {fund_name}, backing off 5s")
                    await asyncio.sleep(5)
                    continue

                resp.raise_for_status()
                data = resp.json()
                filings = data.get("filings", {}).get("recent", {})
                return self._extract_13f_filings(filings, fund_name, cik)

            except httpx.TimeoutException:
                logger.warning(f"Timeout fetching {fund_name} ({cik}), attempt {attempt+1}")
            except Exception as e:
                logger.warning(f"EDGAR fetch failed for {fund_name}: {e}")
                return []

        return []

    def _extract_13f_filings(
        self, filings: dict, fund_name: str, cik: str
    ) -> list[dict]:
        forms = filings.get("form", [])
        accessions = filings.get("accessionNumber", [])
        results = []
        for form, accession in zip(forms, accessions):
            if "13F" in str(form):
                results.append({
                    "fund_name": fund_name,
                    "cik": cik,
                    "accession": accession,
                    "form_type": form,
                    # Full XML parsing of the holdings table would go here in production.
                    # The EDGAR holdings XML is at:
                    # https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/primary-doc.xml
                })
        return results

    async def detect_cluster(
        self, ticker: str, quarter: str = None
    ) -> Optional[SuperinvestorCluster]:
        if quarter is None:
            now = datetime.utcnow()
            q = (now.month - 1) // 3
            quarter = f"{now.year}Q{q}" if q > 0 else f"{now.year - 1}Q4"

        cache_key = f"{ticker}:{quarter}"
        if cache_key in _cache:
            cached_at, result = _cache[cache_key]
            if time.monotonic() - cached_at < _CACHE_TTL_SECS:
                return result

        tasks = [
            self.fetch_13f_holdings(name, cik, quarter)
            for name, cik in KNOWN_FUNDS.items()
        ]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        fund_entries: list[FundEntry] = []
        for (fund_name, cik), result in zip(KNOWN_FUNDS.items(), all_results):
            if isinstance(result, Exception) or not result:
                continue
            for holding in result:
                if (
                    isinstance(holding, dict)
                    and holding.get("ticker", "").upper() == ticker.upper()
                ):
                    fund_entries.append(
                        FundEntry(
                            fund_name=fund_name,
                            cik=cik,
                            shares=holding.get("shares", 0),
                            value_usd=holding.get("value_usd", 0),
                            change_from_prior=holding.get("change_from_prior", 0),
                            pct_of_fund_aum=holding.get("pct_of_fund_aum"),
                        )
                    )

        # Cluster = 3+ funds both holding AND increasing position
        increased = [f for f in fund_entries if f.change_from_prior > 0]
        if len(increased) < 3:
            _cache[cache_key] = (time.monotonic(), None)
            return None

        conviction = self.score_conviction(fund_entries)
        strength = "strong" if conviction >= 7 else "moderate" if conviction >= 4 else "weak"

        cluster = SuperinvestorCluster(
            ticker=ticker,
            quarter=quarter,
            funds=fund_entries,
            conviction_score=conviction,
            cluster_strength=strength,
        )
        _cache[cache_key] = (time.monotonic(), cluster)
        return cluster

    def score_conviction(self, fund_entries: list[FundEntry]) -> float:
        if not fund_entries:
            return 0.0
        total = sum(
            (entry.pct_of_fund_aum or 0.0) * (2.0 if entry.change_from_prior > 0 else 1.0)
            for entry in fund_entries
        )
        raw = total / len(fund_entries)
        return min(raw * 10, 10.0)


superinvestor_detector = SuperinvestorDetector()
