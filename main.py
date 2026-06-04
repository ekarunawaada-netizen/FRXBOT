import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from core.config import settings
from bot.handlers.commands import router as commands_router

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def on_startup(bot: Bot) -> None:
    """Callback function triggered when the bot starts polling."""
    logger.info("Bot is starting up...")
    admin_ids = settings.admin_ids
    
    startup_message = (
        "🤖 <b>AI Forex Co-Pilot Bot is Online!</b>\n\n"
        "Sistem telah berhasil diinisialisasi dan siap menerima perintah analisa forex."
    )
    
    for admin_id in admin_ids:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=startup_message,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Sent startup notification to admin ID: {admin_id}")
        except Exception as e:
            logger.error(f"Failed to send startup notification to admin ID {admin_id}: {str(e)}")

async def main() -> None:
    """Bootstrap and start polling the Telegram Bot."""
    # Ensure token is loaded
    if not settings.telegram_bot_token:
        logger.critical("TELEGRAM_BOT_TOKEN is missing or empty. Exiting.")
        sys.exit(1)

    # Initialize bot and dispatcher
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()

    # Register routers
    dp.include_router(commands_router)

    # Register startup callback
    dp.startup.register(on_startup)

    try:
        logger.info("Starting polling...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical(f"Bot polling error: {str(e)}", exc_info=True)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
