import asyncio
import sys
from db.connection import init_db_pool, get_db_connection, close_db_pool

async def main():
    if len(sys.argv) < 2:
        print("Usage: python db/add_to_whitelist.py <user_id> [username] [full_name]")
        sys.exit(1)
        
    user_id = int(sys.argv[1])
    username = sys.argv[2] if len(sys.argv) > 2 else "whitelisted_user"
    full_name = sys.argv[3] if len(sys.argv) > 3 else "Whitelisted User"
    
    print(f"Connecting to database to whitelist User ID: {user_id}...")
    pool = await init_db_pool()
    if pool is None:
        print("Error: Could not connect to the database. Make sure your DATABASE_URL in .env is correct.")
        sys.exit(1)
        
    try:
        async with get_db_connection() as conn:
            existing = await conn.fetchrow("SELECT user_id, is_active FROM whitelist_users WHERE user_id = $1", user_id)
            if existing:
                if not existing['is_active']:
                    await conn.execute("UPDATE whitelist_users SET is_active = TRUE WHERE user_id = $1", user_id)
                    print(f"User {user_id} was already in database but inactive. Status updated to ACTIVE.")
                else:
                    print(f"User {user_id} is already in the whitelist and is active.")
            else:
                await conn.execute(
                    """
                    INSERT INTO whitelist_users (user_id, telegram_id, username, full_name, is_active)
                    VALUES ($1, $2, $3, $4, True)
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
