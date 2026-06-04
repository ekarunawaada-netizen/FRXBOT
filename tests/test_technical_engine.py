import pytest
import pandas as pd
import numpy as np
from engines.technical_engine import TechnicalEngine

@pytest.fixture
def mock_large_ohlcv_data():
    """Generates mock large OHLCV pandas DataFrame for testing (at least 210 rows)."""
    np.random.seed(42)
    rows = 220
    # Simulate a gentle trend
    close_prices = 100.0 + np.cumsum(np.random.normal(0.1, 0.5, size=rows))
    high_prices = close_prices + np.random.uniform(0.1, 1.0, size=rows)
    low_prices = close_prices - np.random.uniform(0.1, 1.0, size=rows)
    open_prices = close_prices + np.random.uniform(-0.5, 0.5, size=rows)
    
    data = {
        "High": high_prices,
        "Low": low_prices,
        "Close": close_prices,
        "Open": open_prices,
        "Volume": np.random.randint(1000, 5000, size=rows),
    }
    # Create datetime index
    date_range = pd.date_range(start="2026-01-01", periods=rows, freq="h")
    return pd.DataFrame(data, index=date_range)

@pytest.mark.asyncio
async def test_detect_market_regime(mock_large_ohlcv_data):
    engine = TechnicalEngine()
    regime = await engine.detect_market_regime(mock_large_ohlcv_data)
    assert regime in {"TRENDING", "RANGING", "NORMAL"}

@pytest.mark.asyncio
async def test_calculate_snr_swing(mock_large_ohlcv_data):
    engine = TechnicalEngine()
    result = await engine.calculate_snr(mock_large_ohlcv_data, mode="swing")
    
    assert "supports" in result
    assert "resistances" in result
    assert result["method"] == "local_extrema"
    assert isinstance(result["supports"], list)
    assert isinstance(result["resistances"], list)

@pytest.mark.asyncio
async def test_calculate_snr_scalping(mock_large_ohlcv_data):
    engine = TechnicalEngine()
    result = await engine.calculate_snr(mock_large_ohlcv_data, mode="scalping")
    
    assert "pivot" in result
    assert "supports" in result
    assert "resistances" in result
    assert result["method"] == "fibonacci_pivots"
    assert len(result["supports"]) == 3
    assert len(result["resistances"]) == 3

@pytest.mark.asyncio
async def test_generate_technical_bias(mock_large_ohlcv_data):
    engine = TechnicalEngine()
    result = await engine.generate_technical_bias(mock_large_ohlcv_data, mode="swing")
    
    assert "direction" in result
    assert "confluence_score" in result
    assert "reason" in result
    assert result["direction"] in {"LONG", "SHORT", "WAIT"}
    assert 0.0 <= result["confluence_score"] <= 100.0
    assert isinstance(result["reason"], str)
