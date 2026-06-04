import json
import logging
from typing import Dict, Any, Optional
from db.connection import get_db_connection

logger = logging.getLogger(__name__)

async def is_user_whitelisted(user_id: int) -> bool:
    """
    Checks if a user is in the whitelist and has an active status.

    Args:
        user_id: The Telegram User ID.

    Returns:
        True if user exists and is active, False otherwise.
    """
    query = """
        SELECT is_active 
        FROM whitelist_users 
        WHERE user_id = $1;
    """
    try:
        async with get_db_connection() as conn:
            is_active = await conn.fetchval(query, user_id)
            return bool(is_active)
    except Exception as e:
        logger.error(f"Error checking whitelist for user {user_id}: {str(e)}")
        return False


async def log_signal(
    user_id: int,
    pair: str,
    timeframe: str,
    direction: str,
    entry_price: float,
    sl_price: float,
    tp1_price: float,
    tp2_price: float,
    lot_size: float,
    atr_value: float,
    signal_source: str,
    ai_confidence: Optional[float] = None,
    ai_reasoning: Optional[str] = None
) -> Optional[str]:
    """
    Logs a generated signal to the signal_log table.

    Args:
        user_id: Telegram User ID.
        pair: Currency pair (e.g. "XAUUSD").
        timeframe: Signal timeframe (e.g. "H1").
        direction: Signal direction ("LONG" | "SHORT").
        entry_price: Recommended entry price.
        sl_price: Recommended stop loss price.
        tp1_price: Recommended take profit 1 price.
        tp2_price: Recommended take profit 2 price.
        lot_size: Recommended lot size.
        atr_value: Calculated ATR value.
        signal_source: Source of the signal ("PUSH" | "PULL").
        ai_confidence: Optional AI model confidence score.
        ai_reasoning: Optional reasoning behind the signal.

    Returns:
        The generated UUID of the log record as a string, or None if logging failed.
    """
    query = """
        INSERT INTO signal_log (
            user_id, pair, timeframe, direction, entry_price, sl_price, 
            tp1_price, tp2_price, lot_size, atr_value, signal_source, 
            ai_confidence, ai_reasoning, outcome
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, 'OPEN'
        ) RETURNING id;
    """
    try:
        async with get_db_connection() as conn:
            uuid_val = await conn.fetchval(
                query,
                user_id,
                pair,
                timeframe,
                direction.upper(),
                entry_price,
                sl_price,
                tp1_price,
                tp2_price,
                lot_size,
                atr_value,
                signal_source.upper(),
                ai_confidence,
                ai_reasoning
            )
            return str(uuid_val) if uuid_val else None
    except Exception as e:
        logger.error(f"Error logging signal for user {user_id} on {pair}: {str(e)}")
        return None


async def save_backtest_result(
    user_id: int,
    pair: str,
    timeframe: str,
    period_years: int,
    strategy_params: Dict[str, Any],
    win_rate: float,
    net_pnl_pct: float,
    max_drawdown: float,
    total_trades: int,
    winning_trades: int,
    losing_trades: int,
    avg_rrr: float,
    sharpe_ratio: float,
    sortino_ratio: float,
    raw_report_json: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Saves a backtest simulation report into the backtest_results table.

    Args:
        user_id: Telegram User ID of the initiator.
        pair: Currency pair.
        timeframe: Timeframe.
        period_years: Historical range of the backtest.
        strategy_params: Dict of parameters used (EMA, RSI, MACD bounds).
        win_rate: Win rate percentage.
        net_pnl_pct: Net PnL percentage return.
        max_drawdown: Maximum drawdown percentage.
        total_trades: Total trades executed.
        winning_trades: Number of winning trades.
        losing_trades: Number of losing trades.
        avg_rrr: Average Risk/Reward ratio.
        sharpe_ratio: Sharpe Ratio.
        sortino_ratio: Sortino Ratio.
        raw_report_json: Optional complete JSON output from vectorbt.

    Returns:
        The generated UUID of the backtest record as a string, or None if save failed.
    """
    query = """
        INSERT INTO backtest_results (
            user_id, pair, timeframe, period_years, strategy_params, 
            win_rate, net_pnl_pct, max_drawdown, total_trades, winning_trades, 
            losing_trades, avg_rrr, sharpe_ratio, sortino_ratio, raw_report_json
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
        ) RETURNING id;
    """
    try:
        # Convert dictionary settings to JSON strings for jsonb insertion
        params_json = json.dumps(strategy_params)
        report_json = json.dumps(raw_report_json) if raw_report_json else None

        async with get_db_connection() as conn:
            uuid_val = await conn.fetchval(
                query,
                user_id,
                pair,
                timeframe,
                period_years,
                params_json,
                win_rate,
                net_pnl_pct,
                max_drawdown,
                total_trades,
                winning_trades,
                losing_trades,
                avg_rrr,
                sharpe_ratio,
                sortino_ratio,
                report_json
            )
            return str(uuid_val) if uuid_val else None
    except Exception as e:
        logger.error(f"Error saving backtest results for user {user_id} on {pair}: {str(e)}")
        return None
