import os
import asyncio
import random
import logging
from typing import Optional
import pandas as pd
import numpy as np
import httpx
from cachetools import TTLCache

from core.config import settings

logger = logging.getLogger(__name__)

# ── TTL Cache ─────────────────────────────────────────────────────────────────
_cache_short_tf = TTLCache(maxsize=100, ttl=300)   # 5 min for M1/M5/M15
_cache_long_tf = TTLCache(maxsize=100, ttl=1800)   # 30 min for H1/H4/D1

# ── MT5 Timeframe Mapping ─────────────────────────────────────────────────────
_MT5_TF_MAP = {}  # populated lazily after mt5 import

def _get_mt5_tf_map() -> dict:
    """Lazily build MT5 timeframe map (avoids import error if mt5 not available)."""
    global _MT5_TF_MAP
    if not _MT5_TF_MAP:
        try:
            import MetaTrader5 as mt5
            _MT5_TF_MAP = {
                "M1":  mt5.TIMEFRAME_M1,
                "M5":  mt5.TIMEFRAME_M5,
                "M15": mt5.TIMEFRAME_M15,
                "M30": mt5.TIMEFRAME_M30,
                "H1":  mt5.TIMEFRAME_H1,
                "H4":  mt5.TIMEFRAME_H4,
                "D1":  mt5.TIMEFRAME_D1,
            }
        except ImportError:
            pass
    return _MT5_TF_MAP

# ── Yahoo Finance Fallback Maps ──────────────────────────────────────────────
_YFINANCE_TICKER_MAP = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X",
    "NZDUSD": "NZDUSD=X",
    "EURGBP": "EURGBP=X",
    "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X",
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
}

_YF_INTERVAL_MAP = {
    "M1":  {"interval": "1m",  "period": "7d"},
    "M5":  {"interval": "5m",  "period": "60d"},
    "M15": {"interval": "15m", "period": "60d"},
    "M30": {"interval": "30m", "period": "60d"},
    "H1":  {"interval": "1h",  "period": "730d"},
    "H4":  {"interval": "1h",  "period": "730d"},
    "D1":  {"interval": "1d",  "period": "2y"},
}


def _get_cache_and_key(pair: str, tf: str) -> tuple[TTLCache, str]:
    """Determine cache bucket based on timeframe."""
    tf_upper = tf.upper()
    key = f"{pair.upper()}_{tf_upper}"
    is_large = any(x in tf_upper for x in ["H", "D", "W"]) or (
        tf_upper.startswith("M") and tf_upper not in {"M1", "M5", "M15"}
    )
    if is_large:
        return _cache_long_tf, key
    return _cache_short_tf, key


class RateLimitError(Exception):
    """Custom exception raised when an API rate limit is hit."""
    pass


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

async def fetch_ohlcv_with_backoff(pair: str, tf: str, retries: int = 3) -> pd.DataFrame:
    """
    Fetches OHLCV data with TTL caching and multi-provider waterfall:
    
      1. MetaTrader 5 (primary — live broker feed, requires MT5 terminal running)
      2. Yahoo Finance (secondary — free, no API key)
      3. Alpha Vantage (tertiary — if key configured)
      4. Synthetic data (last resort — offline/test environments)
    
    Returns:
        pd.DataFrame with columns: Open, High, Low, Close, Volume
    """
    cache, key = _get_cache_and_key(pair, tf)

    # Cache hit
    if key in cache:
        logger.info(f"Cache HIT for price data: {key}")
        return cache[key]

    # ── Provider 1: MetaTrader 5 ──
    try:
        df = await _fetch_from_mt5(pair, tf)
        if df is not None and not df.empty:
            cache[key] = df
            logger.info(f"Successfully fetched {len(df)} bars for {key} via MetaTrader 5.")
            return df
    except Exception as e:
        logger.warning(f"MT5 fetch failed for {key}: {e}. Falling through to Yahoo Finance.")

    # ── Provider 2: Yahoo Finance ──
    for attempt in range(retries):
        try:
            df = await _fetch_from_yfinance(pair, tf)
            if df is not None and not df.empty:
                cache[key] = df
                logger.info(f"Successfully fetched {len(df)} bars for {key} via Yahoo Finance.")
                return df
            else:
                logger.warning(f"Yahoo Finance returned empty data for {key}.")
                break
        except Exception as e:
            wait_time = (2 ** attempt) + random.uniform(0.1, 1.0)
            logger.warning(f"Yahoo Finance failed for {key}: {e}. Retrying in {wait_time:.2f}s ({attempt+1}/{retries})")
            await asyncio.sleep(wait_time)

    # ── Provider 3: Alpha Vantage ──
    if settings.alpha_vantage_key:
        try:
            logger.info(f"Attempting Alpha Vantage fallback for {key}...")
            df = await _fetch_from_alpha_vantage(pair, tf)
            if df is not None and not df.empty:
                cache[key] = df
                logger.info(f"Successfully fetched {len(df)} bars for {key} via Alpha Vantage.")
                return df
        except Exception as e:
            logger.error(f"Alpha Vantage fallback also failed for {key}: {e}")

    # ── Provider 4: Synthetic ──
    logger.error(f"All providers failed for {key}. Using synthetic data fallback.")
    df = _generate_synthetic_ohlcv(pair, tf)
    cache[key] = df
    return df


# ══════════════════════════════════════════════════════════════════════════════
# PROVIDER: MetaTrader 5
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_from_mt5(pair: str, tf: str, num_bars: int = 220) -> pd.DataFrame:
    """
    Fetches live OHLCV data from the MetaTrader 5 terminal.
    
    Requires:
      - MetaTrader5 Python package installed
      - MT5 terminal application running on the Windows desktop
      - The requested symbol available in the broker's market watch
    
    Runs the synchronous MT5 calls in a thread executor.
    """
    loop = asyncio.get_event_loop()

    def _mt5_download():
        import MetaTrader5 as mt5

        if not mt5.initialize():
            error = mt5.last_error()
            mt5.shutdown()
            raise ConnectionError(f"MT5 initialize() failed: {error}")

        try:
            tf_map = _get_mt5_tf_map()
            mt5_tf = tf_map.get(tf.upper())
            if mt5_tf is None:
                raise ValueError(f"Unsupported timeframe for MT5: {tf}")

            # Fetch bars
            rates = mt5.copy_rates_from_pos(pair, mt5_tf, 0, num_bars)
            if rates is None or len(rates) == 0:
                error = mt5.last_error()
                raise ValueError(f"MT5 returned no data for {pair} {tf}: {error}")

            # Convert structured numpy array to DataFrame
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df = df.set_index("time")

            # Rename MT5 columns to match our schema
            df = df.rename(columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "tick_volume": "Volume",
            })

            # Keep only required columns
            required = ["Open", "High", "Low", "Close", "Volume"]
            available = [c for c in required if c in df.columns]
            df = df[available]

            return df
        finally:
            mt5.shutdown()

    return await loop.run_in_executor(None, _mt5_download)


def compute_market_data_context(df: pd.DataFrame, pair: str) -> str:
    """
    Computes a human-readable market data context string from an OHLCV DataFrame.
    
    Includes:
      - Current price, session high/low
      - EMA 20/50 trend alignment
      - RSI (14-period)
      - MACD line vs signal
      - Last 5 candle OHLC summary
    
    This string is passed to the Groq AI agent for technical reasoning.
    """
    if df is None or df.empty or len(df) < 50:
        return "Insufficient market data for technical context."

    try:
        close = df["Close"].astype(float)
        high = df["High"].astype(float)
        low = df["Low"].astype(float)

        current_price = float(close.iloc[-1])
        session_high = float(high.iloc[-1])
        session_low = float(low.iloc[-1])

        # ── EMA 20 / 50 ──
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        ema20_val = float(ema20.iloc[-1])
        ema50_val = float(ema50.iloc[-1])
        ema_trend = "BULLISH (EMA20 > EMA50)" if ema20_val > ema50_val else "BEARISH (EMA20 < EMA50)"

        # ── RSI (14) ──
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0

        # ── MACD (12, 26, 9) ──
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_val = float(macd_line.iloc[-1])
        signal_val = float(signal_line.iloc[-1])
        macd_cross = "BULLISH (MACD > Signal)" if macd_val > signal_val else "BEARISH (MACD < Signal)"

        # ── Last 5 candles summary ──
        last5 = df.tail(5)
        candle_lines = []
        for idx, row in last5.iterrows():
            ts = idx.strftime("%Y-%m-%d %H:%M") if hasattr(idx, "strftime") else str(idx)
            candle_lines.append(
                f"  {ts} | O:{row['Open']:.2f} H:{row['High']:.2f} L:{row['Low']:.2f} C:{row['Close']:.2f}"
            )
        candles_str = "\n".join(candle_lines)

        # Price formatting
        fmt = ".2f" if current_price > 10 else ".5f"

        context = (
            f"── Live Market Data ({pair}) ──\n"
            f"Current Price: {current_price:{fmt}}\n"
            f"Session H/L: {session_high:{fmt}} / {session_low:{fmt}}\n"
            f"EMA(20): {ema20_val:{fmt}} | EMA(50): {ema50_val:{fmt}} → Trend: {ema_trend}\n"
            f"RSI(14): {rsi_val:.1f}\n"
            f"MACD: {macd_val:{fmt}} | Signal: {signal_val:{fmt}} → {macd_cross}\n"
            f"\nLast 5 Candles (OHLC):\n{candles_str}"
        )
        return context

    except Exception as e:
        logger.error(f"Error computing market data context: {e}")
        return f"Market data context computation failed: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# PROVIDER: Yahoo Finance
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_from_yfinance(pair: str, tf: str) -> pd.DataFrame:
    """
    Fetches OHLCV data from Yahoo Finance using the yfinance library.
    Runs the synchronous yfinance download in a thread executor.
    """
    import yfinance as yf

    ticker_symbol = _YFINANCE_TICKER_MAP.get(pair.upper())
    if not ticker_symbol:
        ticker_symbol = f"{pair.upper()}=X"

    logger.info(f"Resolved {pair} -> Yahoo Finance ticker: {ticker_symbol}")

    tf_upper = tf.upper()
    yf_params = _YF_INTERVAL_MAP.get(tf_upper, {"interval": "1h", "period": "730d"})

    loop = asyncio.get_event_loop()

    def _download():
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(
            period=yf_params["period"],
            interval=yf_params["interval"],
            auto_adjust=True,
        )
        return df

    df = await loop.run_in_executor(None, _download)

    if df is None or df.empty:
        return pd.DataFrame()

    required_cols = ["Open", "High", "Low", "Close", "Volume"]
    available_cols = [c for c in required_cols if c in df.columns]
    df = df[available_cols]

    if "Volume" in df.columns and (df["Volume"] == 0).all():
        df["Volume"] = 1000.0

    if tf_upper == "H4" and not df.empty:
        df = df.resample("4h").agg({
            "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum",
        }).dropna()

    if len(df) > 220:
        df = df.tail(220)

    return df


# ══════════════════════════════════════════════════════════════════════════════
# PROVIDER: Alpha Vantage
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_from_alpha_vantage(pair: str, tf: str) -> pd.DataFrame:
    """Fallback provider: Alpha Vantage (requires API key, 5 RPM free tier)."""
    api_key = settings.alpha_vantage_key
    if not api_key:
        raise ValueError("ALPHA_VANTAGE_KEY not configured.")

    interval_map = {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min", "H1": "60min"}
    interval = interval_map.get(tf.upper(), "60min")

    url = (
        f"https://www.alphavantage.co/query?function=FX_INTRADAY"
        f"&from_symbol={pair[:3]}&to_symbol={pair[3:]}"
        f"&interval={interval}&apikey={api_key}"
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

        if "Note" in data or "Information" in data:
            raise RateLimitError("Alpha Vantage rate limit reached")

        time_series_key = f"Time Series FX ({interval})"
        if time_series_key not in data:
            raise KeyError(f"Invalid response from Alpha Vantage API: {data}")

        time_series = data[time_series_key]
        rows = []
        for dt_str, values in time_series.items():
            rows.append({
                "Date": pd.to_datetime(dt_str),
                "Open": float(values["1. open"]),
                "High": float(values["2. high"]),
                "Low": float(values["3. low"]),
                "Close": float(values["4. close"]),
                "Volume": 1000.0,
            })

        df = pd.DataFrame(rows).set_index("Date").sort_index()
        return df


# ══════════════════════════════════════════════════════════════════════════════
# FALLBACK: Synthetic Data
# ══════════════════════════════════════════════════════════════════════════════

def _generate_synthetic_ohlcv(pair: str, tf: str) -> pd.DataFrame:
    """Generates realistic synthetic OHLCV bars for offline testing and fallback."""
    logger.info(f"Generating synthetic OHLCV data for {pair} ({tf})")

    np.random.seed(42)
    rows = 220
    start_price = 150.0 if "JPY" in pair else (2300.0 if pair.startswith("XAU") else 1.0800)

    close_prices = start_price + np.cumsum(np.random.normal(0, start_price * 0.001, size=rows))
    high_prices = close_prices + np.random.uniform(0.01, start_price * 0.002, size=rows)
    low_prices = close_prices - np.random.uniform(0.01, start_price * 0.002, size=rows)
    open_prices = close_prices + np.random.uniform(-start_price * 0.001, start_price * 0.001, size=rows)

    data = {
        "High": high_prices, "Low": low_prices, "Close": close_prices,
        "Open": open_prices, "Volume": np.random.uniform(1000, 5000, size=rows),
    }
    date_range = pd.date_range(end=pd.Timestamp.now(), periods=rows, freq="h")
    return pd.DataFrame(data, index=date_range)
