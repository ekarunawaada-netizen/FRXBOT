import os
import sys
import json
import argparse
import asyncio
import pandas as pd
import numpy as np
import html

# Add project root directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.gemini_client import GeminiAnalyseClient
from engines.technical_engine import TechnicalEngine
from engines.risk_engine import RiskManagementEngine
from data.price_fetcher import compute_market_data_context

async def main():
    parser = argparse.ArgumentParser(description="AI Model Trainer & Evaluator - Mass Historical Backtester.")
    parser.add_argument("--csv", type=str, required=True, help="Path to historical CSV file.")
    parser.add_argument("--mode", type=str, default="swing", choices=["swing", "scalping"], help="Execution mode (swing or scalping)")
    parser.add_argument("--mock-ai", action="store_true", help="Use mock AI responses instead of calling Groq API.")
    parser.add_argument("--max-trades", type=int, default=50, help="Maximum number of simulated trades to execute.")
    parser.add_argument("--start-idx", type=int, default=400, help="Starting index in the CSV to allow indicator calculation history.")
    args = parser.parse_args()

    # 1. Load CSV
    print(f"Loading dataset: {args.csv}")
    if not os.path.exists(args.csv):
        print(f"Error: CSV file not found: {args.csv}")
        sys.exit(1)
        
    df = pd.read_csv(args.csv)
    df["time"] = pd.to_datetime(df["time"] if "time" in df.columns else df.iloc[:,0])
    df = df.set_index("time").sort_index()

    print(f"Loaded {len(df)} bars of historical data.")
    
    # Instantiate engines
    tech_engine = TechnicalEngine()
    risk_engine = RiskManagementEngine()
    gemini_client = GeminiAnalyseClient()

    pair = os.path.basename(args.csv).split("_")[0]
    timeframe = "M5" if args.mode == "scalping" else "H1"
    
    # Backtest parameters
    pending_limit_bars = 48 if args.mode == "scalping" else 24
    max_trade_duration = 120
    pip_size = risk_engine.PIP_SIZES.get(pair, 0.0001)

    # Tracking lists
    pending_orders = []
    active_trades = []
    closed_trades = []
    filtered_signals_count = 0

    print(f"Starting moving-window simulation on {pair} ({args.mode.upper()})...")
    print(f"Mock AI: {args.mock_ai} | Max Trades: {args.max_trades} | Start Index: {args.start_idx}")

    # Main moving window loop
    for i in range(args.start_idx, len(df)):
        # Stop generating new signals if we reached max trades
        total_trade_slots = len(closed_trades) + len(active_trades) + len(pending_orders)
        can_trade = total_trade_slots < args.max_trades

        slice_df = df.iloc[:i]
        current_row = df.iloc[i]
        current_time = df.index[i]
        
        # 1. Update pending orders
        still_pending = []
        for trade in pending_orders:
            # Check expiration
            if i - trade["open_idx"] > pending_limit_bars:
                trade["status"] = "CANCELLED"
                trade["outcome"] = "CANCELLED"
                trade["exit_time"] = current_time
                closed_trades.append(trade)
                continue
            
            # Check trigger
            triggered = False
            entry_spot = trade["entry_spot"]
            if trade["direction"] == "LONG":
                if current_row["Low"] <= entry_spot:
                    triggered = True
            else: # SHORT
                if current_row["High"] >= entry_spot:
                    triggered = True
                    
            if triggered:
                trade["status"] = "ACTIVE"
                trade["fill_idx"] = i
                trade["fill_time"] = current_time
                active_trades.append(trade)
                print(f"[{current_time}] ORDER TRIGGERED: {trade['direction']} {pair} at {entry_spot}")
            else:
                still_pending.append(trade)
        pending_orders = still_pending

        # 2. Update active trades
        still_active = []
        for trade in active_trades:
            # Check SL/TP hits
            sl_hit = False
            tp_hit = False
            
            if trade["direction"] == "LONG":
                if current_row["Low"] <= trade["sl_price"]:
                    sl_hit = True
                if current_row["High"] >= trade["tp_price"]:
                    tp_hit = True
            else: # SHORT
                if current_row["High"] >= trade["sl_price"]:
                    sl_hit = True
                if current_row["Low"] <= trade["tp_price"]:
                    tp_hit = True
                    
            if sl_hit and tp_hit:
                # Conservative: assume SL hit first
                sl_hit = True
                tp_hit = False
                
            if sl_hit:
                trade["status"] = "CLOSED"
                trade["exit_price"] = trade["sl_price"]
                trade["exit_time"] = current_time
                trade["pnl"] = -trade["risk_package"].risk_amount_usd
                trade["outcome"] = "SL"
                closed_trades.append(trade)
                print(f"[{current_time}] HIT SL: {trade['direction']} {pair} PnL: {trade['pnl']:.2f} USD")
            elif tp_hit:
                trade["status"] = "CLOSED"
                trade["exit_price"] = trade["tp_price"]
                trade["exit_time"] = current_time
                trade["pnl"] = trade["risk_package"].risk_amount_usd * 2.0
                trade["outcome"] = "TP"
                closed_trades.append(trade)
                print(f"[{current_time}] HIT TP: {trade['direction']} {pair} PnL: {trade['pnl']:.2f} USD")
            elif i - trade["fill_idx"] > max_trade_duration:
                # Time exit
                trade["status"] = "CLOSED"
                exit_price = float(current_row["Close"])
                trade["exit_price"] = exit_price
                trade["exit_time"] = current_time
                entry_spot = trade["entry_spot"]
                
                # Proportional PnL
                if trade["direction"] == "LONG":
                    trade["pnl"] = trade["risk_package"].risk_amount_usd * (exit_price - entry_spot) / (entry_spot - trade["sl_price"])
                else:
                    trade["pnl"] = trade["risk_package"].risk_amount_usd * (entry_spot - exit_price) / (trade["sl_price"] - entry_spot)
                    
                trade["outcome"] = "TIME_EXIT"
                closed_trades.append(trade)
                print(f"[{current_time}] TIME OUT EXIT: {trade['direction']} {pair} at {exit_price} PnL: {trade['pnl']:.2f} USD")
            else:
                still_active.append(trade)
        active_trades = still_active

        # 3. Check for new trade signals
        if not can_trade:
            continue

        # Slice timeframes
        if args.mode == "scalping":
            exec_df = slice_df.tail(100)
            macro_df = slice_df.tail(310).resample("15min").agg({
                "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
            }).dropna().tail(70)
            lookback_bars = 12
        else:
            exec_df = slice_df.tail(100)
            macro_df = slice_df.tail(380).resample("4h").agg({
                "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
            }).dropna().tail(70)
            lookback_bars = 24

        # Verify minimal bar lengths
        if len(exec_df) < 50 or len(macro_df) < 50:
            continue

        # Get Technical Bias
        tech_bias = await tech_engine.generate_technical_bias(exec_df, mode=args.mode)
        tech_direction = tech_bias["direction"]
        
        # Calculate Macro Trend
        macro_close = macro_df["Close"].astype(float)
        macro_ema50 = macro_close.ewm(span=50, adjust=False).mean()
        macro_trend = "BULLISH" if macro_close.iloc[-1] > macro_ema50.iloc[-1] else "BEARISH"

        if tech_direction == "WAIT":
            continue

        # Macro Trend Filtering
        if (tech_direction == "LONG" and macro_trend == "BEARISH") or (tech_direction == "SHORT" and macro_trend == "BULLISH"):
            filtered_signals_count += 1
            continue

        # Fetch AI Bias
        entry_price = float(exec_df["Close"].iloc[-1])
        if args.mock_ai:
            ai_result = {
                "sentiment": "BULLISH" if tech_direction == "LONG" else "BEARISH",
                "bias": "LONG" if tech_direction == "LONG" else "SHORT",
                "order_type": "MARKET EXECUTION",
                "entry_spot": entry_price,
                "reason": "[MOCK AI] Aligned with technical trend."
            }
        else:
            # Recreate structural params
            highest_high = float(exec_df["High"].tail(lookback_bars).max())
            lowest_low = float(exec_df["Low"].tail(lookback_bars).min())
            
            last_candle = exec_df.iloc[-1]
            o_val = float(last_candle["Open"])
            h_val = float(last_candle["High"])
            l_val = float(last_candle["Low"])
            c_val = float(last_candle["Close"])
            
            last_candle_type = "BULLISH" if c_val > o_val else "BEARISH"
            total_range = h_val - l_val
            is_rejection = False
            if total_range > 0:
                body_max = max(o_val, c_val)
                body_min = min(o_val, c_val)
                is_rejection = ((h_val - body_max) / total_range > 0.4) or ((body_min - l_val) / total_range > 0.4)

            market_data_ctx = compute_market_data_context(exec_df, pair)
            
            print(f"[{current_time}] Sending window to AI...")
            try:
                ai_result = await gemini_client.analyse_news_sentiment(
                    pair=pair,
                    economic_context="",
                    market_data_context=market_data_ctx,
                    h4_trend=macro_trend,
                    highest_high_24h=highest_high,
                    lowest_low_24h=lowest_low,
                    last_candle_type=last_candle_type,
                    is_rejection=is_rejection,
                    mode=args.mode
                )
            except Exception as e:
                print(f"AI error at {current_time}: {e}")
                continue

        # Process AI signal
        ai_bias = str(ai_result.get("bias", "WAIT")).upper().strip()
        if "BUY" in ai_bias or "LONG" in ai_bias:
            ai_bias = "LONG"
        elif "SELL" in ai_bias or "SHORT" in ai_bias:
            ai_bias = "SHORT"
        else:
            ai_bias = "WAIT"

        if ai_bias == "WAIT":
            continue

        # AI Macro Trend Filter
        if (ai_bias == "LONG" and macro_trend == "BEARISH") or (ai_bias == "SHORT" and macro_trend == "BULLISH"):
            filtered_signals_count += 1
            continue

        order_type = ai_result.get("order_type", "MARKET EXECUTION")
        entry_spot = float(ai_result.get("entry_spot", entry_price))

        # Risk Package
        try:
            risk_package = await risk_engine.calculate(
                pair=pair,
                direction=ai_bias,
                entry_price=entry_spot,
                ohlcv=exec_df,
                capital_usd=5000.0,
                risk_pct=1.0,
                timeframe=timeframe
            )
        except Exception as e:
            print(f"Risk calculations failed: {e}")
            continue

        # Create Trade
        trade = {
            "pair": pair,
            "mode": args.mode,
            "direction": ai_bias,
            "order_type": order_type,
            "entry_spot": entry_spot,
            "sl_price": risk_package.sl_price,
            "tp_price": risk_package.tp2_price,
            "risk_package": risk_package,
            "status": "PENDING",
            "open_time": current_time,
            "open_idx": i,
            "fill_time": None,
            "fill_idx": None,
            "exit_time": None,
            "exit_price": None,
            "pnl": 0.0,
            "outcome": None
        }

        if order_type == "MARKET EXECUTION":
            trade["status"] = "ACTIVE"
            trade["fill_idx"] = i
            trade["fill_time"] = current_time
            active_trades.append(trade)
            print(f"[{current_time}] EXECUTED MARKET ORDER: {ai_bias} {pair} at {entry_spot}")
        else:
            pending_orders.append(trade)
            print(f"[{current_time}] PLACED LIMIT ORDER: {order_type} {pair} at {entry_spot}")

    # Complete the backtest simulation: close remaining pending/active trades at final bar
    final_time = df.index[-1]
    final_close = float(df["Close"].iloc[-1])
    
    for trade in pending_orders:
        trade["status"] = "EXPIRED"
        trade["outcome"] = "CANCELLED"
        trade["exit_time"] = final_time
        closed_trades.append(trade)
        
    for trade in active_trades:
        trade["status"] = "CLOSED"
        trade["exit_price"] = final_close
        trade["exit_time"] = final_time
        entry_spot = trade["entry_spot"]
        if trade["direction"] == "LONG":
            trade["pnl"] = trade["risk_package"].risk_amount_usd * (final_close - entry_spot) / (entry_spot - trade["sl_price"])
        else:
            trade["pnl"] = trade["risk_package"].risk_amount_usd * (entry_spot - final_close) / (trade["sl_price"] - entry_spot)
        trade["outcome"] = "TIME_EXIT"
        closed_trades.append(trade)

    # 4. Display Stats Dashboard
    filled_trades = [t for t in closed_trades if t["outcome"] != "CANCELLED"]
    total_trades = len(filled_trades)
    
    wins = [t for t in filled_trades if t["pnl"] > 0]
    losses = [t for t in filled_trades if t["pnl"] < 0]
    
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    
    gross_profit = sum([t["pnl"] for t in wins])
    gross_loss = abs(sum([t["pnl"] for t in losses]))
    
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)

    print("\n" + "="*50)
    print("           HISTORICAL MASS BACKTEST REPORT")
    print("="*50)
    print(f"Market Instrument : {pair}")
    print(f"Analysis Mode     : {args.mode.upper()}")
    print(f"Dataset Size      : {len(df)} bars")
    print(f"Total Placed      : {len(closed_trades)}")
    print(f"Total Filled      : {total_trades}")
    print(f"Win Rate %        : {win_rate:.2f}% ({len(wins)} W / {len(losses)} L)")
    print(f"Profit Factor     : {profit_factor:.2f}")
    print(f"Gross Profit      : {gross_profit:.2f} USD")
    print(f"Gross Loss        : {gross_loss:.2f} USD")
    print(f"Net Profit        : {gross_profit - gross_loss:.2f} USD")
    print(f"Macro Filtered    : {filtered_signals_count} signals")
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
