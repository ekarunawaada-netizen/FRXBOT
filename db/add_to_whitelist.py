"""
db/add_to_whitelist.py — Whitelist Management CLI (SQLite)

Adds or reactivates a Telegram user in the local whitelist_users table
inside data/frxbot_brain.db.

Usage:
    python db/add_to_whitelist.py <user_id> [username] [full_name]
"""

import asyncio
import os
import sys

# Add project root to path for standalone execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import init_db_pool, get_db_connection, close_db_pool


async def main():
    if len(sys.argv) < 2:
        print("Usage: python db/add_to_whitelist.py <user_id> [username] [full_name]")
        sys.exit(1)

    user_id = int(sys.argv[1])
    username = sys.argv[2] if len(sys.argv) > 2 else "whitelisted_user"
    full_name = sys.argv[3] if len(sys.argv) > 3 else "Whitelisted User"

    print(f"Connecting to local SQLite database to whitelist User ID: {user_id}...")
    result = await init_db_pool()
    if not result:
        print("Error: Could not initialize the local SQLite database.")
        sys.exit(1)

    try:
        async with get_db_connection() as conn:
            existing = await conn.fetchrow(
                "SELECT user_id, is_active FROM whitelist_users WHERE user_id = ?;",
                user_id
            )
            if existing:
                if not existing['is_active']:
                    await conn.execute(
                        "UPDATE whitelist_users SET is_active = 1 WHERE user_id = ?;",
                        user_id
                    )
                    print(f"User {user_id} was already in database but inactive. Status updated to ACTIVE.")
                else:
                    print(f"User {user_id} is already in the whitelist and is active.")
            else:
                await conn.execute(
                    """
                    INSERT INTO whitelist_users (user_id, telegram_id, username, full_name, is_active)
                    VALUES (?, ?, ?, ?, 1);
                    """,
                    user_id,
                    user_id,
                    username,
                    full_name
                )
                print(f"Successfully added User ID {user_id} ({full_name}) to the whitelist table.")
    except Exception as e:
        print(f"Database error: {e}")
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
