import html
import logging
import sqlite3
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
from core.database_manager import get_active_parameters, get_latest_regime, DB_PATH, _db_lock

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

def get_market_sentiment(symbol: str) -> dict:
    """
    Fetches retail sentiment for the requested symbol.
    Defaults to 50/50 if the table or symbol is missing.
    """
    with _db_lock:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT long_percentage, short_percentage FROM market_sentiment WHERE UPPER(symbol) = ?;",
                (symbol.upper(),)
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                return dict(row)
        except Exception as e:
            logger.error(f"Database error fetching retail sentiment for {symbol}: {e}")
    return {"long_percentage": 50.0, "short_percentage": 50.0}

def get_intermarket_correlation_data() -> dict:
    """
    Fetches daily price change metrics for DXY and US10Y.
    Defaults to 0.0% changes if records are missing.
    """
    data = {
        "DXY": {"current_price": 0.0, "daily_change_percent": 0.0},
        "US10Y": {"current_price": 0.0, "daily_change_percent": 0.0}
    }
    with _db_lock:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT ticker, current_price, daily_change_percent FROM intermarket_correlation WHERE ticker IN ('DXY', 'US10Y');"
            )
            rows = cursor.fetchall()
            conn.close()
            for row in rows:
                ticker = row["ticker"]
                data[ticker] = {
                    "current_price": row["current_price"],
                    "daily_change_percent": row["daily_change_percent"]
                }
        except Exception as e:
            logger.error(f"Database error fetching intermarket correlation: {e}")
    return data

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
    # Supported symbols and modes for the help menu
    SUPPORTED_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"]
    SUPPORTED_MODES = ["scalping", "intraday", "swing"]

    args_str = command.args
    if not args_str:
        symbols_list = "  ".join([f"<code>{s}</code>" for s in SUPPORTED_SYMBOLS])
        await message.answer(
            f"📋 <b>FRXBOT Quant Analyzer — Panduan Cepat</b>\n"
            f"────────────────────────\n"
            f"<b>Format:</b> <code>/analisa [SYMBOL] [MODE]</code>\n\n"
            f"🪙 <b>Simbol Aktif:</b>\n{symbols_list}\n\n"
            f"⚙️ <b>Mode Trading:</b>\n"
            f"  <code>scalping</code>  — M5 ultra-cepat\n"
            f"  <code>intraday</code> — M30 intra-hari\n"
            f"  <code>swing</code>    — H1 posisi menengah\n\n"
            f"<b>Contoh:</b>\n"
            f"  <code>/analisa XAUUSD swing</code>\n"
            f"  <code>/analisa EURUSD scalping</code>\n"
            f"  <code>/analisa GBPUSD intraday</code>\n"
            f"────────────────────────\n"
            f"💡 <i>Jika mode tidak ditentukan, default = swing</i>",
            parse_mode=ParseMode.HTML
        )
        return

    parts = [p.strip() for p in args_str.split() if p.strip()]
    pair = parts[0].upper()

    mode = "swing"  # default mode
    if len(parts) >= 2:
        mode_arg = parts[1].lower()
        if mode_arg in {"sc", "scalping"}:
            mode = "scalping"
        elif mode_arg in {"id", "intraday"}:
            mode = "intraday"
        elif mode_arg in {"sw", "swing"}:
            mode = "swing"

    # ── Quant Dashboard: Dual-Table SQLite Queries ────────────────
    # Query 1: Trained optimization parameters from pair_optimized_rules
    db_params = get_active_parameters(pair, mode)
    if db_params:
        sl_mult = db_params["sl_atr_multiplier"]
        tp_mult = db_params["tp_atr_multiplier"]
        bep_mult = db_params["bep_multiplier"]
        trained_wr = db_params.get("win_rate", 0.0)
        trained_pf = db_params.get("profit_factor", 0.0)
        param_source = "TRAINED"
    else:
        # Safe-mode production fallback (guarantees RR >= 1.0)
        sl_mult, tp_mult, bep_mult = 2.0, 2.0, 1.5
        trained_wr, trained_pf = 0.0, 0.0
        param_source = "SAFE-MODE"
        logger.warning(f"No trained params for {pair} ({mode}). Using safe-mode defaults.")

    # Query 2: Latest market regime from market_regimes_history
    regime_data = get_latest_regime(pair)
    if regime_data:
        regime_state = regime_data["market_state"]
        regime_atr = regime_data.get("calculated_atr", 0.0)
        regime_std = regime_data.get("standard_deviation", 0.0)
    else:
        regime_state = "UNKNOWN"
        regime_atr, regime_std = 0.0, 0.0

    # Query 3: Retail Sentiment Ingestion Metrics
    sentiment = get_market_sentiment(pair)
    long_percentage = sentiment["long_percentage"]
    short_percentage = sentiment["short_percentage"]
    
    if long_percentage > 60.0:
        sentiment_label = " (Retail Trapped LONG - Bearish Bias)"
    elif short_percentage > 60.0:
        sentiment_label = " (Retail Trapped SHORT - Bullish Bias)"
    else:
        sentiment_label = " (Balanced Sentiment)"

    # Query 4: Intermarket Correlation Data
    intermarket_data = get_intermarket_correlation_data()
    dxy_change = intermarket_data["DXY"]["daily_change_percent"]
    us10y_change = intermarket_data["US10Y"]["daily_change_percent"]

    # Regime display emoji mapping
    regime_emoji_map = {
        "HIGH_VOLATILITY": "🔴 HIGH VOLATILITY",
        "TRENDING": "🟢 TRENDING",
        "NORMAL": "🟡 NORMAL/RANGING",
        "UNKNOWN": "⚪ UNKNOWN"
    }
    regime_display = regime_emoji_map.get(regime_state, f"⚪ {regime_state}")

    # Format performance metrics display
    wr_display = f"{trained_wr:.2f}%" if trained_wr > 0 else "N/A"
    pf_display = f"{trained_pf:.2f}" if trained_pf > 0 else "N/A"

    # Build the Quant Dashboard header message
    quant_dashboard = (
        f"🏦 <b>FRXBOT QUANT DASHBOARD</b>\n"
        f"════════════════════════════\n\n"
        f"🪙 <b>Asset:</b> <code>{pair}</code> | <b>Mode:</b> <code>{mode.upper()}</code>\n"
        f"☁️ <b>Market Regime:</b> {regime_display}\n"
        f"   ATR: <code>{regime_atr:.6f}</code> | StdDev: <code>{regime_std:.6f}</code>\n\n"
        f"👥 Retail Sentiment: {long_percentage}% BUY | {short_percentage}% SELL{sentiment_label}\n\n"
        f"🎯 <b>Optimal Multipliers</b> <i>({param_source})</i>:\n"
        f"   SL: <code>{sl_mult}</code> | TP: <code>{tp_mult}</code> | BEP: <code>{bep_mult}</code>\n\n"
        f"📈 <b>Training Performance:</b>\n"
        f"   Win Rate: <code>{wr_display}</code> | Profit Factor: <code>{pf_display}</code>\n\n"
        f"💵 Global Macro: DXY ({dxy_change:+.4f}%) | US10Y ({us10y_change:+.4f}%)\n"
        f"════════════════════════════\n"
        f"⏳ Menjalankan analisis <b>[{mode.upper()}]</b> untuk <b>{pair}</b>..."
    )
    await message.answer(quant_dashboard, parse_mode=ParseMode.HTML)

    try:
        # 3. Step A: Price Data Retrieval
        # Resolve timeframe from mode: scalping→M5, intraday→M30, swing→H1
        timeframe_map = {"scalping": "M5", "intraday": "M30", "swing": "H1"}
        timeframe = timeframe_map.get(mode, "H1")

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

        # 5. Step C: AI Analysis (Technical from live data + Fundamental from calendar -> Groq/Gemini)
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
                
            # Pass both technical + fundamental context to unified Groq/Gemini analysis
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
                atr_period=settings.default_atr_period,
                mode=mode
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
