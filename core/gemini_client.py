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
    ) -> dict:
        """
        Unified AI analysis method combining Technical + Fundamental reasoning.
        
        Args:
            pair: Trading instrument (e.g. 'XAUUSD', 'EURUSD').
            economic_context: Pre-formatted text of scheduled economic events
                              from Forex Factory XML or simulated calendar.
            market_data_context: Pre-computed string of live price data, indicators
                                 (EMA, RSI, MACD), and recent candle summaries
                                 from MetaTrader 5 / Yahoo Finance.
        
        Returns:
            dict with keys: sentiment, bias, reason.
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

        prompt = f"""You are an Elite Institutional Forex Technical & Fundamental Analyst and AI Agent.
Today's date is {current_date_str}. You are analyzing: {pair}.

{technical_section}

{calendar_section}

INSTRUCTIONS — Perform a blended Technical + Fundamental analysis:

TECHNICAL (from the live data above):
1. Identify the current trend using EMA 20/50 alignment and price position.
2. Evaluate momentum using RSI(14) — is the market overbought (>70), oversold (<30), or neutral?
3. Check MACD crossover direction for momentum confirmation.
4. Examine the last 5 candles for price action signals: break of structure, rejection wicks, engulfing patterns, or inside bars.

FUNDAMENTAL (from the economic calendar above):
5. Which scheduled high-impact events (if any) are likely to cause volatility for {pair}?
6. What is the prevailing market expectation ahead of these events?

SYNTHESIS:
7. Combine technical structure with fundamental catalysts to determine a high-conviction short-term directional bias.
8. If technical and fundamental signals conflict, lean toward WAIT.

You MUST respond with a raw, valid JSON object only. Do NOT wrap in markdown code-blocks.
Ensure keys match exactly:
{{
    "sentiment": "BULLISH" or "BEARISH" or "NEUTRAL",
    "bias": "BUY" or "SELL" or "WAIT",
    "reason": "1-2 sentence high-conviction breakdown blending the live chart patterns with fundamental data."
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
            return json.loads(raw_content)

        except Exception as e:
            logger.error(f"Groq Agent failed to parse sentiment: {e}")
            return {
                "sentiment": "NEUTRAL",
                "bias": "WAIT",
                "reason": f"Agent engine temporary calculation error: {str(e)}"
            }

    async def analyze_market_news(self, news_text: str) -> Dict[str, Any]:
        """
        Legacy method called by test suite. Normalizes the output.
        
        - Maps "reason" to "summary" (and vice versa)
        - Maps bias: BUY/LONG -> LONG, SELL/SHORT -> SHORT, else WAIT
        - Maps sentiment: BULLISH/BULL -> BULLISH, BEARISH/BEAR -> BEARISH, else NEUTRAL
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

        return result

    def _generate_mock_analysis(self, news_text: str) -> Dict[str, Any]:
        """Generates realistic mock sentiment decisions for local debugging/fallback."""
        logger.info("Generating mock Groq analysis.")
        news_lower = news_text.lower() if news_text else ""
        
        if "nfp" in news_lower or "stronger" in news_lower or "bullish" in news_lower:
            return {
                "sentiment": "BULLISH",
                "bias": "LONG",
                "summary": "[MOCK AI] Employment data shows solid growth. Yields rising and support currency strength."
            }
        elif "weak" in news_lower or "dovish" in news_lower or "bearish" in news_lower:
            return {
                "sentiment": "BEARISH",
                "bias": "SHORT",
                "summary": "[MOCK AI] Softer data print fuels interest rate cut expectations, weighing down the currency."
            }
        else:
            return {
                "sentiment": "NEUTRAL",
                "bias": "WAIT",
                "summary": "[MOCK AI] Mixed indicators; no high-impact events currently aligning for direction."
            }
