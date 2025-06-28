import asyncio
from config.config import Config
from logger.logger import Logger
from handlers.bot import Handler
from services.bot_service import BotService
from services.crypto_service import CryptoService
from repositories.db import Repository
from aiogram import Bot

async def main():
    config = Config()
    config.validate()
    logger = Logger()
    
    try:
        repo = Repository(config.db_config, logger)
    except Exception as e:
        logger.error(f"Не удалось подключиться к базе данных: {e}")
        raise SystemExit("Не удалось запустить бота")

    crypto_service = CryptoService(config.crypto_bot_token, logger)
    bot_service = BotService(repo, crypto_service, logger)
    
    bot = Bot(token=config.bot_token)
    
    handler = Handler(bot, bot_service, logger)
    
    asyncio.create_task(bot_service.check_subscriptions(bot))
    
    logger.info("Запуск бота...")
    await handler.start()

if __name__ == "__main__":
    asyncio.run(main())