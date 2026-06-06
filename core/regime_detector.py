"""
core/regime_detector.py — Market Regime Detection Module ("Weather Sensor")

Detects the current market regime for each instrument using ATR-based
volatility ratios and EMA trend distance analysis. Results are persisted
into the `market_regimes_history` table inside data/frxbot_brain.db.

Classification Rules:
    HIGH_VOLATILITY : ATR_14 / ATR_100 > 1.5  (extreme volatility spike)
    TRENDING        : ratio <= 1.5, but price is stretching away from EMA_50
                      beyond 0.5% OR exceeding 1 standard deviation channel
    NORMAL          : all other conditions (range-bound / low-vol market)
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import pandas as pd
import numpy as np

# Add project root to path for standalone execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database_manager import DB_PATH, _db_lock, init_db

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Active forex & commodity symbols for regime scanning (excludes crypto)
# ──────────────────────────────────────────────────────────────────────
REGIME_SCAN_SYMBOLS = [
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY",
    "AUDUSD", "USDCAD", "USDCHF"
]

# ──────────────────────────────────────────────────────────────────────
# Regime Classification Thresholds
# ──────────────────────────────────────────────────────────────────────
HIGH_VOL_RATIO_THRESHOLD = 1.5   # ATR_14/ATR_100 above this → HIGH_VOLATILITY
TREND_DISTANCE_PCT       = 0.005 # 0.5% price distance from EMA_50
TREND_STD_MULTIPLIER     = 1.0   # Price beyond 1.0x StdDev channel → TRENDING


def detect_market_regime(
    symbol: str,
    timeframe_file_path: str
) -> Optional[Dict[str, Any]]:
    """
    Reads the static CSV file for a given symbol and classifies the
    current market regime using ATR volatility ratio and EMA trend analysis.

    Args:
        symbol: The instrument symbol (e.g. 'XAUUSD').
        timeframe_file_path: Absolute path to the H1 max-bars CSV file.

    Returns:
        A dictionary containing regime classification data:
            - symbol: str
            - regime: str ('HIGH_VOLATILITY' | 'TRENDING' | 'NORMAL')
            - volatility_ratio: float (ATR_14 / ATR_100)
            - atr_14: float
            - atr_100: float
            - std_dev: float (100-period rolling standard deviation of Close)
            - ema_50: float (latest EMA_50 value)
            - close: float (latest closing price)
        Returns None if the file is missing or data is insufficient.
    """
    # ── 1. Validate input file ────────────────────────────────────────
    if not os.path.exists(timeframe_file_path):
        print(f"[REGIME ERROR] Data file not found: {timeframe_file_path}")
        logger.error(f"Regime detection skipped — file missing: {timeframe_file_path}")
        return None

    try:
        df = pd.read_csv(timeframe_file_path)
    except Exception as e:
        print(f"[REGIME ERROR] Failed to read CSV for {symbol}: {e}")
        logger.error(f"CSV read error for {symbol}: {e}", exc_info=True)
        return None

    # Normalize time column and sort chronologically
    time_col = "time" if "time" in df.columns else df.columns[0]
    df["time"] = pd.to_datetime(df[time_col])
    df = df.sort_values("time").reset_index(drop=True)

    # Require at least 120 bars for the 100-period ATR to stabilize
    if len(df) < 120:
        print(f"[REGIME WARNING] Insufficient data for {symbol} ({len(df)} bars). Need >= 120.")
        return None

    # ── 2. Compute Indicators ─────────────────────────────────────────
    high = df["High"].astype(float)
    low  = df["Low"].astype(float)
    close = df["Close"].astype(float)

    # True Range components
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    # ATR_14: Short-term volatility (current conditions)
    atr_14 = tr.rolling(window=14).mean().iloc[-1]

    # ATR_100: Long-term historical baseline volatility
    atr_100 = tr.rolling(window=100).mean().iloc[-1]

    # Volatility Ratio
    if pd.isna(atr_14) or pd.isna(atr_100) or atr_100 == 0:
        print(f"[REGIME WARNING] ATR calculation returned invalid values for {symbol}.")
        return None

    volatility_ratio = atr_14 / atr_100

    # EMA_50: Trend direction anchor
    ema_50 = close.ewm(span=50, adjust=False).mean().iloc[-1]

    # 100-period rolling standard deviation of closing prices
    std_dev_100 = close.rolling(window=100).std().iloc[-1]

    # Latest closing price
    latest_close = float(close.iloc[-1])

    # ── 3. Classification Logic ───────────────────────────────────────
    if volatility_ratio > HIGH_VOL_RATIO_THRESHOLD:
        # Rule 1: Extreme volatility spike
        regime = "HIGH_VOLATILITY"
    else:
        # Calculate distance from EMA_50
        ema_distance = abs(latest_close - ema_50)
        pct_distance = ema_distance / ema_50 if ema_50 != 0 else 0.0

        # Rule 2: Trending — price is stretching away from EMA_50
        # Either percentage distance exceeds 0.5% threshold
        # OR price has breached 1x standard deviation channel from EMA_50
        is_pct_trending = pct_distance > TREND_DISTANCE_PCT
        is_std_trending = (
            not pd.isna(std_dev_100)
            and std_dev_100 > 0
            and ema_distance > (std_dev_100 * TREND_STD_MULTIPLIER)
        )

        if is_pct_trending or is_std_trending:
            regime = "TRENDING"
        else:
            # Rule 3: Default — low volatility, range-bound market
            regime = "NORMAL"

    # ── 4. Build result payload ───────────────────────────────────────
    result = {
        "symbol": symbol.upper(),
        "regime": regime,
        "volatility_ratio": round(float(volatility_ratio), 4),
        "atr_14": round(float(atr_14), 6),
        "atr_100": round(float(atr_100), 6),
        "std_dev": round(float(std_dev_100), 6) if not pd.isna(std_dev_100) else 0.0,
        "ema_50": round(float(ema_50), 6),
        "close": round(latest_close, 6),
    }

    return result


def save_regime_to_db(regime_result: Dict[str, Any]) -> bool:
    """
    Persists a regime detection result into the `market_regimes_history`
    table inside frxbot_brain.db.

    Inserts a new historical row each time it is called (append-only log),
    enabling time-series analysis of regime transitions.

    Args:
        regime_result: Dictionary returned by `detect_market_regime()`.

    Returns:
        True if the write succeeded, False otherwise.
    """
    with _db_lock:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                INSERT INTO market_regimes_history (
                    symbol, calculated_atr, standard_deviation,
                    market_state, timestamp
                ) VALUES (?, ?, ?, ?, ?);
            """, (
                regime_result["symbol"],
                regime_result["atr_14"],
                regime_result["std_dev"],
                regime_result["regime"],
                timestamp
            ))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(
                f"Failed to save regime for {regime_result.get('symbol')}: {e}",
                exc_info=True
            )
            return False


def run_regime_check_all_pairs() -> None:
    """
    Batch runner: loops through all 7 active forex/commodity symbols,
    detects the current market regime using H1 macro data, persists
    results into SQLite, and prints clean engineering logs.
    """
    # Ensure the database tables exist before writing
    init_db()

    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print("\n" + "=" * 60)
    print("     FRXBOT MARKET REGIME SCANNER — Jalur A")
    print("=" * 60)

    for symbol in REGIME_SCAN_SYMBOLS:
        csv_path = os.path.join(root_dir, "data", f"{symbol}_H1_max_bars.csv")

        result = detect_market_regime(symbol, csv_path)

        if result is None:
            print(f"[REGIME SKIP] {symbol} — could not compute regime (data issue).")
            continue

        saved = save_regime_to_db(result)

        status = "Saved to DB." if saved else "DB WRITE FAILED."
        print(
            f"[REGIME] {result['symbol']} detected as {result['regime']} "
            f"(Ratio: {result['volatility_ratio']:.2f} | "
            f"ATR14: {result['atr_14']:.6f} | "
            f"StdDev: {result['std_dev']:.6f}). {status}"
        )

    print("=" * 60)
    print("     Regime scan complete.")
    print("=" * 60 + "\n")


# ──────────────────────────────────────────────────────────────────────
# Standalone execution entry point
# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run_regime_check_all_pairs()
