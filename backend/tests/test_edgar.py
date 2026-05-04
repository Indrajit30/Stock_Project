import pytest

from shared.schemas import InsiderTrade


@pytest.mark.asyncio
async def test_get_insider_trades_returns_list():
    from backend.services.edgar import get_insider_trades
    trades = await get_insider_trades("AAPL", days_back=90)
    assert isinstance(trades, list)


@pytest.mark.asyncio
async def test_get_recent_filings_returns_list():
    from backend.services.edgar import get_recent_filings
    filings = await get_recent_filings("AAPL", form_types=["10-Q"])
    assert isinstance(filings, list)
