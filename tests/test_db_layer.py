"""Quick integration test for the refactored db layer."""
import os, sys, asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.connection import init_db_pool
from db.queries import is_user_whitelisted, log_signal

async def test():
    await init_db_pool()
    
    # Test whitelist check
    wl = await is_user_whitelisted(6827317690)
    print(f"Whitelist check (admin): {wl}")
    
    # Test signal logging
    row_id = await log_signal(
        user_id=6827317690,
        pair="XAUUSD",
        timeframe="H1",
        direction="LONG",
        entry_price=2650.0,
        sl_price=2640.0,
        tp1_price=2665.0,
        tp2_price=2680.0,
        lot_size=0.15,
        atr_value=7.5,
        signal_source="PULL",
        ai_confidence=75.0,
        ai_reasoning="Test signal from integration test"
    )
    print(f"Signal logged successfully: row_id={row_id}")
    print("All db layer tests PASSED.")

asyncio.run(test())
