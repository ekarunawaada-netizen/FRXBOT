import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from db.queries import is_user_whitelisted, log_signal, save_backtest_result

@pytest.mark.asyncio
@patch("db.queries.get_db_connection")
async def test_is_user_whitelisted(mock_get_conn):
    # Mocking the connection and cursor/fetchval
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = True
    
    # Mocking the async context manager
    mock_context_manager = MagicMock()
    mock_context_manager.__aenter__.return_value = mock_conn
    mock_get_conn.return_value = mock_context_manager

    # Call function
    res = await is_user_whitelisted(12345)
    
    assert res is True
    mock_conn.fetchval.assert_called_once()
    assert "whitelist_users" in mock_conn.fetchval.call_args[0][0]


@pytest.mark.asyncio
@patch("db.queries.get_db_connection")
async def test_log_signal(mock_get_conn):
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "some-uuid-string"
    
    mock_context_manager = MagicMock()
    mock_context_manager.__aenter__.return_value = mock_conn
    mock_get_conn.return_value = mock_context_manager

    res = await log_signal(
        user_id=123,
        pair="EURUSD",
        timeframe="H1",
        direction="LONG",
        entry_price=1.0800,
        sl_price=1.0750,
        tp1_price=1.0875,
        tp2_price=1.0900,
        lot_size=0.1,
        atr_value=0.0015,
        signal_source="PUSH"
    )

    assert res == "some-uuid-string"
    mock_conn.fetchval.assert_called_once()
    assert "signal_log" in mock_conn.fetchval.call_args[0][0]


@pytest.mark.asyncio
@patch("db.queries.get_db_connection")
async def test_save_backtest_result(mock_get_conn):
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "backtest-uuid"
    
    mock_context_manager = MagicMock()
    mock_context_manager.__aenter__.return_value = mock_conn
    mock_get_conn.return_value = mock_context_manager

    res = await save_backtest_result(
        user_id=123,
        pair="GBPUSD",
        timeframe="M15",
        period_years=2,
        strategy_params={"ema_fast": 20, "ema_slow": 50},
        win_rate=55.5,
        net_pnl_pct=25.0,
        max_drawdown=5.0,
        total_trades=100,
        winning_trades=55,
        losing_trades=45,
        avg_rrr=1.5,
        sharpe_ratio=1.8,
        sortino_ratio=2.1
    )

    assert res == "backtest-uuid"
    mock_conn.fetchval.assert_called_once()
    assert "backtest_results" in mock_conn.fetchval.call_args[0][0]
