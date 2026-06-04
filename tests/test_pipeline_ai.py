import pytest
import asyncio
import time
import pandas as pd
from unittest.mock import AsyncMock, patch, MagicMock
from data.price_fetcher import fetch_ohlcv_with_backoff
from data.news_fetcher import fetch_economic_calendar
from core.gemini_client import GeminiRateLimiter, GeminiAnalyseClient

@pytest.mark.asyncio
async def test_fetch_ohlcv_cache_and_fallback():
    # Test fallback to synthetic generator and caching
    # Call 1 (miss cache, generates synthetic)
    res1 = await fetch_ohlcv_with_backoff("EURUSD", "M15")
    assert isinstance(res1, dict)
    assert "df" in res1
    assert isinstance(res1["df"], pd.DataFrame)
    assert not res1["df"].empty
    assert "Close" in res1["df"].columns
    assert "h4_trend" in res1
    assert "highest_high_24h" in res1

    # Call 2 (hit cache, fast)
    with patch("data.price_fetcher._generate_synthetic_ohlcv") as mock_gen:
        res2 = await fetch_ohlcv_with_backoff("EURUSD", "M15")
        mock_gen.assert_not_called()
        assert res1["df"].equals(res2["df"])

@pytest.mark.asyncio
async def test_fetch_ohlcv_scalping():
    res = await fetch_ohlcv_with_backoff("EURUSD", mode="scalping")
    assert isinstance(res, dict)
    assert res["mode"] == "scalping"
    assert not res["df"].empty
    assert "Close" in res["df"].columns

@pytest.mark.asyncio
async def test_fetch_economic_calendar():
    events = await fetch_economic_calendar()
    assert isinstance(events, list)
    assert len(events) > 0
    for event in events:
        assert "source" in event
        assert "headline" in event
        assert "impact" in event
        assert "currency" in event
        assert "event_time" in event
        assert event["impact"] in {"HIGH", "MEDIUM", "LOW"}
        assert event["currency"] in {"USD", "EUR", "GBP"}

@pytest.mark.asyncio
async def test_gemini_rate_limiter():
    limiter = GeminiRateLimiter(rpm=60)  # 1 token per second
    
    # We should be able to acquire immediately
    start_time = time.monotonic()
    await limiter.acquire()
    await limiter.acquire()
    end_time = time.monotonic()
    # It should take almost 0 time since bucket starts full
    assert (end_time - start_time) < 0.1

@pytest.mark.asyncio
async def test_gemini_analyse_client_mock():
    # Force mock mode by removing settings key
    from core.config import settings
    orig_groq = settings.groq_api_key
    orig_gemini = settings.gemini_api_key
    settings.groq_api_key = None
    settings.gemini_api_key = None
    try:
        client = GeminiAnalyseClient()
        res = await client.analyze_market_news("We have NFP data showing stronger job gains.")
        
        assert res["sentiment"] == "BULLISH"
        assert res["bias"] == "LONG"
        assert "MOCK" in res["summary"]
        assert "order_type" in res
        assert res["entry_spot"] == 1.08500
    finally:
        settings.groq_api_key = orig_groq
        settings.gemini_api_key = orig_gemini
