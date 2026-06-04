import os
import json
import logging
from dataclasses import dataclass
from typing import Dict, Optional
import pandas as pd
import pandas_ta as ta

def load_pair_settings() -> dict:
    """Helper to dynamically load settings from pair_settings.json."""
    try:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        settings_path = os.path.join(root_dir, "data", "pair_settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading pair settings: {e}")
    return {}

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class RiskPackage:
    """Dataclass representing the complete risk profile for a generated signal."""
    pair: str
    direction: str          # "LONG" | "SHORT"
    entry_price: float
    sl_price: float
    tp1_price: float        # TP1 (RRR 1:1.5)
    tp2_price: float        # TP2 (RRR 1:2.0)
    lot_size: float
    sl_pips: float
    atr_value: float
    risk_amount_usd: float
    rrr_tp1: float = 1.5
    rrr_tp2: float = 2.0


class RiskManagementEngine:
    """Engine responsible for calculating Stop Loss, Take Profits, and Lot Sizing."""

    # Pip sizes per pair type/prefix
    PIP_SIZES: Dict[str, float] = {
        "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001, "NZDUSD": 0.0001,
        "USDJPY": 0.01,   "GBPJPY": 0.01,   "EURJPY": 0.01,
        "USDCAD": 0.0001, "USDCHF": 0.0001,
        "XAUUSD": 0.01,   "BTCUSD": 1.0,
    }

    # Contract sizes per asset class
    CONTRACT_SIZES: Dict[str, float] = {
        "XAUUSD": 100.0,    # Gold: 1 lot = 100 oz
        "BTCUSD": 1.0,      # Crypto: 1 lot = 1 BTC
    }
    DEFAULT_FOREX_CONTRACT_SIZE = 100000.0  # Standard lot = 100k units

    # ATR Multipliers per timeframe
    ATR_MULTIPLIERS: Dict[str, float] = {
        "M1": 1.25,
        "M5": 1.25,
        "M15": 1.5,
        "H1": 1.75,
        "H4": 2.0,
        "D1": 2.5
    }
    DEFAULT_ATR_MULTIPLIER = 1.75

    async def compute_atr(self, ohlcv: pd.DataFrame, period: int = 14) -> float:
        """
        Asynchronously computes the Average True Range (ATR) from a DataFrame of OHLCV data.

        Args:
            ohlcv: pd.DataFrame containing 'High', 'Low', 'Close' columns.
            period: The period over which to calculate ATR.

        Returns:
            The last ATR value as a float.

        Raises:
            ValueError: If required columns are missing or DataFrame is empty.
        """
        if ohlcv.empty:
            raise ValueError("OHLCV DataFrame is empty.")
        
        required_cols = {"High", "Low", "Close"}
        missing_cols = required_cols - set(ohlcv.columns)
        if missing_cols:
            # Fallback to check case-insensitive match
            ohlcv_cols_lower = {c.lower(): c for c in ohlcv.columns}
            mapped_cols = {}
            for col in required_cols:
                if col.lower() in ohlcv_cols_lower:
                    mapped_cols[col] = ohlcv_cols_lower[col.lower()]
                else:
                    raise ValueError(f"Missing required column: {col}")
            # Rename columns to standard casing for pandas_ta
            ohlcv = ohlcv.rename(columns={v: k for k, v in mapped_cols.items()})

        # Perform calculations
        try:
            atr_series = ta.atr(
                high=ohlcv["High"],
                low=ohlcv["Low"],
                close=ohlcv["Close"],
                length=period
            )
            if atr_series is None or atr_series.empty:
                raise ValueError("ATR computation returned empty series.")
            
            last_atr = atr_series.iloc[-1]
            if pd.isna(last_atr):
                # If last is NaN (e.g., not enough data), get last non-NaN or raise
                last_atr = atr_series.dropna().iloc[-1] if not atr_series.dropna().empty else None
                if last_atr is None:
                    raise ValueError("ATR computation resulted in all NaN values.")
                    
            return float(last_atr)
        except Exception as e:
            logger.error(f"Error computing ATR: {str(e)}")
            raise ValueError(f"Failed to compute ATR: {str(e)}") from e

    def compute_pip_value(self, pair: str, current_price: float, quote_usd_rate: Optional[float] = None) -> float:
        """
        Computes the pip value in USD for 1.0 standard lot.

        Args:
            pair: The symbol currency pair (e.g. 'EURUSD', 'USDJPY', 'XAUUSD').
            current_price: The current market price of the pair.
            quote_usd_rate: Optional exchange rate to convert the quote currency to USD.
                            For EURGBP, quote is GBP, so quote_usd_rate would be the GBPUSD rate.

        Returns:
            The value of 1 pip in USD for 1 standard lot.
        """
        pip_size = self.PIP_SIZES.get(pair, 0.0001)
        contract_size = self.CONTRACT_SIZES.get(pair, self.DEFAULT_FOREX_CONTRACT_SIZE)

        # Standard Direct Pairs (XXX/USD)
        if pair.endswith("USD") and not pair.startswith("USD"):
            # Gold (XAUUSD): pip_size = 0.01, contract_size = 100 -> pip_value = 0.01 * 100 = $1.00
            # EURUSD: pip_size = 0.0001, contract_size = 100,000 -> pip_value = 0.0001 * 100,000 = $10.00
            return pip_size * contract_size

        # Indirect Pairs (USD/XXX, e.g. USDJPY, USDCAD, USDCHF)
        if pair.startswith("USD"):
            # Pip value in base (USD) = (pip_size / current_price) * contract_size
            return (pip_size / current_price) * contract_size

        # Cross Currency Pairs (XXX/YYY, e.g. EURGBP)
        if quote_usd_rate is not None:
            # Pip value in quote currency = pip_size * contract_size
            # Convert to USD: (pip_size * contract_size) * quote_usd_rate
            return pip_size * contract_size * quote_usd_rate

        # Generic fallback
        return pip_size * contract_size

    async def calculate(
        self,
        pair: str,
        direction: str,
        entry_price: float,
        ohlcv: pd.DataFrame,
        capital_usd: float,
        risk_pct: float,
        timeframe: str = "H1",
        quote_usd_rate: Optional[float] = None,
        atr_period: int = 14,
        mode: Optional[str] = None,
        override_settings: Optional[dict] = None
    ) -> RiskPackage:
        """
        Calculates a complete RiskPackage containing stop loss, take profit targets, and dynamic lot sizing.

        Args:
            pair: Currency pair (e.g. 'EURUSD', 'USDJPY', 'XAUUSD').
            direction: Sinyal direction ('LONG' or 'SHORT').
            entry_price: Market entry price.
            ohlcv: DataFrame of historical OHLCV data.
            capital_usd: Account capital in USD.
            risk_pct: Risk percentage per trade (e.g., 1.0 for 1%).
            timeframe: Timeframe of the signal (determines the ATR multiplier).
            quote_usd_rate: Optional rate for cross-pair conversion.
            atr_period: Period for ATR calculation.
            mode: Optional trading mode ('scalping' or 'swing').
            override_settings: Optional dictionary to override pair_settings.json.

        Returns:
            RiskPackage detailing the risk management plan.
        """
        direction_upper = direction.upper()
        if direction_upper not in {"LONG", "SHORT"}:
            raise ValueError(f"Invalid direction: '{direction}'. Must be LONG or SHORT.")

        # 1. Compute ATR & Volatility
        atr = await self.compute_atr(ohlcv, period=atr_period)
        
        # Determine dynamic multipliers from pair_settings.json
        resolved_mode = mode.lower() if mode else ("scalping" if timeframe.upper() in {"M1", "M5", "M15", "M30"} else "swing")
        
        if override_settings:
            mode_config = override_settings
        else:
            settings_dict = load_pair_settings()
            pair_upper = pair.upper()
            pair_config = settings_dict.get(pair_upper, settings_dict.get("DEFAULT", {}))
            mode_config = pair_config.get(resolved_mode, settings_dict.get("DEFAULT", {}).get(resolved_mode, {}))
        
        # Fallbacks if JSON config is missing or incomplete
        default_sl_mult = 1.5 if resolved_mode == "scalping" else self.ATR_MULTIPLIERS.get(timeframe.upper(), self.DEFAULT_ATR_MULTIPLIER)
        default_tp_mult = 1.5 if resolved_mode == "scalping" else 3.0
        
        sl_multiplier = mode_config.get("sl_atr_multiplier", default_sl_mult)
        tp_multiplier = mode_config.get("tp_atr_multiplier", default_tp_mult)
        
        sl_distance = atr * sl_multiplier

        # Determine precision based on pair (JPY or Gold have 2 decimals, standard forex has 5)
        is_jpy_or_gold = "JPY" in pair or pair.startswith("XAU")
        price_precision = 2 if is_jpy_or_gold else 5
        pip_size = self.PIP_SIZES.get(pair, 0.0001)

        # 2. Calculate Stop Loss Price
        if direction_upper == "LONG":
            sl_price = entry_price - sl_distance
        else:
            sl_price = entry_price + sl_distance

        # Prevent negative SL prices
        sl_price = max(0.00001, sl_price)

        risk_dist = abs(entry_price - sl_price)

        # 3. Calculate Take Profit Prices
        tp2_distance = atr * tp_multiplier
        tp1_distance = atr * (tp_multiplier * 0.8)  # TP1 is 80% of TP2
        
        if direction_upper == "LONG":
            tp1_price = entry_price + tp1_distance
            tp2_price = entry_price + tp2_distance
        else:
            tp1_price = entry_price - tp1_distance
            tp2_price = entry_price - tp2_distance

        # Prevent negative TP prices
        tp1_price = max(0.00001, tp1_price)
        tp2_price = max(0.00001, tp2_price)

        # Round prices to their correct precision
        sl_price_rounded = round(sl_price, price_precision)
        tp1_price_rounded = round(tp1_price, price_precision)
        tp2_price_rounded = round(tp2_price, price_precision)
        entry_price_rounded = round(entry_price, price_precision)

        # Ensure TP2 is further than TP1 by at least 1 pip/unit of precision
        if tp1_price_rounded == tp2_price_rounded:
            precision_step = 10 ** (-price_precision)
            if direction_upper == "LONG":
                tp2_price_rounded = round(tp2_price_rounded + precision_step, price_precision)
            else:
                tp2_price_rounded = round(tp2_price_rounded - precision_step, price_precision)

        # 4. Pip distance & risk value calculations
        sl_pips = risk_dist / pip_size
        risk_amount_usd = capital_usd * (risk_pct / 100.0)

        # Compute pip value per lot at entry price
        pip_value_per_lot = self.compute_pip_value(pair, entry_price, quote_usd_rate)

        # Calculate Lot Size: risk_amount / (sl_pips * pip_value_per_lot)
        if sl_pips > 0 and pip_value_per_lot > 0:
            lot_size = risk_amount_usd / (sl_pips * pip_value_per_lot)
            # Standard rounding to 2 decimals, minimum lot size is 0.01
            lot_size = round(max(0.01, lot_size), 2)
        else:
            lot_size = 0.01

        return RiskPackage(
            pair=pair,
            direction=direction_upper,
            entry_price=entry_price_rounded,
            sl_price=sl_price_rounded,
            tp1_price=tp1_price_rounded,
            tp2_price=tp2_price_rounded,
            lot_size=lot_size,
            sl_pips=round(sl_pips, 1),
            atr_value=round(atr, 6),
            risk_amount_usd=round(risk_amount_usd, 2)
        )
