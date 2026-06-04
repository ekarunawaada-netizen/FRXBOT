import pytest
import pandas as pd
import numpy as np
from engines.risk_engine import RiskManagementEngine, RiskPackage

@pytest.fixture
def mock_ohlcv_data():
    """Generates mock OHLCV pandas DataFrame for testing."""
    np.random.seed(42)
    rows = 20
    data = {
        "High": np.random.uniform(1.0800, 1.0900, size=rows),
        "Low": np.random.uniform(1.0700, 1.0790, size=rows),
        "Close": np.random.uniform(1.0750, 1.0850, size=rows),
        "Open": np.random.uniform(1.0750, 1.0850, size=rows),
        "Volume": np.random.randint(1000, 5000, size=rows),
    }
    return pd.DataFrame(data)

@pytest.mark.asyncio
async def test_compute_atr(mock_ohlcv_data):
    engine = RiskManagementEngine()
    atr = await engine.compute_atr(mock_ohlcv_data, period=14)
    assert isinstance(atr, float)
    assert atr > 0.0

def test_compute_pip_value():
    engine = RiskManagementEngine()
    
    # 1. Direct Pair (EURUSD) - standard lot has $10 pip value
    pip_val_eurusd = engine.compute_pip_value("EURUSD", 1.0800)
    assert pytest.approx(pip_val_eurusd) == 10.0

    # 2. Indirect Pair (USDJPY) - standard lot has (0.01 / price) * 100k
    # At price 150.00: (0.01 / 150.00) * 100,000 = 6.6667
    pip_val_usdjpy = engine.compute_pip_value("USDJPY", 150.00)
    assert pytest.approx(pip_val_usdjpy, rel=1e-3) == 6.6667

    # 3. Gold (XAUUSD) - standard lot has 0.01 * 100 = 1.00
    pip_val_xauusd = engine.compute_pip_value("XAUUSD", 2300.00)
    assert pytest.approx(pip_val_xauusd) == 1.0

    # 4. Cross pair with custom quote rate (e.g. EURGBP)
    # Quote is GBP, if GBPUSD is 1.25 -> pip value is 0.0001 * 100,000 * 1.25 = 12.50
    pip_val_eurgbp = engine.compute_pip_value("EURGBP", 0.8500, quote_usd_rate=1.25)
    assert pytest.approx(pip_val_eurgbp) == 12.5

@pytest.mark.asyncio
async def test_calculate_long(mock_ohlcv_data):
    engine = RiskManagementEngine()
    
    # EURUSD Long signal
    result = await engine.calculate(
        pair="EURUSD",
        direction="LONG",
        entry_price=1.0800,
        ohlcv=mock_ohlcv_data,
        capital_usd=10000.0,
        risk_pct=1.0,  # 1% = $100 risk
        timeframe="H1"
    )
    
    assert isinstance(result, RiskPackage)
    assert result.pair == "EURUSD"
    assert result.direction == "LONG"
    assert result.entry_price == 1.0800
    assert result.sl_price < 1.0800
    assert result.tp1_price > 1.0800
    assert result.tp2_price > result.tp1_price
    assert result.risk_amount_usd == 100.0
    assert result.lot_size >= 0.01
    
    # Check proper precision (5 decimals for EURUSD)
    assert len(str(result.sl_price).split(".")[1]) <= 5

@pytest.mark.asyncio
async def test_calculate_short_jpy(mock_ohlcv_data):
    engine = RiskManagementEngine()
    
    # USDJPY Short signal
    result = await engine.calculate(
        pair="USDJPY",
        direction="SHORT",
        entry_price=155.50,
        ohlcv=mock_ohlcv_data,
        capital_usd=5000.0,
        risk_pct=2.0,  # 2% = $100 risk
        timeframe="H4"
    )
    
    assert isinstance(result, RiskPackage)
    assert result.pair == "USDJPY"
    assert result.direction == "SHORT"
    assert result.entry_price == 155.50
    assert result.sl_price > 155.50
    assert result.tp1_price < 155.50
    assert result.tp2_price < result.tp1_price
    assert result.risk_amount_usd == 100.0
    assert result.lot_size >= 0.01
    
    # Check proper JPY precision (2 decimals)
    assert len(str(result.sl_price).split(".")[1]) <= 2

@pytest.mark.asyncio
async def test_calculate_adaptive_multiplier(mock_ohlcv_data):
    engine = RiskManagementEngine()
    
    # 1. Gold (XAUUSD) in scalping mode: multiplier should be 2.2
    result_gold_scalping = await engine.calculate(
        pair="XAUUSD",
        direction="LONG",
        entry_price=2000.00,
        ohlcv=mock_ohlcv_data,
        capital_usd=5000.0,
        risk_pct=1.0,
        timeframe="M5",
        mode="scalping"
    )
    atr = await engine.compute_atr(mock_ohlcv_data, period=14)
    expected_dist_gold = atr * 2.2
    expected_tp2_gold = atr * 1.2
    # Use absolute tolerance because Gold prices are rounded to 2 decimals
    assert pytest.approx(abs(result_gold_scalping.entry_price - result_gold_scalping.sl_price), abs=0.01) == expected_dist_gold
    assert pytest.approx(abs(result_gold_scalping.tp2_price - result_gold_scalping.entry_price), abs=0.01) == expected_tp2_gold
    
    # 2. EURUSD in scalping mode: multiplier should be 1.5
    result_eur_scalping = await engine.calculate(
        pair="EURUSD",
        direction="LONG",
        entry_price=1.0800,
        ohlcv=mock_ohlcv_data,
        capital_usd=5000.0,
        risk_pct=1.0,
        timeframe="M5",
        mode="scalping"
    )
    expected_dist_eur = atr * 1.5
    assert pytest.approx(abs(result_eur_scalping.entry_price - result_eur_scalping.sl_price), rel=1e-3) == expected_dist_eur

    # 3. Gold in swing mode: multiplier should default to H1 (1.75)
    result_gold_swing = await engine.calculate(
        pair="XAUUSD",
        direction="LONG",
        entry_price=2000.00,
        ohlcv=mock_ohlcv_data,
        capital_usd=5000.0,
        risk_pct=1.0,
        timeframe="H1",
        mode="swing"
    )
    expected_dist_gold_swing = atr * 1.75
    assert pytest.approx(abs(result_gold_swing.entry_price - result_gold_swing.sl_price), abs=0.01) == expected_dist_gold_swing
