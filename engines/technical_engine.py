import logging
from typing import Dict, Any, List
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)

class TechnicalEngine:
    """Engine responsible for calculating market regimes, support/resistance levels, and technical bias."""

    def __init__(self):
        pass

    async def detect_market_regime(self, df: pd.DataFrame) -> str:
        """
        Detects the current market regime (TRENDING, RANGING, or NORMAL) using ADX and EMA.

        Args:
            df: pd.DataFrame with OHLCV data.

        Returns:
            Market regime string: "TRENDING", "RANGING", or "NORMAL".
        """
        if df.empty or len(df) < 200:
            logger.warning("Insufficient data to detect market regime. Defaulting to NORMAL.")
            return "NORMAL"

        try:
            # Clean columns names for pandas_ta
            df_cleaned = df.rename(columns={c: c.capitalize() for c in df.columns})

            # Calculate ADX (14)
            adx_df = ta.adx(
                high=df_cleaned["High"],
                low=df_cleaned["Low"],
                close=df_cleaned["Close"],
                length=14
            )
            if adx_df is None or adx_df.empty:
                return "NORMAL"

            # ADX column name in pandas_ta is typically ADX_14
            adx_col = [col for col in adx_df.columns if "ADX" in col]
            if not adx_col:
                return "NORMAL"

            current_adx = adx_df[adx_col[0]].iloc[-1]

            if pd.isna(current_adx):
                return "NORMAL"

            if current_adx > 25:
                return "TRENDING"
            elif current_adx < 20:
                return "RANGING"
            else:
                return "NORMAL"
        except Exception as e:
            logger.error(f"Error in detect_market_regime: {str(e)}")
            return "NORMAL"

    async def calculate_snr(self, df: pd.DataFrame, mode: str) -> Dict[str, Any]:
        """
        Calculates Support and Resistance levels based on the mode (swing or scalping).

        Args:
            df: pd.DataFrame containing historical OHLCV data.
            mode: 'swing' or 'scalping'.

        Returns:
            Dict containing calculated support and resistance levels.
        """
        mode_lower = mode.lower()
        if mode_lower not in {"swing", "scalping"}:
            raise ValueError(f"Invalid mode: '{mode}'. Must be 'swing' or 'scalping'.")

        if df.empty or len(df) < 50:
            return {"supports": [], "resistances": []}

        df_cleaned = df.rename(columns={c: c.capitalize() for c in df.columns})

        if mode_lower == "swing":
            # local extrema using rolling window of 20 periods on each side (window = 41)
            window = 20
            lows = df_cleaned["Low"]
            highs = df_cleaned["High"]

            # Compute rolling min/max
            rolling_min = lows.rolling(window=window * 2 + 1, center=True).min()
            rolling_max = highs.rolling(window=window * 2 + 1, center=True).max()

            # Find points where low equals rolling min and high equals rolling max
            support_mask = lows == rolling_min
            resistance_mask = highs == rolling_max

            supports = lows[support_mask].dropna().unique().tolist()
            resistances = highs[resistance_mask].dropna().unique().tolist()

            # Sort levels
            supports = sorted(supports)
            resistances = sorted(resistances)

            # Cap list length for convenience (e.g., last 3 closest to current price)
            current_price = df_cleaned["Close"].iloc[-1]
            supports_closest = sorted(supports, key=lambda x: abs(x - current_price))[:3]
            resistances_closest = sorted(resistances, key=lambda x: abs(x - current_price))[:3]

            return {
                "supports": sorted(supports_closest),
                "resistances": sorted(resistances_closest),
                "method": "local_extrema"
            }

        else:  # scalping mode
            # Calculate Fibonacci Pivot Points based on the latest daily bar in the dataframe,
            # or the overall high, low, close if Daily timeframe isn't directly segmented.
            # For robust fallback, we take the last 24 periods to represent the daily session.
            # If the index is DatetimeIndex, we try to resample to Daily.
            try:
                if isinstance(df_cleaned.index, pd.DatetimeIndex):
                    daily_df = df_cleaned.resample('D').agg({
                        'High': 'max',
                        'Low': 'min',
                        'Close': 'last'
                    }).dropna()
                    if len(daily_df) >= 2:
                        # Use the previous complete day
                        prev_day = daily_df.iloc[-2]
                        high = prev_day['High']
                        low = prev_day['Low']
                        close = prev_day['Close']
                    else:
                        high = df_cleaned['High'].max()
                        low = df_cleaned['Low'].min()
                        close = df_cleaned['Close'].iloc[-1]
                else:
                    # Fallback to whole df range
                    high = df_cleaned['High'].max()
                    low = df_cleaned['Low'].min()
                    close = df_cleaned['Close'].iloc[-1]
            except Exception as e:
                logger.warning(f"Failed to compute daily pivots, using df-wide metrics: {str(e)}")
                high = df_cleaned['High'].max()
                low = df_cleaned['Low'].min()
                close = df_cleaned['Close'].iloc[-1]

            # Classical Fibonacci Pivot Points formulas
            pp = (high + low + close) / 3.0
            range_val = high - low

            r1 = pp + 0.382 * range_val
            r2 = pp + 0.618 * range_val
            r3 = pp + 1.000 * range_val

            s1 = pp - 0.382 * range_val
            s2 = pp - 0.618 * range_val
            s3 = pp - 1.000 * range_val

            return {
                "pivot": pp,
                "resistances": [r1, r2, r3],
                "supports": [s1, s2, s3],
                "method": "fibonacci_pivots"
            }

    async def generate_technical_bias(self, df: pd.DataFrame, mode: str) -> Dict[str, Any]:
        """
        Generates technical bias (LONG, SHORT, WAIT) and confluence score based on Triple Confirmation Strategy.

        Args:
            df: pd.DataFrame of historical OHLCV data.
            mode: 'swing' or 'scalping' (can be used to customize periods if needed).

        Returns:
            Dict containing 'direction', 'confluence_score', and 'reason'.
        """
        if df.empty or len(df) < 50:
            return {
                "direction": "WAIT",
                "confluence_score": 0.0,
                "reason": "Insufficient data to calculate technical bias."
            }

        try:
            df_cleaned = df.rename(columns={c: c.capitalize() for c in df.columns})

            # 1. EMA Trend Confirmation (EMA 20 vs EMA 50)
            ema_fast = ta.ema(df_cleaned["Close"], length=20)
            ema_slow = ta.ema(df_cleaned["Close"], length=50)

            # 2. Momentum Confirmation (RSI 14)
            rsi = ta.rsi(df_cleaned["Close"], length=14)

            # 3. MACD Crossover Confirmation
            macd_df = ta.macd(df_cleaned["Close"])

            if ema_fast is None or ema_slow is None or rsi is None or macd_df is None:
                return {
                    "direction": "WAIT",
                    "confluence_score": 0.0,
                    "reason": "Indicator calculation failed."
                }

            # Find MACD column names
            macd_col = [c for c in macd_df.columns if "MACD_" in c and not "s" in c.lower()]
            macd_sig_col = [c for c in macd_df.columns if "MACDs_" in c]

            if not macd_col or not macd_sig_col:
                return {
                    "direction": "WAIT",
                    "confluence_score": 0.0,
                    "reason": "MACD indicator columns missing."
                }

            macd_line = macd_df[macd_col[0]]
            macd_sig = macd_df[macd_sig_col[0]]

            # Extract last values
            last_close = df_cleaned["Close"].iloc[-1]
            last_ema_fast = ema_fast.iloc[-1]
            last_ema_slow = ema_slow.iloc[-1]
            last_rsi = rsi.iloc[-1]
            last_macd = macd_line.iloc[-1]
            last_macd_sig = macd_sig.iloc[-1]

            # Evaluate each signal
            signals = []
            reasons = []

            # Trend (EMA Crossover)
            if last_ema_fast > last_ema_slow:
                signals.append("LONG")
                reasons.append(f"EMA Trend Bullish (EMA20 {last_ema_fast:.5f} > EMA50 {last_ema_slow:.5f})")
            elif last_ema_fast < last_ema_slow:
                signals.append("SHORT")
                reasons.append(f"EMA Trend Bearish (EMA20 {last_ema_fast:.5f} < EMA50 {last_ema_slow:.5f})")
            else:
                signals.append("NEUTRAL")

            # Momentum (RSI)
            if 50.0 < last_rsi < 70.0:
                signals.append("LONG")
                reasons.append(f"RSI Momentum Bullish ({last_rsi:.1f})")
            elif 30.0 < last_rsi < 50.0:
                signals.append("SHORT")
                reasons.append(f"RSI Momentum Bearish ({last_rsi:.1f})")
            else:
                signals.append("NEUTRAL")
                reasons.append(f"RSI Neutral/Extreme ({last_rsi:.1f})")

            # MACD Crossover
            if last_macd > last_macd_sig:
                signals.append("LONG")
                reasons.append(f"MACD Bullish Crossover (MACD {last_macd:.5f} > Signal {last_macd_sig:.5f})")
            elif last_macd < last_macd_sig:
                signals.append("SHORT")
                reasons.append(f"MACD Bearish Crossover (MACD {last_macd:.5f} < Signal {last_macd_sig:.5f})")
            else:
                signals.append("NEUTRAL")

            # Count signals
            long_count = signals.count("LONG")
            short_count = signals.count("SHORT")

            if long_count > short_count:
                direction = "LONG"
                score = (long_count / 3.0) * 100.0
            elif short_count > long_count:
                direction = "SHORT"
                score = (short_count / 3.0) * 100.0
            else:
                direction = "WAIT"
                score = 0.0

            # If confluence is too low (e.g., less than 66.7%), we default to WAIT
            if score < 66.0:
                direction = "WAIT"

            reason_str = " | ".join(reasons)
            return {
                "direction": direction,
                "confluence_score": round(score, 2),
                "reason": reason_str
            }
        except Exception as e:
            logger.error(f"Error in generate_technical_bias: {str(e)}")
            return {
                "direction": "WAIT",
                "confluence_score": 0.0,
                "reason": f"Calculation error: {str(e)}"
            }
