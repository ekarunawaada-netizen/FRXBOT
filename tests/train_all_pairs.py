import os
import sys
import json
import glob
import argparse
import asyncio
import pandas as pd

# Add project root directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.mass_backtester import run_backtest_simulation
from engines.risk_engine import load_pair_settings

def find_csv_files(pair: str) -> list:
    """Finds all CSV files in the data directory matching the symbol/pair name."""
    pattern = f"data/{pair.upper()}_*.csv"
    return glob.glob(pattern)

def save_pair_settings(settings: dict):
    """Saves the updated settings back to data/pair_settings.json."""
    try:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        settings_path = os.path.join(root_dir, "data", "pair_settings.json")
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)
        print(f"Successfully saved settings to {settings_path}")
    except Exception as e:
        print(f"Error saving settings: {e}")

async def optimize_pair_mode(csv_path: str, pair: str, mode: str) -> dict:
    """Performs grid search optimization for a single pair and mode."""
    print(f"\nOptimizing {pair.upper()} ({mode.upper()}) using {os.path.basename(csv_path)}...")
    
    # 1. Load CSV data once
    df = pd.read_csv(csv_path)
    df["time"] = pd.to_datetime(df["time"] if "time" in df.columns else df.iloc[:,0])
    df = df.set_index("time").sort_index()

    # Define search ranges
    sl_range = [1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.5]
    tp_range = [0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0]
    bep_range = [1.0, 1.5, 2.0]

    best_profit = -float('inf')
    best_win_rate = -1.0
    best_pf = -1.0
    best_params = None

    total_runs = len(sl_range) * len(tp_range) * len(bep_range)
    current_run = 0

    for sl_mult in sl_range:
        for tp_mult in tp_range:
            for bep_thresh in bep_range:
                current_run += 1
                if current_run % 20 == 0 or current_run == total_runs:
                    print(f"Progress: {current_run}/{total_runs} combinations evaluated...", end="\r")

                overrides = {
                    "sl_atr_multiplier": sl_mult,
                    "tp_atr_multiplier": tp_mult,
                    "bep_trigger_threshold": bep_thresh
                }

                # Run simulation (suppress printing of individual trades)
                results = await run_backtest_simulation(
                    df=df,
                    pair=pair,
                    mode=mode,
                    mock_ai=True,
                    max_trades=100,
                    start_idx=400,
                    override_settings=overrides,
                    verbose=False
                )

                profit = results["net_profit"]
                win_rate = results["win_rate"]
                pf = results["profit_factor"]

                # Scoring criteria: Highest Net Profit (primary), Win Rate (secondary), Profit Factor (tertiary)
                is_better = False
                if profit > best_profit:
                    is_better = True
                elif profit == best_profit:
                    if win_rate > best_win_rate:
                        is_better = True
                    elif win_rate == best_win_rate:
                        if pf > best_pf:
                            is_better = True

                if is_better:
                    best_profit = profit
                    best_win_rate = win_rate
                    best_pf = pf
                    best_params = overrides

    print(f"\nOptimization complete for {pair.upper()} ({mode.upper()}).")
    print(f"Best Params: SL={best_params['sl_atr_multiplier']} | TP={best_params['tp_atr_multiplier']} | BEP={best_params['bep_trigger_threshold']}")
    print(f"Best Results: Profit=${best_profit:.2f} | Win Rate={best_win_rate:.2f}% | Profit Factor={best_pf:.2f}")
    
    return best_params

async def main():
    parser = argparse.ArgumentParser(description="Automated Optimization Loop for FRXBOT Multipliers.")
    parser.add_argument("--pairs", type=str, default="XAUUSD,EURUSD", help="Comma-separated list of symbols to train (e.g. XAUUSD,EURUSD)")
    args = parser.parse_args()

    pairs_list = [p.strip().upper() for p in args.pairs.split(",") if p.strip()]
    
    # Load current settings JSON
    settings = load_pair_settings()
    
    for pair in pairs_list:
        csv_files = find_csv_files(pair)
        if not csv_files:
            print(f"Warning: No historical CSV files found in data/ for pair '{pair}'. Skipping...")
            continue
            
        for csv_path in csv_files:
            filename = os.path.basename(csv_path).upper()
            
            # Resolve mode from CSV file name or timeframe
            if "_M5_" in filename or "_M15_" in filename:
                mode = "scalping"
            elif "_H1_" in filename or "_H4_" in filename:
                mode = "swing"
            else:
                # Default fallback
                mode = "scalping"

            # Optimize parameters
            best_params = await optimize_pair_mode(csv_path, pair, mode)
            
            # Update settings structure
            if pair not in settings:
                settings[pair] = {}
            settings[pair][mode] = best_params

    # Save to disk
    save_pair_settings(settings)

if __name__ == "__main__":
    asyncio.run(main())
