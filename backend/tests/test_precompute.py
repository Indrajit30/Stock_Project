import pytest


@pytest.mark.asyncio
async def test_run_full_pipeline_completes():
    from backend.services.precompute import PrecomputeService
    svc = PrecomputeService()
    result = await svc.run_full_pipeline("AAPL")
    assert "ticker" in result
    assert result["ticker"] == "AAPL"
    assert "elapsed" in result
