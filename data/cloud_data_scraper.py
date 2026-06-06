import os
import io
import sys
import gzip
import zipfile
import argparse
import requests
import pandas as pd
from tqdm import tqdm

# Add project root directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Target Assets — Expanded institutional universe (Forex + Commodities + Crypto)
ASSETS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "BTCUSD"]

# Base URL for ejtraderLabs repository
BASE_URL = "https://raw.githubusercontent.com/ejtraderLabs/historical-data/main/"

def decompress_stream(content: bytes) -> bytes:
    """Decompress zip or gzip byte streams on-the-fly based on magic numbers."""
    # ZIP magic number: PK\x03\x04
    if content.startswith(b'PK\x03\x04'):
        print("Detected ZIP archive. Decompressing on-the-fly...")
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            for filename in z.namelist():
                if filename.endswith('.csv'):
                    return z.read(filename)
        raise ValueError("No CSV file found inside the downloaded ZIP archive.")
    
    # GZIP magic number: \x1f\x8b
    elif content.startswith(b'\x1f\x8b'):
        print("Detected GZIP archive. Decompressing on-the-fly...")
        return gzip.decompress(content)
    
    # Raw uncompressed content
    return content

def download_file(url: str, desc: str) -> bytes:
    """Downloads a file streaming bytes with an interactive tqdm progress bar."""
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
    
    total_size = int(response.headers.get('content-length', 0))
    block_size = 8192  # 8 KB chunks
    
    progress_bar = tqdm(
        total=total_size, 
        unit='iB', 
        unit_scale=True, 
        desc=desc,
        leave=True
    )
    
    chunks = []
    for data in response.iter_content(block_size):
        progress_bar.update(len(data))
        chunks.append(data)
    
    progress_bar.close()
    return b"".join(chunks)

def normalize_dataframe(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Normalizes DataFrame schema, timestamps, and dynamically rescales prices."""
    # Normalize headers case-insensitively
    col_mapping = {}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in ['date', 'time', 'timestamp', 'datetime']:
            col_mapping[col] = 'time'
        elif col_lower == 'open':
            col_mapping[col] = 'Open'
        elif col_lower == 'high':
            col_mapping[col] = 'High'
        elif col_lower == 'low':
            col_mapping[col] = 'Low'
        elif col_lower == 'close':
            col_mapping[col] = 'Close'
        elif col_lower in ['tick_volume', 'volume', 'vol']:
            col_mapping[col] = 'Volume'
            
    df = df.rename(columns=col_mapping)
    
    # Ensure all required columns are present
    required_cols = ['time', 'Open', 'High', 'Low', 'Close', 'Volume']
    for col in required_cols:
        if col not in df.columns:
            raise KeyError(f"Missing required normalized column '{col}' in downloaded data.")
            
    df = df[required_cols]
    
    # Clean and parse time to ISO-8601 format
    df['time'] = pd.to_datetime(df['time'])
    df['time'] = df['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Dynamic price rescaling based on decimal positions
    first_open = float(df['Open'].iloc[0])
    scale = 1.0
    symbol_upper = symbol.upper()
    
    if symbol_upper in ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF"]:
        # Standard Forex pairs are around 0.5 - 2.0.
        # If the price is > 100, it is scaled up by 100,000.
        if first_open > 100.0:
            scale = 100000.0
    elif symbol_upper == "USDJPY":
        # USDJPY is around 80.0 - 160.0.
        # If the price is > 1000, it is scaled up by 1,000.
        if first_open > 1000.0:
            scale = 1000.0
    elif symbol_upper == "XAUUSD":
        # XAUUSD is around 1000.0 - 2500.0.
        # If the price is > 10000, it is scaled up by 100.
        if first_open > 10000.0:
            scale = 100.0
    elif symbol_upper == "BTCUSD":
        # BTCUSD is around 20,000 - 100,000.
        # If the price is > 1,000,000, it is scaled up by 100.
        if first_open > 1000000.0:
            scale = 100.0
            
    if scale != 1.0:
        print(f"Rescaling prices for {symbol_upper} by dividing by {scale}...")
        for col in ['Open', 'High', 'Low', 'Close']:
            df[col] = df[col] / scale
            
    return df

def run_scraper(target_pairs=None, single_timeframe=None):
    """Executes the cloud mirroring and scraping process."""
    os.makedirs("data", exist_ok=True)
    pairs = target_pairs if target_pairs else ASSETS
    
    # Define timeframe mappings (Ultra-Scale Big Data volume targets)
    # M5  maps to native m15 from the mirror — 200,000 bars for deep scalping
    # M30 maps to native m30 from the mirror — 100,000 bars for intraday
    # H1  maps to native h1  from the mirror — 100,000 bars for swing depth
    timeframes = {
        'M5': {
            'native': 'm15',
            'bars': 200000
        },
        'M30': {
            'native': 'm30',
            'bars': 100000
        },
        'H1': {
            'native': 'h1',
            'bars': 100000
        }
    }
    
    if single_timeframe:
        if single_timeframe.upper() not in timeframes:
            print(f"Error: Timeframe '{single_timeframe}' not supported. Choose M5, M30, or H1.")
            sys.exit(1)
        tf_keys = [single_timeframe.upper()]
    else:
        tf_keys = list(timeframes.keys())
        
    for symbol in pairs:
        symbol = symbol.upper()
        for tf in tf_keys:
            cfg = timeframes[tf]
            native_tf = cfg['native']
            required_bars = cfg['bars']
            
            # Construct download URL
            url = f"{BASE_URL}{symbol}/{symbol}{native_tf}.csv"
            # Static overwrite tactic: fixed filename eliminates workspace file clutter
            filename = f"data/{symbol}_{tf}_max_bars.csv"
            
            desc = f"{symbol} {tf} ({native_tf} native)"
            print(f"\nProcessing: {desc}")
            print(f"Downloading from: {url}")
            
            try:
                # 1. Fetch byte stream
                raw_bytes = download_file(url, desc=desc)
                
                # 2. Decompress if zipped/gzipped
                decompressed_bytes = decompress_stream(raw_bytes)
                
                # 3. Load into Pandas
                df = pd.read_csv(io.BytesIO(decompressed_bytes))
                
                # 4. Normalize schema and prices
                df = normalize_dataframe(df, symbol)
                
                # 5. Sort chronologically to make sure latest is at the bottom
                df['time_dt'] = pd.to_datetime(df['time'])
                df = df.sort_values('time_dt').drop(columns=['time_dt'])
                
                # 6. Slice exactly the latest N bars
                df_sliced = df.tail(required_bars)
                actual_bars = len(df_sliced)
                
                # 7. Save output
                df_sliced.to_csv(filename, index=False)
                print(f"Successfully saved {actual_bars} bars to {filename}")
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    print(f"Warning: Data not found (404) for {symbol} on native {native_tf}. Skipping...")
                else:
                    print(f"Warning: HTTP Error downloading {symbol} {tf}: {e}. Skipping...")
            except Exception as e:
                print(f"Warning: Failed to process {symbol} {tf}. Error: {e}. Skipping...")

def main():
    parser = argparse.ArgumentParser(description="Cloud historical data downloader/scraper for FRXBOT.")
    parser.add_argument("--pairs", type=str, default=None, help="Comma-separated list of pairs to download (e.g. EURUSD,XAUUSD)")
    parser.add_argument("--timeframe", type=str, default=None, help="Timeframe (M5, M30, or H1)")
    args = parser.parse_args()
    
    target_pairs = None
    if args.pairs:
        target_pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()]
        
    run_scraper(target_pairs=target_pairs, single_timeframe=args.timeframe)

if __name__ == "__main__":
    main()
