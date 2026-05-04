import asyncio
import difflib
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx

from backend.services.data_fetcher import DataFetcher
from shared.schemas import (
    DiffSection,
    FilingDiff,
    InsiderCluster,
    InsiderTrade,
)

logger = logging.getLogger(__name__)

EDGAR_HEADERS = {
    "User-Agent": "StockResearchApp research@example.com",
    "Accept-Encoding": "gzip, deflate",
}
_RATE_LIMIT = asyncio.Semaphore(10)


async def _get(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    async with _RATE_LIMIT:
        resp = await client.get(url, headers=EDGAR_HEADERS, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp


async def get_recent_filings(ticker: str, form_types: list[str] | None = None) -> list[dict]:
    form_types = form_types or ["10-K", "10-Q", "8-K"]
    results = []
    try:
        identity = await DataFetcher().get_company_identity(ticker)
        cik = identity.get("cik")
        if not cik:
            return []

        async with httpx.AsyncClient() as client:
            resp = await _get(client, f"https://data.sec.gov/submissions/CIK{cik}.json")
            recent = resp.json().get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        cik_path = str(int(cik))

        for form, accession, primary_doc, filing_date, report_date in zip(
            forms, accession_numbers, primary_docs, filing_dates, report_dates
        ):
            if form not in form_types or not accession or not primary_doc:
                continue
            accession_path = accession.replace("-", "")
            results.append(
                {
                    "accession_number": accession,
                    "form_type": form,
                    "filed_date": report_date or filing_date,
                    "filing_date": filing_date,
                    "document_url": (
                        f"https://www.sec.gov/Archives/edgar/data/"
                        f"{cik_path}/{accession_path}/{primary_doc}"
                    ),
                }
            )
            if len(results) >= 10:
                break
    except Exception as exc:
        logger.warning("EDGAR submissions fetch failed for %s: %s", ticker, exc)
    return results


async def get_filing_text(accession_url: str) -> str:
    async with httpx.AsyncClient() as client:
        try:
            resp = await _get(client, accession_url)
            html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", resp.text)
            html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h[1-6]>", "\n", html)
            text = re.sub(r"<[^>]+>", " ", html)
            text = html_module_unescape(text)
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n\s+", "\n", text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            return text[:100_000]
        except Exception as exc:
            logger.warning("Failed to fetch filing text from %s: %s", accession_url, exc)
            return ""


async def get_insider_trades(ticker: str, days_back: int = 90) -> list[InsiderTrade]:
    start = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    url = (
        f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22"
        f"&forms=4&dateRange=custom&startdt={start}"
    )
    trades: list[InsiderTrade] = []
    async with httpx.AsyncClient() as client:
        try:
            resp = await _get(client, url)
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            for h in hits[:50]:
                src = h.get("_source", {})
                # Try to parse XML from the filing
                doc_url = src.get("file_date", "")
                trade = InsiderTrade(
                    name=src.get("display_names", ["Unknown"])[0] if src.get("display_names") else "Unknown",
                    role=src.get("entity_type", "Director"),
                    shares=0.0,
                    value_usd=0.0,
                    trade_date=datetime.fromisoformat(src.get("period_of_report", datetime.now().isoformat()[:10])),
                    is_10b5_plan=False,
                )
                trades.append(trade)
        except Exception as exc:
            logger.warning("Failed to get insider trades for %s: %s", ticker, exc)
    return trades


async def detect_insider_cluster(ticker: str) -> InsiderCluster | None:
    trades = await get_insider_trades(ticker, days_back=30)
    # Exclude 10b5 plan trades
    trades = [t for t in trades if not t.is_10b5_plan]

    if len(set(t.name for t in trades)) < 3:
        return None
    total_value = sum(t.value_usd for t in trades)
    if total_value < 100_000:
        return None

    role_weights = {"CEO": 3.0, "CFO": 2.0}
    weighted_sum = sum(role_weights.get(t.role.upper(), 1.0) for t in trades)
    signal_strength = min(weighted_sum / (len(trades) * 3.0), 1.0)

    return InsiderCluster(
        ticker=ticker,
        cluster_date=datetime.now(timezone.utc),
        total_value_usd=total_value,
        insider_count=len(set(t.name for t in trades)),
        insiders=trades,
        signal_strength=round(signal_strength, 3),
    )


async def get_congressional_trades(ticker: str) -> list[dict]:
    url = f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&forms=SD"
    trades = []
    async with httpx.AsyncClient() as client:
        try:
            resp = await _get(client, url)
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            for h in hits[:20]:
                src = h.get("_source", {})
                trades.append({
                    "politician_name": src.get("display_names", ["Unknown"])[0] if src.get("display_names") else "Unknown",
                    "chamber": "Unknown",
                    "party": "Unknown",
                    "transaction_type": "Purchase",
                    "amount_range": "Unknown",
                    "trade_date": src.get("period_of_report", ""),
                })
        except Exception as exc:
            logger.warning("Failed to get congressional trades for %s: %s", ticker, exc)
    return trades


async def get_recent_8k_items(ticker: str) -> list[dict]:
    url = (
        f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22"
        f"&forms=8-K&dateRange=custom&startdt=2023-01-01"
    )
    items = []
    async with httpx.AsyncClient() as client:
        try:
            resp = await _get(client, url)
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            for h in hits[:10]:
                src = h.get("_source", {})
                desc = src.get("file_description", "")
                alert_level = "NORMAL"
                item_numbers = []
                if "4.02" in desc:
                    alert_level = "HIGH_ALERT"
                    item_numbers.append("4.02")
                if "5.02" in desc:
                    alert_level = "HIGH_ALERT"
                    item_numbers.append("5.02")
                items.append({
                    "filed_date": src.get("period_of_report", ""),
                    "item_numbers": item_numbers,
                    "descriptions": [desc],
                    "alert_level": alert_level,
                })
        except Exception as exc:
            logger.warning("Failed to get 8-K items for %s: %s", ticker, exc)
    return items


async def compute_filing_diff(ticker: str, form_type: str = "10-Q") -> FilingDiff:
    filings = await get_recent_filings(ticker, form_types=[form_type])
    sections_of_interest = ["MD&A", "Risk Factors", "Financial Statements"]
    changed_sections: list[DiffSection] = []

    if len(filings) >= 2:
        try:
            text_a = await get_filing_text(filings[1]["document_url"])
            text_b = await get_filing_text(filings[0]["document_url"])

            for section in sections_of_interest:
                lines_a = _section_lines(text_a, section)
                lines_b = _section_lines(text_b, section)
                diff = list(difflib.unified_diff(lines_a, lines_b, lineterm=""))
                additions = [l[1:] for l in diff if l.startswith("+") and not l.startswith("+++")][:20]
                deletions = [l[1:] for l in diff if l.startswith("-") and not l.startswith("---")][:20]
                if not additions and not deletions:
                    additions = [
                        (
                            "No material line-level changes detected in this section between "
                            f"{filings[1]['filed_date']} and {filings[0]['filed_date']}."
                        )
                    ]
                changed_sections.append(
                    DiffSection(
                        section_name=section,
                        additions=additions,
                        deletions=deletions,
                        summary=f"{len(additions)} additions, {len(deletions)} deletions",
                    )
                )
        except Exception as exc:
            logger.warning("Filing diff failed for %s: %s", ticker, exc)

    current_period = filings[0]["filed_date"] if filings else "unknown"
    prior_period = filings[1]["filed_date"] if len(filings) > 1 else "unknown"

    return FilingDiff(
        ticker=ticker,
        filing_type=form_type,
        current_period=current_period,
        prior_period=prior_period,
        changed_sections=changed_sections,
    )


def _section_lines(text: str, section: str) -> list[str]:
    lowered = text.lower()
    aliases = {
        "MD&A": ["management's discussion", "management discussion", "item 2."],
        "Risk Factors": ["risk factors", "item 1a."],
        "Financial Statements": ["financial statements", "condensed consolidated"],
    }.get(section, [section.lower()])

    start = -1
    for alias in aliases:
        start = lowered.find(alias)
        if start != -1:
            break
    snippet = text[start:start + 25000] if start != -1 else text[:25000]

    sentences = re.split(r"(?<=[.;:])\s+", snippet)
    cleaned = []
    for sentence in sentences:
        line = re.sub(r"\s+", " ", sentence).strip()
        if 40 <= len(line) <= 500:
            cleaned.append(line)
        if len(cleaned) >= 120:
            break
    return cleaned


def html_module_unescape(text: str) -> str:
    return html.unescape(text).replace("\xa0", " ")
