import os
import sys
import argparse
import pandas as pd
from datetime import datetime

# Add the root directory of the project to PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    parser = argparse.ArgumentParser(description="Download historical bars from MetaTrader 5 and save to CSV.")
    parser.add_argument("--pair", type=str, default="XAUUSD", help="Market symbol/pair (e.g. XAUUSD, EURUSD)")
    parser.add_argument("--timeframe", type=str, default="M5", help="Timeframe (M1, M5, M15, M30, H1, H4, D1)")
    parser.add_argument("--bars", type=int, default=20000, help="Number of bars to fetch")
    args = parser.parse_args()

    # 1. Load MetaTrader5 dynamically
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("Error: MetaTrader5 library is not installed. Install it using 'pip install MetaTrader5'.")
        sys.exit(1)

    # 2. Map Timeframe
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    
    tf_upper = args.timeframe.upper()
    mt5_tf = tf_map.get(tf_upper)
    if mt5_tf is None:
        print(f"Error: Timeframe '{args.timeframe}' is not supported. Supported: {list(tf_map.keys())}")
        sys.exit(1)

    # 3. Initialize MT5 Connection
    print("Initializing MetaTrader 5...")
    if not mt5.initialize():
        print(f"Error: mt5.initialize() failed. Error code: {mt5.last_error()}")
        sys.exit(1)

    try:
        # Check symbol availability
        symbol = args.pair.upper()
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            print(f"Warning: Symbol '{symbol}' not found in MT5 Market Watch. Attempting to select...")
            if not mt5.symbol_select(symbol, True):
                print(f"Error: Failed to select symbol '{symbol}'. Error code: {mt5.last_error()}")
                sys.exit(1)
        
        # 4. Fetch Rates
        print(f"Fetching {args.bars} bars of {symbol} ({tf_upper}) from MT5...")
        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, args.bars)
        
        if rates is None or len(rates) == 0:
            print(f"Error: Failed to copy rates from MT5. Error code: {mt5.last_error()}")
            sys.exit(1)

        # 5. Format & Save
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.set_index("time")
        
        df = df.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "tick_volume": "Volume"
        })
        
        # Select required columns
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        
        # Ensure data folder exists
        os.makedirs("data", exist_ok=True)
        filename = f"data/{symbol}_{tf_upper}_{args.bars}_bars.csv"
        df.to_csv(filename)
        
        print(f"Successfully downloaded {len(df)} bars of {symbol} ({tf_upper}).")
        print(f"Data saved to file: {os.path.abspath(filename)}")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)
    finally:
        # 6. Shutdown MT5
        mt5.shutdown()

if __name__ == "__main__":
    main()
