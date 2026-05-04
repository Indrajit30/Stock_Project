import pytest

from shared.schemas import FinancialSnapshot


@pytest.mark.asyncio
async def test_get_financials_returns_snapshot():
    from backend.services.data_fetcher import DataFetcher
    fetcher = DataFetcher()
    result = await fetcher.get_financials("AAPL")
    assert isinstance(result, FinancialSnapshot)


@pytest.mark.asyncio
async def test_get_price_history_returns_list():
    from backend.services.data_fetcher import DataFetcher
    fetcher = DataFetcher()
    result = await fetcher.get_price_history("AAPL", days=30)
    assert isinstance(result, list)
