import os
import json
import logging
import asyncio
import datetime
from typing import Dict, Any
from groq import Groq

from core.config import settings

logger = logging.getLogger(__name__)

class GeminiRateLimiter:
    """
    Retained for backward compatibility/limiter testing.
    """
    def __init__(self, rpm: int = 60):
        self.rpm = rpm

    async def acquire(self) -> None:
        pass


class GeminiAnalyseClient:
    def __init__(self):
        self.api_key = settings.groq_api_key or os.getenv("GROQ_API_KEY")
        self.model = settings.groq_model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        
        if not self.api_key:
            logger.warning("GROQ_API_KEY is not configured. Client will operate in mock mode.")
            self.client = None
        else:
            self.client = Groq(api_key=self.api_key)

    async def analyse_news_sentiment(
        self,
        pair: str,
        economic_context: str = "",
        market_data_context: str = "",
        h4_trend: str = "BULLISH",
        highest_high_24h: float = 0.0,
        lowest_low_24h: float = 0.0,
        last_candle_type: str = "BULLISH",
        is_rejection: bool = False,
        mode: str = "swing"
    ) -> dict:
        """
        Unified AI analysis method combining Technical + Fundamental reasoning.
        """
        if not self.client:
            return {
                "sentiment": "NEUTRAL",
                "bias": "WAIT",
                "reason": "[MOCK AI] Groq API key is missing. Operating in fallback simulation mode."
            }

        current_date_str = datetime.date.today().strftime("%A, %B %d, %Y")

        # ── Build Fundamental Section ──
        if economic_context and economic_context.strip():
            calendar_section = (
                "── Scheduled Economic Calendar (Forex Factory) ──\n"
                "NOTE: This is an UPCOMING EVENT SCHEDULE containing event names, impact levels,\n"
                "and scheduled times — but NOT actual release figures or outcomes.\n"
                "Use these to assess which high-impact events could cause volatility.\n\n"
                f"{economic_context}"
            )
        else:
            calendar_section = "No scheduled economic events found for today."

        # ── Build Technical Section ──
        if market_data_context and market_data_context.strip():
            technical_section = (
                "── Live Technical Data (from broker feed) ──\n"
                f"{market_data_context}"
            )
        else:
            technical_section = "No live market data available for technical analysis."

        mode_lower = mode.lower()
        if mode_lower == "scalping":
            prompt = f"""You are an Elite Forex Scalper and Momentum Trader.
Today's date is {current_date_str}. You are analyzing: {pair} in SCALPING mode (Execution: M5, Macro: M15).

{technical_section}

── M5/M15 Scalping Parameters ──
- M15 Macro Trend Bias: {h4_trend}
- 3-Hour Highest High (Local Resistance): {highest_high_24h}
- 3-Hour Lowest Low (Local Support): {lowest_low_24h}
- Last M5 Candle Type: {last_candle_type}
- Last M5 Candle Rejection Wick Detected (>40% of range): {is_rejection}

{calendar_section}

SCALPING INSTRUCTIONS:
1. Analyze micro-momentum and candlestick rejections near the 3-hour High/Low key levels.
2. Target tight spreads, fast order flow, and quick scalping pullbacks.
3. Prioritize M15 Trend Bias: {h4_trend}. Favor quick momentum entries in that direction. If M5 is highly volatile or conflicting, suggest "WAIT".
4. If current price is close to 3-hour support or resistance showing rejection wicks (rejection detected: {is_rejection}), suggest instant MARKET EXECUTION. Otherwise, set a BUY LIMIT or SELL LIMIT at the local 3h High/Low or key pullback spots.

SYNTHESIS & FORMAT:
- Respond with a raw, valid JSON object only. Do NOT wrap in markdown code-blocks.
Ensure keys match exactly:
{{
    "sentiment": "BULLISH" or "BEARISH" or "NEUTRAL",
    "order_type": "MARKET EXECUTION" or "BUY LIMIT" or "SELL LIMIT",
    "entry_spot": 1.15950,
    "bias": "BUY" or "SELL" or "WAIT",
    "reason": "A 1-2 sentence scalping breakdown explaining the local M5/M15 momentum setup and trigger levels."
}}"""
        else:
            prompt = f"""You are an Elite Institutional Forex Swing Analyst and Macro Trader.
Today's date is {current_date_str}. You are analyzing: {pair} in SWING mode (Execution: H1, Macro: H4).

{technical_section}

── H1/H4 Swing Parameters ──
- H4 Institutional Macro Trend: {h4_trend}
- 24-Hour Highest High (Major Resistance): {highest_high_24h}
- 24-Hour Lowest Low (Major Support): {lowest_low_24h}
- Last H1 Candle Type: {last_candle_type}
- Last H1 Candle Rejection Wick Detected (>40% of range): {is_rejection}

{calendar_section}

SWING INSTRUCTIONS:
1. Evaluate major Smart Money Concepts (SMC) like Break of Structure (BOS), Change of Character (CHoCH), and Fair Value Gaps (FVG) based on the candle matrix.
2. Prioritize the H4 Institutional Trend: {h4_trend}. Look for entries that align with this macro trend, ignoring minor H1 counter-trend breakouts.
3. If current price is far from optimal support/resistance levels or FVG pullback zones, do NOT suggest instant entry. Instead, set a BUY LIMIT or SELL LIMIT at a premium structural level. Suggest MARKET EXECUTION only if major candle rejection or breakout occurs right now.

SYNTHESIS & FORMAT:
- Combine technical structure (SMC, Price Action, MTF alignment) with fundamental calendar catalysts.
- You MUST respond with a raw, valid JSON object only. Do NOT wrap in markdown code-blocks.
Ensure keys match exactly:
{{
    "sentiment": "BULLISH" or "BEARISH" or "NEUTRAL",
    "order_type": "MARKET EXECUTION" or "BUY LIMIT" or "SELL LIMIT",
    "entry_spot": 1.15950,
    "bias": "BUY" or "SELL" or "WAIT",
    "reason": "A 1-2 sentence swing analysis detailing SMC, premium pullback zones, and H4 macro alignment."
}}"""


        try:
            loop = asyncio.get_event_loop()
            completion = await loop.run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
            )
            
            raw_content = completion.choices[0].message.content
            parsed = json.loads(raw_content)
            
            # Ensure safety defaults
            if "order_type" not in parsed:
                parsed["order_type"] = "MARKET EXECUTION"
            if "entry_spot" not in parsed:
                # We can fallback to the current price if available, parsed as float
                parsed["entry_spot"] = float(highest_high_24h + lowest_low_24h) / 2.0 if highest_high_24h > 0 else 1.08500
            else:
                try:
                    parsed["entry_spot"] = float(parsed["entry_spot"])
                except (ValueError, TypeError):
                    parsed["entry_spot"] = 1.08500
            
            return parsed

        except Exception as e:
            logger.error(f"Groq Agent failed to parse sentiment: {e}")
            return {
                "sentiment": "NEUTRAL",
                "order_type": "MARKET EXECUTION",
                "entry_spot": 1.08500,
                "bias": "WAIT",
                "reason": f"Agent engine temporary calculation error: {str(e)}"
            }

    async def analyze_market_news(self, news_text: str) -> Dict[str, Any]:
        """
        Legacy method called by test suite. Normalizes the output.
        """
        if not self.client or not news_text or "MOCK" in (news_text or ""):
            result = self._generate_mock_analysis(news_text)
        else:
            result = await self.analyse_news_sentiment(
                pair="GENERAL",
                economic_context=news_text
            )

        # Normalize keys
        if "reason" in result and "summary" not in result:
            result["summary"] = result["reason"]
        elif "summary" in result and "reason" not in result:
            result["reason"] = result["summary"]
            
        # Normalize bias
        bias_val = str(result.get("bias", "WAIT")).upper().strip()
        if "BUY" in bias_val or "LONG" in bias_val:
            result["bias"] = "LONG"
        elif "SELL" in bias_val or "SHORT" in bias_val:
            result["bias"] = "SHORT"
        else:
            result["bias"] = "WAIT"

        # Normalize sentiment
        sentiment_val = str(result.get("sentiment", "NEUTRAL")).upper().strip()
        if "BULL" in sentiment_val:
            result["sentiment"] = "BULLISH"
        elif "BEAR" in sentiment_val:
            result["sentiment"] = "BEARISH"
        else:
            result["sentiment"] = "NEUTRAL"

        if "order_type" not in result:
            result["order_type"] = "MARKET EXECUTION"
        if "entry_spot" not in result:
            result["entry_spot"] = 1.08500

        return result

    def _generate_mock_analysis(self, news_text: str) -> Dict[str, Any]:
        """Generates realistic mock sentiment decisions for local debugging/fallback."""
        logger.info("Generating mock Groq analysis.")
        news_lower = news_text.lower() if news_text else ""
        
        if "nfp" in news_lower or "stronger" in news_lower or "bullish" in news_lower:
            return {
                "sentiment": "BULLISH",
                "bias": "LONG",
                "order_type": "MARKET EXECUTION",
                "entry_spot": 1.08500,
                "summary": "[MOCK AI] Employment data shows solid growth. Yields rising and support currency strength."
            }
        elif "weak" in news_lower or "dovish" in news_lower or "bearish" in news_lower:
            return {
                "sentiment": "BEARISH",
                "bias": "SHORT",
                "order_type": "MARKET EXECUTION",
                "entry_spot": 1.08500,
                "summary": "[MOCK AI] Softer data print fuels interest rate cut expectations, weighing down the currency."
            }
        else:
            return {
                "sentiment": "NEUTRAL",
                "bias": "WAIT",
                "order_type": "MARKET EXECUTION",
                "entry_spot": 1.08500,
                "summary": "[MOCK AI] Mixed indicators; no high-impact events currently aligning for direction."
            }

