import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, types
from aiogram.exceptions import TelegramForbiddenError
from aiogram.enums import ChatMemberStatus
from src.models.user import User
from src.models.payments import Payment
from src.repositories.db import Repository
from src.services.crypto_service import CryptoService
from src.logger.logger import Logger

class BotService:
    TARIFFS = {
        "test" : {"days" : 1, "price" : 5, "name" : "Тестовый (1 день)"},
        "1month" : {"days" : 30, "price" : 70, "name" : "1 месяц"},
        "3months" : {"days" : 90, "price" : 180, "name" : "3 месяца (Выгода 50$)"},
        "6months" : {"days" : 180, "price" : 320, "name" : "6 месяцев (Выгода 100$)"},
        "12 months" : {"days" : 365, "price" : 600, "name" : "12 месяцев (Выгода 200$)"}
    }

    SUPPORTED_EXCHANGES = ["Binance", "Bybit", "OKX", "BingX"]
    def __init__(self, repo: Repository, crypto_service: CryptoService, group_id: int, logger: Logger):
        self.repo = repo
        self.crypto_service = crypto_service
        self.group_id = group_id
        self.logger = logger
    
    async def is_bot_in_group(self, bot: Bot) -> bool:
        try:
            member = await bot.get_chat_member(chat_id=self.group_id, user_id=bot.id)
            return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]
        except TelegramForbiddenError:
            self.logger.error("Бот не добавлен в группу или не имеет доступа")
            return False
        except Exception as e:
            self.logger.error(f"Ошибка при проверке статуса бота в группе: {e}")
            return False
    
    async def request_exchange(self, user_id: int, message: types.Message, bot: Bot):
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for exchange in self.SUPPORTED_EXCHANGES:
            keyboard.add(types.KeyboardButton(exchange))
        await bot.send_message(
            chat_id=user_id,
            text="Выберите биржу для получения торговых сигналов:",
            reply_markup=keyboard
        )
        self.logger.info(f"Пользователь {user_id} запрашивает биржу для торговых сигналов")
    
    async def request_api_key(self, user_id: int, message: types.Message, bot: Bot):
        await bot.send_message(
            user_id,
            "Пожалуйста, предоставьте API-ключ для выбранной биржи.\n\n"
            "🔒 <b>О безопасности:</b>\n"
            "1. Мы используем ваш API-ключ только для чтения данных (например, баланса или торговой истории).\n"
            "2. Ваш ключ надежно хранится и не передается третьим лицам.\n"
            "3. Мы не можем использовать ваш API-ключ для вывода средств или других действий без вашего явного разрешения.\n"
            "4. Убедитесь, что ваш API-ключ настроен только с правами на чтение (без прав на торговлю или вывод).\n\n"
            "Введите API-ключ:",
            parse_mode="HTML",
            reply_markup=types.ReplyKeyboardRemove()
        )
