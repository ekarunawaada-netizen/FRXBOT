import os
import sys
import argparse
import asyncio
import pandas as pd

# Add project root directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.mass_backtester import run_backtest_simulation
from core.database_manager import init_db, save_optimized_parameters

# Explicit timeframe-to-bars file resolution used instead of brute glob scanning.

async def optimize_pair_mode(csv_path: str, pair: str, mode: str) -> dict:
    """Performs grid search optimization for a single pair and mode."""
    print(f"\nOptimizing {pair.upper()} ({mode.upper()}) using {os.path.basename(csv_path)}...")
    
    # 1. Load CSV data once
    df = pd.read_csv(csv_path)
    df["time"] = pd.to_datetime(df["time"] if "time" in df.columns else df.iloc[:,0])
    df = df.set_index("time").sort_index()

    # Define search ranges
    sl_range = [1.5, 2.0, 2.5]
    tp_range = [1.0, 1.5, 2.0, 2.5, 3.0]
    bep_range = [1.0, 1.5, 2.0]

    best_score = -float('inf')
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

                # Enforce minimum Risk-to-Reward (RR) ratio constraint
                # RR = TP1_Distance / SL_Distance where TP1_Distance = atr * tp_multiplier * 0.8
                # and SL_Distance = atr * sl_multiplier.
                tp1_distance = tp_mult * 0.8
                sl_distance = sl_mult
                rr = tp1_distance / sl_distance

                if rr < 1.0:
                    continue

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

                # Handle infinity or NaN Profit Factor cleanly
                pf_clean = pf
                if pf == float('inf'):
                    pf_clean = 99.0
                elif pd.isna(pf):
                    pf_clean = 0.0

                # Multi-objective balanced fitness score calculation
                # Balanced_Score = (Net_Profit * Profit_Factor) * (1 if Win_Rate >= 0.50 else 0.5)
                win_rate_fraction = win_rate / 100.0
                win_rate_multiplier = 1.0 if win_rate_fraction >= 0.50 else 0.5
                balanced_score = (profit * pf_clean) * win_rate_multiplier

                is_better = False
                if balanced_score > best_score:
                    is_better = True
                elif balanced_score == best_score:
                    # Tie-breakers
                    if profit > best_profit:
                        is_better = True
                    elif profit == best_profit:
                        if win_rate > best_win_rate:
                            is_better = True
                        elif win_rate == best_win_rate:
                            if pf_clean > best_pf:
                                is_better = True

                if is_better:
                    best_score = balanced_score
                    best_profit = profit
                    best_win_rate = win_rate
                    best_pf = pf_clean
                    best_params = overrides

    print(f"\nOptimization complete for {pair.upper()} ({mode.upper()}).")
    if best_params:
        print(f"Best Params: SL={best_params['sl_atr_multiplier']} | TP={best_params['tp_atr_multiplier']} | BEP={best_params['bep_trigger_threshold']}")
        print(f"Best Results: Profit=${best_profit:.2f} | Win Rate={best_win_rate:.2f}% | Profit Factor={best_pf:.2f}")
    else:
        print("No valid parameter combination met the Risk-to-Reward filter.")

    # Build structured results dictionary alongside params for SQLite persistence
    best_results = {
        "win_rate": best_win_rate,
        "profit_factor": best_pf,
        "total_profit": best_profit
    } if best_params else None

    return best_params, best_results

async def main():
    parser = argparse.ArgumentParser(description="Automated Optimization Loop for FRXBOT Multipliers.")
    parser.add_argument("--pairs", type=str, default="XAUUSD,EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,BTCUSD", help="Comma-separated list of symbols to train")
    args = parser.parse_args()

    pairs_list = [p.strip().upper() for p in args.pairs.split(",") if p.strip()]

    # Initialize the SQLite brain database before training begins
    init_db()

    # Static file lookup factory aligned with cloud_data_scraper overwrite tactic.
    # Each mode maps to its static filename suffix and explicit DB timeframe label.
    modes_config = {
        "scalping":  {"suffix": "M5_max_bars.csv",  "timeframe": "M5"},
        "intraday":  {"suffix": "M30_max_bars.csv", "timeframe": "M30"},
        "swing":     {"suffix": "H1_max_bars.csv",  "timeframe": "H1"}
    }

    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    for pair in pairs_list:
        pair_upper = pair.upper()
        for mode, cfg in modes_config.items():
            suffix = cfg["suffix"]
            timeframe_label = cfg["timeframe"]

            # Construct explicit file path using static naming convention
            target_file = os.path.join(root_dir, "data", f"{pair_upper}_{suffix}")
            rel_path = os.path.join("data", f"{pair_upper}_{suffix}")

            # Fail-fast check: skip gracefully if required big-data file is missing
            if not os.path.exists(target_file):
                print(f"[ERROR] Required Big-Data file {rel_path} not found. Skipping optimization for this mode.")
                continue

            # Optimize parameters
            best_params, best_results = await optimize_pair_mode(target_file, pair_upper, mode)

            # Persist optimal parameters into SQLite brain database
            if best_params and best_results:
                # Remap keys to match database_manager schema expectation
                # Explicitly set the correct timeframe label per mode (M5 for scalping, H1 for swing)
                db_params = {
                    "timeframe": timeframe_label,
                    "sl_atr_multiplier": best_params["sl_atr_multiplier"],
                    "tp_atr_multiplier": best_params["tp_atr_multiplier"],
                    "bep_multiplier": best_params["bep_trigger_threshold"],
                }

                success = save_optimized_parameters(
                    symbol=pair_upper,
                    mode=mode,
                    params_dict=db_params,
                    results_dict=best_results
                )

                if success:
                    print(f"[DB SUCCESS] Successfully saved and locked optimal {mode} parameters for {pair_upper} inside data/frxbot_brain.db")
                else:
                    print(f"[DB ERROR] Failed to persist {mode} parameters for {pair_upper}. Check logs.")


if __name__ == "__main__":
    asyncio.run(main())

