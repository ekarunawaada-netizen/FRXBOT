import os
import sqlite3
import threading
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Resolve the absolute path to the data directory and db file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DB_DIR, "frxbot_brain.db")

# Thread safety lock to serialize write/read operations across threads
_db_lock = threading.Lock()


def init_db() -> None:
    """
    Initializes the SQLite database.
    Creates the necessary tables and indexes if they do not exist.
    Ensures that the target directory exists and operations are thread-safe.
    """
    with _db_lock:
        try:
            # Ensure the directory exists
            os.makedirs(DB_DIR, exist_ok=True)
            
            # Connect to database and set WAL mode for better concurrency
            conn = sqlite3.connect(DB_PATH)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()
            
            # 1. pair_optimized_rules table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pair_optimized_rules (
                    symbol TEXT,
                    timeframe TEXT,
                    mode TEXT,
                    sl_atr_multiplier REAL,
                    tp_atr_multiplier REAL,
                    bep_multiplier REAL,
                    win_rate REAL,
                    profit_factor REAL,
                    total_profit REAL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Create unique index to enable upserts on (symbol, mode)
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_pair_mode 
                ON pair_optimized_rules (symbol, mode);
            """)
            
            # 2. market_regimes_history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_regimes_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    calculated_atr REAL,
                    standard_deviation REAL,
                    market_state TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # 3. fundamental_insights table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fundamental_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    neural_bias TEXT,
                    confidence_score REAL,
                    macro_reasoning TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            conn.commit()
            conn.close()
            logger.info(f"SQLite database successfully initialized at {DB_PATH}")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite database: {e}", exc_info=True)
            raise


def save_optimized_parameters(
    symbol: str, 
    mode: str, 
    params_dict: Dict[str, Any], 
    results_dict: Dict[str, Any]
) -> bool:
    """
    Saves or updates optimized parameters for a given symbol and mode using UPSERT.
    
    Args:
        symbol: The currency pair (e.g. 'EURUSD')
        mode: The strategy mode (e.g. 'scalping', 'swing')
        params_dict: Dictionary containing 'timeframe', 'sl_atr_multiplier', 
                     'tp_atr_multiplier', 'bep_multiplier'
        results_dict: Dictionary containing 'win_rate', 'profit_factor', 'total_profit'
        
    Returns:
        True if the database write succeeded, False otherwise.
    """
    with _db_lock:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            timeframe = params_dict.get("timeframe", "H1")
            sl_atr_multiplier = float(params_dict.get("sl_atr_multiplier", 1.5))
            tp_atr_multiplier = float(params_dict.get("tp_atr_multiplier", 3.0))
            bep_multiplier = float(params_dict.get("bep_multiplier", 1.0))
            
            win_rate = float(results_dict.get("win_rate", 0.0))
            profit_factor = float(results_dict.get("profit_factor", 0.0))
            total_profit = float(results_dict.get("total_profit", 0.0))
            updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            
            # Use INSERT OR REPLACE INTO (UPSERT) leveraging the idx_pair_mode index
            cursor.execute("""
                INSERT OR REPLACE INTO pair_optimized_rules (
                    symbol, timeframe, mode, sl_atr_multiplier, tp_atr_multiplier, 
                    bep_multiplier, win_rate, profit_factor, total_profit, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                symbol.upper(), timeframe, mode.lower(), sl_atr_multiplier, tp_atr_multiplier,
                bep_multiplier, win_rate, profit_factor, total_profit, updated_at
            ))
            
            conn.commit()
            conn.close()
            logger.info(f"Optimized parameters saved for {symbol} ({mode})")
            return True
        except Exception as e:
            logger.error(f"Error saving optimized parameters for {symbol} ({mode}): {e}", exc_info=True)
            return False


def get_active_parameters(symbol: str, mode: str) -> Optional[Dict[str, Any]]:
    """
    Fetches the active optimized parameters for a given symbol and mode.
    
    Args:
        symbol: The currency pair (e.g. 'EURUSD')
        mode: The strategy mode (e.g. 'scalping', 'swing')
        
    Returns:
        A dictionary containing the parameters and performance metrics,
        or None if no records are found.
    """
    with _db_lock:
        try:
            conn = sqlite3.connect(DB_PATH)
            # Enable row factory to access columns by name
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    symbol, timeframe, mode, sl_atr_multiplier, tp_atr_multiplier, 
                    bep_multiplier, win_rate, profit_factor, total_profit, updated_at
                FROM pair_optimized_rules
                WHERE UPPER(symbol) = ? AND LOWER(mode) = ?;
            """, (symbol.upper(), mode.lower()))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Error retrieving parameters for {symbol} ({mode}): {e}", exc_info=True)
            return None


def get_latest_regime(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetches the most recent market regime entry for a given symbol
    from the market_regimes_history table.

    Args:
        symbol: The currency pair (e.g. 'XAUUSD')

    Returns:
        A dictionary with keys: symbol, calculated_atr, standard_deviation,
        market_state, timestamp. Returns None if no records are found.
    """
    with _db_lock:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT symbol, calculated_atr, standard_deviation,
                       market_state, timestamp
                FROM market_regimes_history
                WHERE UPPER(symbol) = ?
                ORDER BY timestamp DESC
                LIMIT 1;
            """, (symbol.upper(),))

            row = cursor.fetchone()
            conn.close()

            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Error retrieving regime for {symbol}: {e}", exc_info=True)
            return None
