import html
import logging
from aiogram import Router, types
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.enums import ParseMode

from core.config import settings
from db.queries import is_user_whitelisted, log_signal
from data.price_fetcher import fetch_ohlcv_with_backoff, compute_market_data_context
from engines.technical_engine import TechnicalEngine
from data.news_fetcher import fetch_economic_calendar
from core.gemini_client import GeminiAnalyseClient
from engines.risk_engine import RiskManagementEngine

logger = logging.getLogger(__name__)

router = Router()

# Initialize engines
tech_engine = TechnicalEngine()
gemini_client = GeminiAnalyseClient()
risk_engine = RiskManagementEngine()

async def check_user_allowed(user_id: int) -> bool:
    """
    Checks if a user is allowed to access the bot.
    Bypasses database check if user is the designated admin.
    """
    # ── HARDCODE FAILSAFE (OVERRIDE ADMIN) ──
    if str(user_id) == "6827317690" or user_id in settings.admin_ids:
        return True
    try:
        return await is_user_whitelisted(user_id)
    except Exception as e:
        logger.error(f"Database error during whitelist check: {e}")
        return False

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    """Handler for the /start command."""
    user_id = message.from_user.id
    username = message.from_user.username or "Trader"
    
    # Check whitelist with override
    if not await check_user_allowed(user_id):
        logger.warning(f"Unauthorized access attempt by user_id {user_id}")
        await message.answer("⚠️ Anda tidak terdaftar dalam whitelist. Akses ditolak.")
        return

    welcome_text = (
        f"👋 <b>Halo, {username}!</b>\n\n"
        f"Selamat datang di <b>AI Forex Co-Pilot Bot</b>.\n"
        f"Bot ini menggunakan kecerdasan buatan dan analisis teknikal untuk memandu keputusan trading Anda.\n\n"
        f"🛠️ <b>Menu Perintah:</b>\n"
        f"/start - Memulai bot dan menyapa Anda\n"
        f"/help - Menampilkan panduan penggunaan lengkap\n"
        f"/analisa [PAIR] - Menjalankan analisis teknikal & fundamental AI (Contoh: <code>/analisa XAUUSD</code>)\n\n"
        f"⚖️ <i>Selalu gunakan manajemen risiko yang ketat.</i>"
    )
    await message.answer(welcome_text, parse_mode=ParseMode.HTML)


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Handler for the /help command."""
    user_id = message.from_user.id
    
    # Check whitelist with override
    if not await check_user_allowed(user_id):
        await message.answer("⚠️ Anda tidak terdaftar dalam whitelist. Akses ditolak.")
        return

    help_text = (
        f"❓ <b>Panduan Penggunaan AI Forex Co-Pilot:</b>\n\n"
        f"📝 <b>Cara Analisis Pair:</b>\n"
        f"Gunakan perintah <code>/analisa [PAIR]</code> untuk melakukan analisis instan.\n"
        f"• Contoh: <code>/analisa XAUUSD</code>\n"
        f"• Contoh: <code>/analisa EURUSD</code>\n"
        f"• Jika tidak menentukan pair, sistem secara default menganalisis <b>XAUUSD</b>.\n\n"
        f"🔍 <b>Proses Kerja AI Orchestrator:</b>\n"
        f"1. <b>Data Retrieval</b>: Mengambil data harga (OHLCV) terbaru.\n"
        f"2. <b>Technical Engine</b>: Mendeteksi market regime, level SNR (Support & Resistance), dan Technical Bias (EMA, RSI, MACD).\n"
        f"3. <b>Fundamental Sentiment</b>: Membaca rilis berita ekonomi hari ini dan meminta analisis sentimen dari Gemini AI.\n"
        f"4. <b>Risk Management</b>: Menghitung target Stop Loss (SL), Take Profit (TP), dan ukuran Lot yang aman secara dinamis berdasarkan parameter risiko Anda.\n\n"
        f"📌 <i>Gunakan bot ini sebagai referensi pelengkap analisis Anda sendiri.</i>"
    )
    await message.answer(help_text, parse_mode=ParseMode.HTML)


@router.message(Command("analisa"))
async def cmd_analisa(message: types.Message, command: CommandObject):
    """Handler for /analisa command to perform complete orchestrated trading analysis."""
    user_id = message.from_user.id
    
    # 1. Whitelist Check with override
    if not await check_user_allowed(user_id):
        logger.warning(f"Unauthorized user {user_id} attempted /analisa command.")
        await message.answer("⚠️ Anda tidak terdaftar dalam whitelist. Akses ditolak.")
        return

    # 2. Extract & validate pair and mode arguments
    # Format: /analisa [PAIR] [MODE]
    args_str = command.args
    if not args_str:
        await message.answer(
            "<b>❌ Format Salah!</b>\n"
            "Gunakan format: <code>/analisa [NAMA_PAIR] [MODE]</code>\n"
            "Contoh: <code>/analisa EURUSD scalping</code> atau <code>/analisa XAUUSD swing</code>",
            parse_mode=ParseMode.HTML
        )
        return

    parts = [p.strip() for p in args_str.split() if p.strip()]
    pair = parts[0].upper()
    
    mode = "swing"
    if len(parts) >= 2:
        mode_arg = parts[1].lower()
        if mode_arg in {"sc", "scalping"}:
            mode = "scalping"
        elif mode_arg in {"sw", "swing"}:
            mode = "swing"

    await message.answer(
        f"⏳ <b>FRXBOT:</b> Memulai analisis <b>[{mode.upper()}]</b> untuk <b>{pair}</b>... Silakan tunggu sebentar.",
        parse_mode=ParseMode.HTML
    )

    try:
        # 3. Step A: Price Data Retrieval
        timeframe = "M5" if mode == "scalping" else "H1"
        logger.info(f"Fetching price data for {pair} in {mode} mode (execution TF: {timeframe})")
        try:
            ohlcv_data = await fetch_ohlcv_with_backoff(pair, timeframe, mode=mode)
            ohlcv = ohlcv_data["df"]
        except Exception as e:
            logger.error(f"Error fetching price data for {pair}: {e}")
            await message.answer(f"❌ Gagal mengambil data harga untuk {pair}. Silakan coba lagi nanti.")
            return

        if ohlcv.empty:
            await message.answer(f"❌ Data harga kosong untuk {pair}. Hubungi admin atau coba pair lain.")
            return

        # 4. Step B: Technical Engine Analysis
        logger.info(f"Analyzing technical indicators for {pair} in {mode} mode")
        try:
            market_regime = await tech_engine.detect_market_regime(ohlcv)
            tech_bias_dict = await tech_engine.generate_technical_bias(ohlcv, mode=mode)
            snr_dict = await tech_engine.calculate_snr(ohlcv, mode=mode)
        except Exception as e:
            logger.error(f"Error in TechnicalEngine for {pair}: {e}")
            await message.answer("❌ Terjadi kesalahan pada Technical Engine saat menganalisis chart.")
            return

        # Extract technical output
        tech_direction = tech_bias_dict.get("direction", "WAIT")
        confluence_score = tech_bias_dict.get("confluence_score", 0.0)
        tech_reason = tech_bias_dict.get("reason", "N/A")
        supports = snr_dict.get("supports", [])
        resistances = snr_dict.get("resistances", [])
        
        supports_str = ", ".join([f"{s:.5f}" if s < 10 else f"{s:.2f}" for s in supports]) if supports else "None"
        resistances_str = ", ".join([f"{r:.5f}" if r < 10 else f"{r:.2f}" for r in resistances]) if resistances else "None"
        
        entry_price = float(ohlcv["Close"].iloc[-1])

        # 5. Step C: AI Analysis (Technical from live data + Fundamental from calendar -> Groq)
        logger.info(f"Running AI Technical & Fundamental analysis for {pair} in {mode} mode")
        try:
            # Compute market data context from the OHLCV already fetched
            market_data_ctx = compute_market_data_context(ohlcv, pair)

            events = await fetch_economic_calendar()
            # Compile events to text format for Groq context
            if events:
                news_text = "\n".join([
                    f"- {e['currency']} | {e['headline']} | Impact: {e['impact']} | Source: {e['source']} | Time: {e.get('event_time', 'N/A')}"
                    for e in events
                ])
            else:
                news_text = ""
                
            # Pass both technical + fundamental context to unified Groq analysis
            ai_sentiment_dict = await gemini_client.analyse_news_sentiment(
                pair,
                economic_context=news_text,
                market_data_context=market_data_ctx,
                h4_trend=ohlcv_data["h4_trend"],
                highest_high_24h=ohlcv_data["highest_high_24h"],
                lowest_low_24h=ohlcv_data["lowest_low_24h"],
                last_candle_type=ohlcv_data["last_candle_type"],
                is_rejection=ohlcv_data["is_rejection"],
                mode=mode
            )

            # Normalize keys for display
            if "reason" in ai_sentiment_dict and "summary" not in ai_sentiment_dict:
                ai_sentiment_dict["summary"] = ai_sentiment_dict["reason"]

            # Normalize bias values
            bias_val = str(ai_sentiment_dict.get("bias", "WAIT")).upper().strip()
            if "BUY" in bias_val or "LONG" in bias_val:
                ai_sentiment_dict["bias"] = "LONG"
            elif "SELL" in bias_val or "SHORT" in bias_val:
                ai_sentiment_dict["bias"] = "SHORT"
            else:
                ai_sentiment_dict["bias"] = "WAIT"

            # Normalize sentiment values
            sentiment_val = str(ai_sentiment_dict.get("sentiment", "NEUTRAL")).upper().strip()
            if "BULL" in sentiment_val:
                ai_sentiment_dict["sentiment"] = "BULLISH"
            elif "BEAR" in sentiment_val:
                ai_sentiment_dict["sentiment"] = "BEARISH"
            else:
                ai_sentiment_dict["sentiment"] = "NEUTRAL"

        except Exception as e:
            logger.error(f"Error in news fetching / AI Sentiment for {pair}: {e}")
            ai_sentiment_dict = {
                "sentiment": "NEUTRAL",
                "bias": "WAIT",
                "order_type": "MARKET EXECUTION",
                "entry_spot": entry_price,
                "reason": f"Failed to perform AI analysis due to unexpected error: {str(e)}"
            }

        ai_sentiment = ai_sentiment_dict.get("sentiment", "NEUTRAL")
        ai_bias = ai_sentiment_dict.get("bias", "WAIT")
        ai_summary = html.escape(ai_sentiment_dict.get("reason", ai_sentiment_dict.get("summary", "N/A")))
        order_type = ai_sentiment_dict.get("order_type", "MARKET EXECUTION")
        
        # Resolve entry spot
        entry_spot = ai_sentiment_dict.get("entry_spot")
        if entry_spot is None:
            entry_spot = entry_price
        else:
            try:
                entry_spot = float(entry_spot)
            except (ValueError, TypeError):
                entry_spot = entry_price

        # 6. Step D: Risk Management Sizing
        logger.info(f"Running risk management calculations for {pair} at entry {entry_spot}")
        # Resolve trading direction for risk engine based on AI bias and order type
        ai_bias_upper = str(ai_bias).upper()
        order_type_upper = str(order_type).upper()
        
        if "BUY" in ai_bias_upper or "LONG" in ai_bias_upper or "BUY" in order_type_upper or "LIMIT" in order_type_upper and "BUY" in order_type_upper:
            risk_direction = "LONG"
        elif "SELL" in ai_bias_upper or "SHORT" in ai_bias_upper or "SELL" in order_type_upper or "LIMIT" in order_type_upper and "SELL" in order_type_upper:
            risk_direction = "SHORT"
        else:
            # Fallback to tech direction if AI bias is WAIT/NEUTRAL
            risk_direction = tech_direction if tech_direction in {"LONG", "SHORT"} else "LONG"
        
        try:
            risk_package = await risk_engine.calculate(
                pair=pair,
                direction=risk_direction,
                entry_price=entry_spot,
                ohlcv=ohlcv,
                capital_usd=settings.default_capital_usd,
                risk_pct=settings.default_risk_pct,
                timeframe=timeframe,
                atr_period=settings.default_atr_period
            )
        except Exception as e:
            logger.error(f"Error in RiskManagementEngine for {pair}: {e}")
            await message.answer("❌ Terjadi kesalahan pada Risk Management Engine.")
            return

        # 7. Format & Send Response
        # Adjust signal display based on the resolved trading direction
        final_direction = risk_direction
        if ai_bias == "WAIT":
            bias_emoji = "🟡 WAIT/NEUTRAL"
            signal_color_text = "⏳ Menunggu Konfirmasi / Tidak Ada Sinyal Masuk"
        elif final_direction == "LONG":
            bias_emoji = "🟢 LONG / BUY"
            signal_color_text = "🚀 Bullish Setup"
        else:
            bias_emoji = "🔴 SHORT / SELL"
            signal_color_text = "📉 Bearish Setup"

        # Safe default or calculations formatting
        sl_display = f"{risk_package.sl_price:.5f}" if entry_price < 10 else f"{risk_package.sl_price:.2f}"
        tp1_display = f"{risk_package.tp1_price:.5f}" if entry_price < 10 else f"{risk_package.tp1_price:.2f}"
        tp2_display = f"{risk_package.tp2_price:.5f}" if entry_price < 10 else f"{risk_package.tp2_price:.2f}"
        entry_display = f"{entry_spot:.5f}" if entry_price < 10 else f"{entry_spot:.2f}"

        # If it's a WAIT regime or WAIT bias, lot sizing is computed but we warn that trade is not active
        lot_size_info = f"<b>{risk_package.lot_size} Lots</b>"
        if final_direction == "WAIT":
            lot_size_info += " <i>(Hanya untuk simulasi jika bias berubah)</i>"

        response_html = (
            f"📊 <b>LAPORAN ANALISIS TRADING AI - [{mode.upper()}] ({pair})</b> 📊\n"
            f"────────────────────────\n"
            f"📈 <b>Arah Sinyal (Bias):</b> {bias_emoji} ({signal_color_text})\n"
            f"⚡ <b>Timeframe:</b> <code>{timeframe}</code> | <b>Regime:</b> <code>{market_regime}</code>\n"
            f"🎯 <b>Entry Strategy:</b> {order_type} @ <code>{entry_display}</code>\n\n"
            
            f"🛡️ <b>Rencana Manajemen Risiko:</b>\n"
            f"• <b>Stop Loss (SL):</b> <code>{sl_display}</code> (~{risk_package.sl_pips} pips)\n"
            f"• <b>Take Profit 1 (TP1):</b> <code>{tp1_display}</code>\n"
            f"• <b>Take Profit 2 (TP2):</b> <code>{tp2_display}</code>\n"
            f"• <b>Ukuran Lot Aman:</b> {lot_size_info}\n"
            f"• <b>Modal Default:</b> <code>${settings.default_capital_usd:.2f}</code> (Resiko: {settings.default_risk_pct}%)\n\n"
            
            f"🔍 <b>Analisis Teknikal:</b>\n"
            f"• <b>Confluence Score:</b> <code>{confluence_score}%</code>\n"
            f"• <b>Support Terdekat:</b> <code>{supports_str}</code>\n"
            f"• <b>Resistance Terdekat:</b> <code>{resistances_str}</code>\n"
            f"• <b>Detail Teknikal:</b> <i>{html.escape(tech_reason)}</i>\n\n"
            
            f"🧠 <b>Analisis Fundamental (Gemini AI):</b>\n"
            f"• <b>Sentimen Berita:</b> <b>{ai_sentiment}</b>\n"
            f"• <b>Bias Fundamental:</b> <b>{ai_bias}</b>\n"
            f"• <b>Alasan AI Sentiment:</b>\n"
            f"<i>{ai_summary}</i>\n"
            f"────────────────────────\n"
            f"⚠️ <i>Disclaimer: Analisis ini bersifat informatif. Gunakan kebijaksanaan Anda sebelum mengeksekusi order.</i>"
        )
        
        # Log signal to database asynchronously
        try:
            await log_signal(
                user_id=user_id,
                pair=pair,
                timeframe=timeframe,
                direction=final_direction,
                entry_price=entry_price,
                sl_price=risk_package.sl_price,
                tp1_price=risk_package.tp1_price,
                tp2_price=risk_package.tp2_price,
                lot_size=risk_package.lot_size,
                atr_value=risk_package.atr_value,
                signal_source="PULL",
                ai_confidence=confluence_score,
                ai_reasoning=f"Technical: {tech_reason} | AI News: {ai_summary}"
            )
        except Exception as log_err:
            logger.error(f"Failed to log signal to DB: {log_err}")

        await message.answer(response_html, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Critical error in cmd_analisa handler: {str(e)}", exc_info=True)
        await message.answer("❌ Terjadi kesalahan sistem internal saat memproses analisis.")
